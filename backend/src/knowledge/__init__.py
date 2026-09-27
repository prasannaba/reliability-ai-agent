"""Document ingestion and hybrid retrieval (generic engine + compat aliases)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # Import-time cost only for type checkers.
    from src.knowledge.base import (
        KNOWLEDGE_BASE_DIR as KNOWLEDGE_BASE_DIR,
    )
    from src.knowledge.base import (
        SUPPORTED_SUFFIXES as SUPPORTED_SUFFIXES,
    )
    from src.knowledge.base import (
        GenericKnowledgeBase as GenericKnowledgeBase,
    )
    from src.knowledge.base import (
        ReliabilityKnowledgeBase as ReliabilityKnowledgeBase,
    )

__all__ = [
    "KNOWLEDGE_BASE_DIR",
    "SUPPORTED_SUFFIXES",
    "GenericKnowledgeBase",
    "ReliabilityKnowledgeBase",
]


def __getattr__(name: str) -> Any:
    """Lazily re-export ``src.knowledge.base`` (avoids a runpy warning for
    ``python -m src.knowledge.base`` and skips heavy imports until used)."""
    if name in __all__:
        import src.knowledge.base as _base

        return getattr(_base, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
