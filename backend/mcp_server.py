"""MCP server exposing reliability engineering capabilities."""

import re
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from life_data_analysis_weibull import plot_weibull_analysis
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("reliability-engineering")
KNOWLEDGE_BASE_DIR = Path(__file__).resolve().parent.parent / "Knowledge_Base"
PLOT_LOCK = Lock()


def _json_value(value: Any) -> Any:
    """Convert NumPy and path values into MCP-safe JSON values."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


@lru_cache(maxsize=1)
def _knowledge_chunks() -> tuple[tuple[str, str], ...]:
    """Load Markdown paragraphs once; retrieval stays local and deterministic."""
    chunks: list[tuple[str, str]] = []
    for path in sorted(KNOWLEDGE_BASE_DIR.glob("*.md")):
        paragraphs = [part.strip() for part in path.read_text(encoding="utf-8").split("\n\n")]
        chunks.extend((path.name, paragraph) for paragraph in paragraphs if paragraph)
    return tuple(chunks)


@mcp.tool()
def calculate_b_life(beta: float, eta: float, percentage: float) -> int:
    """Calculate Weibull B-life for a failure percentile between 0 and 100."""
    if beta <= 0:
        raise ValueError("beta must be greater than zero")
    if eta <= 0:
        raise ValueError("eta must be greater than zero")
    HUNDRED_PERCENT = 100
    if not 0 < percentage < HUNDRED_PERCENT:
        raise ValueError("percentage must be between 0 and 100")

    fraction_failed = percentage / 100.0
    return int(round(eta * (-np.log1p(-fraction_failed)) ** (1 / beta)))


@mcp.tool()
def analyze_weibull(failure_times: list[float], title: str = "Weibull Probability Plot") -> dict[str, Any]:
    """Fit Weibull failure data, create a plot, and return fit statistics."""
    MIN_FAILURES = 2
    if len(failure_times) < MIN_FAILURES:
        raise ValueError("at least two failure times are required")
    if any(value <= 0 for value in failure_times):
        raise ValueError("failure times must be greater than zero")

    # Matplotlib's pyplot state is process-global and is not safe to mutate concurrently.
    with PLOT_LOCK:
        result = plot_weibull_analysis(np.asarray(failure_times, dtype=float), title)
    normalized = {key: _json_value(value) for key, value in result.items()}
    plot_path = Path(normalized["file"])
    normalized["file"] = plot_path.name
    normalized["message"] = f"Weibull plot saved as {plot_path.name}"
    return normalized


@mcp.tool()
def search_reliability_knowledge(query: str, max_results: int = 3) -> dict[str, Any]:
    """Search the local reliability and organizational Markdown knowledge base."""
    MINIMUM_TERM_LENGTH = 2
    terms = {term.casefold() for term in re.findall(r"[A-Za-z0-9]+", query) if len(term) > MINIMUM_TERM_LENGTH}
    if not terms:
        raise ValueError("query must contain a searchable term")
    max_results = max(1, min(max_results, 10))

    ranked: list[tuple[int, str, str]] = []
    for source, text in _knowledge_chunks():
        searchable = text.casefold()
        score = sum(searchable.count(term) for term in terms)
        if score:
            ranked.append((score, source, text))
    ranked.sort(key=lambda item: (-item[0], item[1]))

    matches = [{"source": source, "content": text} for _, source, text in ranked[:max_results]]
    return {"query": query, "matches": matches}


if __name__ == "__main__":
    mcp.run(transport="stdio")
