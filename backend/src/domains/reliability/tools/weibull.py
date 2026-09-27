"""Weibull probability-paper fitting (plain function; registered in server.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from src.domains.reliability.life_data_analysis_weibull import plot_weibull_analysis
from src.domains.reliability.tools._common import PLOT_LOCK, json_safe


def analyze_weibull(
    failure_times: list[float],
    title: str = "Weibull Probability Plot",
    censored_times: list[float] | None = None,
    method: str = "rry",
    confidence: float = 0.9,
) -> dict[str, Any]:
    """Fit 2-parameter Weibull data, plot probability paper, return statistics.

    Use censored_times for right-censored suspensions. method is 'rry' (default,
    median ranks + rank regression on Y) or 'mle'. confidence is the two-sided
    bootstrap interval on the line and on B10/B20 (for example 0.9).
    """
    if len(failure_times) < 2:
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
    normalized = {key: json_safe(value) for key, value in result.items()}
    plot_path = Path(normalized["file"])
    normalized["file"] = plot_path.name
    normalized["message"] = f"Weibull plot saved as {plot_path.name}"
    return normalized
