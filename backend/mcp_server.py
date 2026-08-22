"""MCP server exposing reliability engineering capabilities."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
from mcp.server.mcpserver import MCPServer

from knowledge_base import ReliabilityKnowledgeBase
from life_data_analysis_weibull import plot_weibull_analysis
from reliability_report import build_reliability_report

mcp = MCPServer("reliability-engineering")
PLOT_LOCK = Lock()
KNOWLEDGE_BASE = ReliabilityKnowledgeBase()


def _json_value(value: Any) -> Any:
    """Convert NumPy, tuples, and path values into MCP-safe JSON values."""
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def load_plugins(server: Any) -> None:
    """Load `register(mcp)` hooks from backend/plugins/*.py."""
    import plugins

    for module_info in pkgutil.iter_modules(plugins.__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module(f"plugins.{module_info.name}")
        register = getattr(module, "register", None)
        if callable(register):
            register(server)


@mcp.tool()
def calculate_b_life(beta: float, eta: float, percentage: float) -> int:
    """Calculate Weibull B-life for a failure percentile between 0 and 100."""
    if beta <= 0:
        raise ValueError("beta must be greater than zero")
    if eta <= 0:
        raise ValueError("eta must be greater than zero")
    hundred_percent = 100
    if not 0 < percentage < hundred_percent:
        raise ValueError("percentage must be between 0 and 100")

    fraction_failed = percentage / 100.0
    return int(round(eta * (-np.log1p(-fraction_failed)) ** (1 / beta)))


@mcp.tool()
def analyze_weibull(
    failure_times: list[float],
    title: str = "Weibull Probability Plot",
    censored_times: list[float] | None = None,
    method: str = "rry",
    confidence: float = 0.9,
) -> dict[str, Any]:
    """Fit 2-parameter Weibull data, plot probability paper, and return statistics.

    Use censored_times for right-censored suspensions. method is 'rry' (default,
    median ranks + rank regression on Y) or 'mle'. confidence is the two-sided
    bootstrap interval on the line and on B10/B20 (for example 0.9).
    """
    min_failures = 2
    if len(failure_times) < min_failures:
        raise ValueError("at least two failure times are required")
    if any(value <= 0 for value in failure_times):
        raise ValueError("failure times must be greater than zero")
    if censored_times and any(value < 0 for value in censored_times):
        raise ValueError("censored times must be zero or greater")
    if method not in {"rry", "mle"}:
        raise ValueError("method must be 'rry' or 'mle'")
    if not 0.5 <= confidence < 1:
        raise ValueError("confidence must be in [0.5, 1)")

    with PLOT_LOCK:
        result = plot_weibull_analysis(
            np.asarray(failure_times, dtype=float),
            title,
            censored_times=censored_times,
            method=method,
            confidence=confidence,
        )
    normalized = {key: _json_value(value) for key, value in result.items()}
    plot_path = Path(normalized["file"])
    normalized["file"] = plot_path.name
    normalized["message"] = f"Weibull plot saved as {plot_path.name}"
    return normalized


@mcp.tool()
def export_reliability_report(
    failure_times: list[float],
    question: str = "",
    censored_times: list[float] | None = None,
    method: str = "rry",
    confidence: float = 0.9,
    warranty_hours: float | None = None,
    knowledge_query: str | None = None,
) -> dict[str, Any]:
    """Build a one-page markdown report from tool-computed Weibull results and optional KB cites."""
    analysis = analyze_weibull(
        failure_times,
        title="Weibull Probability Plot",
        censored_times=censored_times,
        method=method,
        confidence=confidence,
    )
    citations = []
    if knowledge_query:
        search = KNOWLEDGE_BASE.search(knowledge_query, max_results=2)
        citations = search.get("matches") or []
    markdown = build_reliability_report(
        analysis,
        question=question,
        warranty_hours=warranty_hours,
        knowledge_citations=citations,
    )
    report_path = Path(__file__).parent / "static" / "reliability_report.md"
    report_path.write_text(markdown, encoding="utf-8")
    return {"markdown": markdown, "file": report_path.name, "analysis": analysis}


@mcp.tool()
def search_reliability_knowledge(query: str, max_results: int = 3) -> dict[str, Any]:
    """Hybrid-search local Markdown, text, PDF, Word, and PowerPoint documents."""
    return KNOWLEDGE_BASE.search(query, max_results)


load_plugins(mcp)


if __name__ == "__main__":
    mcp.run(transport="stdio")
