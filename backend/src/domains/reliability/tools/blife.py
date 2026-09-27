"""Weibull B-life computation (plain function; registered in server.py)."""

from __future__ import annotations

from src.domains.reliability.weibull_fit import b_life


def calculate_b_life(beta: float, eta: float, percentage: float) -> int:
    """Calculate Weibull B-life for a failure percentile between 0 and 100."""
    return int(round(b_life(beta, eta, percentage)))
