import sys
from pathlib import Path

import numpy as np
from docx import Document
from pptx import Presentation

sys.path.append(str(Path(__file__).resolve().parents[1]))

from knowledge_base import ReliabilityKnowledgeBase, SUPPORTED_SUFFIXES, _split_text, load_document


class FakeEmbedder:
    """Small deterministic embedder that keeps tests offline."""

    def encode(self, texts, normalize_embeddings=True, show_progress_bar=False):
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vector = np.asarray(
                [
                    lowered.count("weibull") + lowered.count("shape"),
                    lowered.count("capacitor") + lowered.count("electronic"),
                    lowered.count("prasanna") + 0.01,
                ],
                dtype=float,
            )
            if normalize_embeddings:
                vector /= np.linalg.norm(vector) or 1.0
            vectors.append(vector)
        return np.asarray(vectors)


def test_supported_formats_exclude_images():
    assert {".pdf", ".doc", ".docx", ".ppt", ".pptx"} <= SUPPORTED_SUFFIXES
    assert not ({".png", ".jpg", ".jpeg"} & SUPPORTED_SUFFIXES)


def test_markdown_loader_preserves_heading_metadata(tmp_path):
    knowledge_dir = tmp_path / "Knowledge_Base"
    knowledge_dir.mkdir()
    path = knowledge_dir / "handbook.md"
    path.write_text("# Capacitors\n\nFailure rate depends on environment.", encoding="utf-8")

    chunks = load_document(path, knowledge_dir)

    assert chunks[0].source == "handbook.md"
    assert chunks[0].section == "Capacitors"
    assert "Failure rate" in chunks[0].text


def test_incremental_hybrid_index_and_search(tmp_path):
    knowledge_dir = tmp_path / "Knowledge_Base"
    knowledge_dir.mkdir()
    index_dir = tmp_path / ".rag"
    source = knowledge_dir / "standard.md"
    source.write_text(
        "# Electronic Parts\n\nCapacitor failure rates depend on environment and quality.",
        encoding="utf-8",
    )
    knowledge_base = ReliabilityKnowledgeBase(
        knowledge_base_dir=knowledge_dir,
        index_dir=index_dir,
        embedding_model_name="test-embedding-model",
    )
    knowledge_base._embedder = FakeEmbedder()

    first = knowledge_base.search("capacitor reliability", max_results=2)
    assert first["matches"][0]["source"] == "standard.md"
    assert first["matches"][0]["section"] == "Electronic Parts"
    assert first["index_warnings"] == []

    source.write_text("# Weibull\n\nThe shape parameter is beta.", encoding="utf-8")
    second = knowledge_base.search("Weibull shape parameter", max_results=2)
    assert "shape parameter" in second["matches"][0]["content"]
    assert knowledge_base.collection.count() == 1


def test_token_split_packs_paragraphs_by_word_count():
    chunks = _split_text("alpha beta gamma\n\ndelta epsilon", max_tokens=3, overlap=1, count_tokens=lambda text: len(text.split()))
    assert chunks
    assert all(len(chunk.split()) <= 4 for chunk in chunks)


def test_search_does_not_require_full_collection_scan(tmp_path, monkeypatch):
    knowledge_dir = tmp_path / "Knowledge_Base"
    knowledge_dir.mkdir()
    (knowledge_dir / "standard.md").write_text("# Weibull\n\nThe shape parameter is beta.", encoding="utf-8")
    knowledge_base = ReliabilityKnowledgeBase(
        knowledge_base_dir=knowledge_dir,
        index_dir=tmp_path / ".rag",
        embedding_model_name="test-embedding-model",
    )
    knowledge_base._embedder = FakeEmbedder()
    original_get = knowledge_base.collection.get

    def guarded_get(*args, **kwargs):
        assert args or kwargs.get("ids") is not None
        return original_get(*args, **kwargs)

    knowledge_base.collection.get = guarded_get  # type: ignore[method-assign]
    result = knowledge_base.search("Weibull shape", max_results=1)
    assert result["matches"]


def test_docling_loads_docx_and_pptx_without_image_pipeline(tmp_path):
    knowledge_dir = tmp_path / "Knowledge_Base"
    knowledge_dir.mkdir()

    docx_path = knowledge_dir / "standard.docx"
    document = Document()
    document.add_heading("Reliability Standard", level=1)
    document.add_paragraph("Electronic component failure rate guidance.")
    document.save(docx_path)

    pptx_path = knowledge_dir / "training.pptx"
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[1])
    slide.shapes.title.text = "Reliability Training"
    slide.placeholders[1].text = "Weibull shape parameter beta"
    presentation.save(pptx_path)

    docx_chunks = load_document(docx_path, knowledge_dir)
    pptx_chunks = load_document(pptx_path, knowledge_dir)

    assert any("failure rate guidance" in chunk.text for chunk in docx_chunks)
    assert any("shape parameter beta" in chunk.text for chunk in pptx_chunks)
