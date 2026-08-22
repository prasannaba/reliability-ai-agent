"""Local document ingestion and hybrid retrieval for the reliability knowledge base."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Callable

import chromadb
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = BACKEND_DIR.parent
load_dotenv(REPOSITORY_ROOT / ".env")

KNOWLEDGE_BASE_DIR = REPOSITORY_ROOT / "Knowledge_Base"
INDEX_DIR = BACKEND_DIR / ".rag"
MANIFEST_PATH = INDEX_DIR / "manifest.json"
COLLECTION_NAME = "reliability_knowledge"
SUPPORTED_SUFFIXES = {".md", ".txt", ".pdf", ".doc", ".docx", ".ppt", ".pptx"}
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MANIFEST_SCHEMA = 2
DEFAULT_MAX_TOKENS = 384
DEFAULT_OVERLAP_TOKENS = 64
TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


@dataclass(frozen=True)
class KnowledgeChunk:
    text: str
    source: str
    chunk_number: int
    page: int | None = None
    section: str | None = None
    content_type: str = "text"

    @property
    def identifier(self) -> str:
        raw = f"{self.source}\0{self.chunk_number}\0{self.text}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def metadata(self) -> dict[str, str | int]:
        result: dict[str, str | int] = {
            "source": self.source,
            "chunk_number": self.chunk_number,
            "content_type": self.content_type,
        }
        if self.page is not None:
            result["page"] = self.page
        if self.section:
            result["section"] = self.section
        return result


TokenCounter = Callable[[str], int]


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tokenize_query(text: str) -> list[str]:
    return [term.casefold() for term in TOKEN_RE.findall(text) if len(term) > 2]


def default_token_count(text: str) -> int:
    words = text.split()
    return max(1, len(words)) if text.strip() else 0


def _split_text(
    text: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap: int = DEFAULT_OVERLAP_TOKENS,
    count_tokens: TokenCounter | None = None,
) -> list[str]:
    """Split text at paragraph boundaries using token counts, with modest overlap."""
    counter = count_tokens or default_token_count
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""

    def overlap_prefix(value: str) -> str:
        if not overlap or not value:
            return ""
        words = value.split()
        if len(words) <= overlap:
            return value
        return " ".join(words[-overlap:])

    def flush_long(remaining: str) -> str:
        words = remaining.split()
        while counter(" ".join(words)) > max_tokens and words:
            piece_words: list[str] = []
            for word in words:
                candidate = " ".join([*piece_words, word]).strip()
                if piece_words and counter(candidate) > max_tokens:
                    break
                piece_words.append(word)
            if not piece_words:
                piece_words = [words[0]]
            piece = " ".join(piece_words).strip()
            chunks.append(piece)
            consumed = len(piece_words)
            keep = max(0, overlap) if overlap < consumed else 0
            words = words[consumed - keep :] if keep else words[consumed:]
        return " ".join(words).strip()

    for paragraph in paragraphs:
        remaining = flush_long(paragraph)
        if not remaining:
            continue
        candidate = f"{current}\n\n{remaining}".strip() if current else remaining
        if counter(candidate) <= max_tokens:
            current = candidate
        else:
            if current:
                chunks.append(current)
            prefix = overlap_prefix(current)
            current = f"{prefix}\n\n{remaining}".strip() if prefix else remaining
            if counter(current) > max_tokens:
                leftover = flush_long(current)
                current = leftover
    if current:
        chunks.append(current)
    return chunks


def _load_text_document(path: Path, source: str, count_tokens: TokenCounter | None = None) -> list[KnowledgeChunk]:
    text = path.read_text(encoding="utf-8", errors="replace")
    chunks: list[KnowledgeChunk] = []
    section: str | None = None
    section_text: list[str] = []

    def append_section() -> None:
        nonlocal section_text
        body = "\n".join(section_text).strip()
        for part in _split_text(body, count_tokens=count_tokens):
            content = f"{section}\n\n{part}" if section else part
            chunks.append(KnowledgeChunk(content, source, len(chunks), section=section))
        section_text = []

    for line in text.splitlines():
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            append_section()
            section = heading.group(1)
        else:
            section_text.append(line)
    append_section()
    return chunks


def _docling_page(meta: Any) -> int | None:
    for item in getattr(meta, "doc_items", None) or []:
        for provenance in getattr(item, "prov", None) or []:
            page = getattr(provenance, "page_no", None)
            if isinstance(page, int):
                return page
    return None


def _load_rich_document(path: Path, source: str, count_tokens: TokenCounter | None = None) -> list[KnowledgeChunk]:
    """Use Docling locally for layout-aware PDF and Office extraction."""
    try:
        from docling.chunking import HierarchicalChunker
        from docling.document_converter import DocumentConverter
    except ImportError as exc:  # pragma: no cover - depends on optional system package
        raise RuntimeError("PDF and Office ingestion requires Docling; install backend/requirements.txt") from exc

    document = DocumentConverter().convert(source=str(path)).document
    chunker = HierarchicalChunker()
    chunks: list[KnowledgeChunk] = []
    for raw_chunk in chunker.chunk(dl_doc=document):
        meta = getattr(raw_chunk, "meta", None)
        headings = getattr(meta, "headings", None) or []
        section = " > ".join(str(value) for value in headings if value) or None
        context = [*headings]
        raw_text = str(getattr(raw_chunk, "text", "") or "").strip()
        if not raw_text:
            continue
        contextualized = "\n\n".join([*(str(value) for value in context if value), raw_text])
        doc_items = getattr(meta, "doc_items", None) or []
        labels = {str(getattr(item, "label", "")).casefold() for item in doc_items}
        content_type = "table" if any("table" in label for label in labels) else "text"
        for part in _split_text(contextualized, count_tokens=count_tokens):
            chunks.append(
                KnowledgeChunk(
                    text=part,
                    source=source,
                    chunk_number=len(chunks),
                    page=_docling_page(meta),
                    section=section,
                    content_type=content_type,
                )
            )
    return chunks


def load_document(
    path: Path,
    knowledge_base_dir: Path = KNOWLEDGE_BASE_DIR,
    count_tokens: TokenCounter | None = None,
) -> list[KnowledgeChunk]:
    source = path.relative_to(knowledge_base_dir).as_posix()
    if path.suffix.casefold() in {".md", ".txt"}:
        return _load_text_document(path, source, count_tokens=count_tokens)
    return _load_rich_document(path, source, count_tokens=count_tokens)


class LexicalIndex:
    """Persisted BM25 corpus keyed by chunk id; never requires a full Chroma scan at query time."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.ids: list[str] = []
        self.tokenized: list[list[str]] = []
        self.sources: dict[str, str] = {}
        self._dirty = False

    def load(self) -> None:
        if not self.path.exists():
            self.ids, self.tokenized, self.sources = [], [], {}
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.ids, self.tokenized, self.sources = [], [], {}
            return
        self.ids = list(payload.get("ids") or [])
        self.tokenized = [list(tokens) for tokens in payload.get("tokenized") or []]
        self.sources = {str(key): str(value) for key, value in (payload.get("sources") or {}).items()}
        if len(self.tokenized) != len(self.ids):
            self.ids, self.tokenized, self.sources = [], [], {}

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"ids": self.ids, "tokenized": self.tokenized, "sources": self.sources}, indent=2),
            encoding="utf-8",
        )
        self._dirty = False

    def clear(self) -> None:
        self.ids, self.tokenized, self.sources = [], [], {}
        self._dirty = True

    def remove_source(self, source: str) -> None:
        keep_ids: list[str] = []
        keep_tokens: list[list[str]] = []
        for identifier, tokens in zip(self.ids, self.tokenized):
            if self.sources.get(identifier) == source:
                self.sources.pop(identifier, None)
                continue
            keep_ids.append(identifier)
            keep_tokens.append(tokens)
        if len(keep_ids) != len(self.ids):
            self.ids = keep_ids
            self.tokenized = keep_tokens
            self._dirty = True

    def upsert_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        if chunks:
            self.remove_source(chunks[0].source)
        for chunk in chunks:
            self.ids.append(chunk.identifier)
            self.tokenized.append(tokenize_query(chunk.text) or tokenize_query(chunk.source) or ["document"])
            self.sources[chunk.identifier] = chunk.source
            self._dirty = True

    def query(self, query: str, limit: int) -> list[tuple[str, float]]:
        terms = tokenize_query(query)
        if not terms or not self.ids:
            return []
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            rankings: list[tuple[str, float]] = []
            for identifier, tokens in zip(self.ids, self.tokenized):
                score = float(sum(tokens.count(term) for term in terms))
                if score:
                    rankings.append((identifier, score))
            rankings.sort(key=lambda item: (-item[1], item[0]))
            return rankings[:limit]

        scores = BM25Okapi(self.tokenized).get_scores(terms)
        ranked = sorted(
            ((self.ids[index], float(score)) for index, score in enumerate(scores) if score > 0),
            key=lambda item: (-item[1], item[0]),
        )
        return ranked[:limit]


class ReliabilityKnowledgeBase:
    """Persistent local embeddings with incremental ingestion and hybrid retrieval."""

    def __init__(
        self,
        knowledge_base_dir: Path = KNOWLEDGE_BASE_DIR,
        index_dir: Path = INDEX_DIR,
        embedding_model_name: str | None = None,
    ) -> None:
        self.knowledge_base_dir = knowledge_base_dir
        self.index_dir = index_dir
        self.manifest_path = index_dir / "manifest.json"
        self.embedding_model_name = embedding_model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        self.embedding_local_files_only = os.getenv("EMBEDDING_LOCAL_FILES_ONLY", "true").casefold() not in {
            "0",
            "false",
            "no",
        }
        self.embedding_device = os.getenv("EMBEDDING_DEVICE") or None
        self._lock = RLock()
        self._embedder: Any = None
        self._client: Any = None
        self._collection: Any = None
        self._lexical = LexicalIndex(index_dir / "bm25.json")
        self._lexical_loaded = False

    def _token_count(self, text: str) -> int:
        tokenizer = getattr(self.embedder, "tokenizer", None)
        if tokenizer is None:
            return default_token_count(text)
        encode = getattr(tokenizer, "encode", None)
        if callable(encode):
            try:
                return max(1, len(encode(text, add_special_tokens=False))) if text.strip() else 0
            except TypeError:
                return max(1, len(encode(text))) if text.strip() else 0
        tokenize = getattr(tokenizer, "tokenize", None)
        if callable(tokenize):
            return max(1, len(tokenize(text))) if text.strip() else 0
        return default_token_count(text)

    @property
    def embedder(self) -> Any:
        if self._embedder is None:
            # Keep the heavy PyTorch/Transformers import out of MCP startup and
            # processes that only use the non-search tools.
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(
                self.embedding_model_name,
                device=self.embedding_device,
                local_files_only=self.embedding_local_files_only,
            )
        return self._embedder

    @property
    def collection(self) -> Any:
        if self._collection is None:
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.index_dir / "chroma"))
            self._collection = self._client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
        return self._collection

    def _lexical_index(self) -> LexicalIndex:
        if not self._lexical_loaded:
            self._lexical.load()
            self._lexical_loaded = True
        return self._lexical

    def _empty_manifest(self) -> dict[str, Any]:
        return {"schema": MANIFEST_SCHEMA, "embedding_model": self.embedding_model_name, "files": {}}

    def _read_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return self._empty_manifest()
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_manifest()
        return manifest

    def _reset_store(self) -> None:
        if self._client is None:
            _ = self.collection
        try:
            self._client.delete_collection(COLLECTION_NAME)
        except ValueError:
            pass
        self._collection = self._client.get_or_create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
        lexical = self._lexical_index()
        lexical.clear()
        lexical.save()

    def _manifest(self) -> dict[str, Any]:
        manifest = self._read_manifest()
        if manifest.get("schema") != MANIFEST_SCHEMA or manifest.get("embedding_model") != self.embedding_model_name:
            self._reset_store()
            return self._empty_manifest()
        return manifest

    def _documents(self) -> list[Path]:
        if not self.knowledge_base_dir.exists():
            return []
        return sorted(
            path
            for path in self.knowledge_base_dir.rglob("*")
            if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES
        )

    def _index_is_current(self, manifest: dict[str, Any], current_paths: dict[str, Path]) -> bool:
        old_files: dict[str, Any] = manifest.get("files") or {}
        if set(old_files) != set(current_paths):
            return False
        lexical_path = self.index_dir / "bm25.json"
        if current_paths and not lexical_path.exists():
            return False
        return all(old_files.get(source, {}).get("sha256") == _file_digest(path) for source, path in current_paths.items())

    def ensure_index(self, force: bool = False) -> list[str]:
        """Synchronize changed files and return non-fatal conversion warnings."""
        with self._lock:
            current_paths = {path.relative_to(self.knowledge_base_dir).as_posix(): path for path in self._documents()}
            stored = self._read_manifest()
            if (
                not force
                and stored.get("schema") == MANIFEST_SCHEMA
                and stored.get("embedding_model") == self.embedding_model_name
                and self._index_is_current(stored, current_paths)
            ):
                return []

            manifest = self._manifest()
            old_files: dict[str, Any] = manifest.setdefault("files", {})
            warnings: list[str] = []
            lexical = self._lexical_index()

            for removed in sorted(set(old_files) - set(current_paths)):
                self.collection.delete(where={"source": removed})
                lexical.remove_source(removed)
                old_files.pop(removed, None)

            for source, path in current_paths.items():
                digest = _file_digest(path)
                if not force and old_files.get(source, {}).get("sha256") == digest:
                    continue
                try:
                    chunks = load_document(path, self.knowledge_base_dir, count_tokens=self._token_count)
                    if not chunks:
                        raise RuntimeError("conversion produced no searchable text")
                    embeddings = self.embedder.encode(
                        [chunk.text for chunk in chunks], normalize_embeddings=True, show_progress_bar=False
                    ).tolist()
                    self.collection.delete(where={"source": source})
                    lexical.remove_source(source)
                    for start in range(0, len(chunks), 64):
                        batch = chunks[start : start + 64]
                        self.collection.upsert(
                            ids=[chunk.identifier for chunk in batch],
                            documents=[chunk.text for chunk in batch],
                            metadatas=[chunk.metadata() for chunk in batch],
                            embeddings=embeddings[start : start + 64],
                        )
                    lexical.upsert_chunks(chunks)
                    old_files[source] = {"sha256": digest, "chunks": len(chunks)}
                except Exception as exc:  # keep other documents searchable
                    warnings.append(f"{source}: {exc}")

            self.index_dir.mkdir(parents=True, exist_ok=True)
            lexical.save()
            self.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            return warnings

    def status(self) -> dict[str, Any]:
        warnings = self.ensure_index()
        manifest = self._read_manifest()
        chunk_count = 0
        if (self.index_dir / "chroma").exists():
            chunk_count = self.collection.count()
        return {
            "embedding_model": self.embedding_model_name,
            "chunk_count": chunk_count,
            "files": manifest.get("files") or {},
            "index_warnings": warnings,
        }

    def search(self, query: str, max_results: int = 3) -> dict[str, Any]:
        terms = tokenize_query(query)
        if not terms:
            raise ValueError("query must contain a searchable term")
        max_results = max(1, min(max_results, 10))
        warnings = self.ensure_index()
        if self.collection.count() == 0:
            return {"query": query, "matches": [], "index_warnings": warnings}

        candidate_count = min(max(max_results * 4, 12), self.collection.count())
        query_embedding = self.embedder.encode([query], normalize_embeddings=True, show_progress_bar=False).tolist()
        vector = self.collection.query(
            query_embeddings=query_embedding,
            n_results=candidate_count,
            include=["documents", "metadatas", "distances"],
        )

        rankings: dict[str, float] = {}
        vector_ids = (vector.get("ids") or [[]])[0]
        for rank, identifier in enumerate(vector_ids, start=1):
            rankings[identifier] = rankings.get(identifier, 0.0) + 1.0 / (60 + rank)

        for rank, (identifier, _) in enumerate(self._lexical_index().query(query, candidate_count), start=1):
            rankings[identifier] = rankings.get(identifier, 0.0) + 1.0 / (60 + rank)

        if not rankings:
            return {"query": query, "matches": [], "index_warnings": warnings}

        ranked_ids = sorted(rankings, key=lambda identifier: (-rankings[identifier], identifier))[:max_results]
        fetched = self.collection.get(ids=ranked_ids, include=["documents", "metadatas"])
        records = {
            identifier: (document, metadata)
            for identifier, document, metadata in zip(
                fetched.get("ids") or [],
                fetched.get("documents") or [],
                fetched.get("metadatas") or [],
            )
        }
        best_score = rankings[ranked_ids[0]]
        matches = []
        for identifier in ranked_ids:
            document, metadata = records.get(identifier, ("", {}))
            matches.append(
                {
                    **(metadata or {}),
                    "score": round(rankings[identifier] / best_score, 4),
                    "content": document,
                }
            )
        return {"query": query, "matches": matches, "index_warnings": warnings}


def main() -> None:
    """Build or refresh the local index from the command line."""
    knowledge_base = ReliabilityKnowledgeBase()
    if "--download-model" in os.sys.argv:
        knowledge_base.embedding_local_files_only = False
    warnings = knowledge_base.ensure_index(force="--force" in os.sys.argv)
    print(f"Indexed {knowledge_base.collection.count()} chunks with {knowledge_base.embedding_model_name}")
    for warning in warnings:
        print(f"Warning: {warning}")


if __name__ == "__main__":
    main()
