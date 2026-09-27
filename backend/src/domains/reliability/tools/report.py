"""One-page reliability report (plain function; registered in server.py)."""

from __future__ import annotations

from typing import Any

from src.domains.reliability.reliability_report import build_reliability_report
from src.domains.reliability.tools._common import STATIC_DIR
from src.domains.reliability.tools.knowledge_tool import knowledge_base
from src.domains.reliability.tools.weibull import analyze_weibull


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
        search = knowledge_base().search(knowledge_query, max_results=2)
        citations = search.get("matches") or []
    markdown = build_reliability_report(
        analysis,
        question=question,
        warranty_hours=warranty_hours,
        knowledge_citations=citations,
    )
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    report_path = STATIC_DIR / "reliability_report.md"
    report_path.write_text(markdown, encoding="utf-8")
    return {"markdown": markdown, "file": report_path.name, "analysis": analysis}
