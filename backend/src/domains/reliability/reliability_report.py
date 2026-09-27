"""One-page reliability report: numbers from tools, not from the LLM."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _fmt_interval(bounds: tuple[float, float] | list[float] | None, digits: int = 2) -> str:
    if not bounds:
        return "n/a"
    low, high = bounds
    return f"{low:.{digits}f} – {high:.{digits}f}"


def build_reliability_report(
    analysis: dict[str, Any],
    *,
    question: str = "",
    warranty_hours: float | None = None,
    knowledge_citations: list[dict[str, Any]] | None = None,
) -> str:
    method = "MLE" if analysis.get("method") == "mle" else "median ranks + RRY"
    bounds = analysis.get("bounds") or {}
    n_fail = analysis.get("n_failures")
    n_cens = analysis.get("n_censored", 0)
    plot_name = Path(str(analysis.get("file") or "")).name
    lines = [
        "# Reliability analysis report",
        "",
        "Computed by MCP tools (Weibull fit, B-life). The language model does not invent life metrics.",
        "",
    ]
    if question:
        lines.extend(["## Question", "", question, ""])
    lines.extend(
        [
            "## Sample",
            "",
            f"- Failures: {n_fail}",
            f"- Suspensions (right-censored): {n_cens}",
            f"- Fit method: {method}",
            "",
            "## Estimates",
            "",
            f"- Shape β: {float(analysis['beta']):.3f}",
            f"- Scale η: {float(analysis['eta']):.2f} hours",
            f"- MTBF: {float(analysis['mtbf']):.2f} hours",
            f"- B10: {float(analysis['b10']):.1f} hours",
            f"- B20: {float(analysis['b20']):.1f} hours",
            f"- B30: {float(analysis['b30']):.1f} hours",
            "",
        ]
    )
    if bounds:
        conf = int(float(bounds.get("confidence", 0.9)) * 100)
        lines.extend(
            [
                f"## {conf}% bootstrap percentile bounds",
                "",
                f"- Method: {bounds.get('method', 'bootstrap percentile')}",
                f"- β: {_fmt_interval(bounds.get('beta'), 3)}",
                f"- η (hours): {_fmt_interval(bounds.get('eta'))}",
                f"- B10 (hours): {_fmt_interval(bounds.get('b10'), 1)}",
                f"- B20 (hours): {_fmt_interval(bounds.get('b20'), 1)}",
                "",
            ]
        )
    if warranty_hours is not None:
        b10 = float(analysis["b10"])
        cover = "covers" if b10 >= warranty_hours else "does not cover"
        lines.extend(
            [
                "## Warranty check",
                "",
                f"B10 is {b10:.1f} h versus a {warranty_hours:g} h warranty — B10 **{cover}** the warranty period on the point estimate.",
                "",
            ]
        )
    if plot_name:
        lines.extend(["## Plot", "", f"![Weibull paper]({plot_name})", ""])
    if knowledge_citations:
        lines.extend(["## Knowledge-base citations", ""])
        for item in knowledge_citations:
            source = item.get("source", "document")
            snippet = str(item.get("content") or item.get("section") or "").strip().splitlines()
            preview = snippet[0][:200] if snippet else ""
            lines.append(f"- `{source}`: {preview}")
        lines.append("")
    lines.extend(
        [
            "## Notes",
            "",
            "- This copilot complements commercial solvers (e.g. ReliaSoft Weibull++) via MCP later; it is not a replacement for ALT, Weibayes, or competing-risks analysis.",
            f"- Informal K-S on failures: statistic={analysis.get('ks_stat')}, p={analysis.get('p_value')}.",
        ]
    )
    return "\n".join(lines)
