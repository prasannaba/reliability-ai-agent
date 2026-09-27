"""Mean time between failures from observed times-to-failure."""

from __future__ import annotations

from typing import Any

import numpy as np


def register(mcp: Any) -> None:
    @mcp.tool()
    def calculate_mtbf(
        failure_times: list[float], censored_times: list[float] | None = None
    ) -> dict[str, float]:
        """Estimate MTBF from failure times and optional right-censored run times."""
        if not failure_times:
            raise ValueError("at least one failure time is required")
        if any(value <= 0 for value in failure_times):
            raise ValueError("failure times must be greater than zero")
        censored = censored_times or []
        if any(value < 0 for value in censored):
            raise ValueError("censored times must be zero or greater")

        failures = np.asarray(failure_times, dtype=float)
        total_time = float(failures.sum() + np.asarray(censored, dtype=float).sum())
        count = float(len(failures))
        mtbf = total_time / count
        return {
            "mtbf": mtbf,
            "failure_count": count,
            "total_time": total_time,
            "failure_rate": 1.0 / mtbf,
        }
