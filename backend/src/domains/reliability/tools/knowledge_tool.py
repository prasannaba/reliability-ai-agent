"""Hybrid search over the domain knowledge base (plain fn; registered in server.py)."""

from __future__ import annotations

from typing import Any

from src.host.domain_registry import get_active_domain
from src.knowledge.base import GenericKnowledgeBase

_KB: GenericKnowledgeBase | None = None


def knowledge_base() -> GenericKnowledgeBase:
    """Lazily built per-domain KB so non-search tools skip the heavy embedder."""
    global _KB
    if _KB is None:
        domain = get_active_domain("reliability")
        _KB = GenericKnowledgeBase(
            knowledge_base_dir=domain.knowledge_dir,
            index_dir=domain.index_dir,
            collection_name=domain.collection,
        )
    return _KB


def search_knowledge(query: str, max_results: int = 3) -> dict[str, Any]:
    """Hybrid-search local Markdown, text, PDF, Word, and PowerPoint documents."""
    return knowledge_base().search(query, max_results)
