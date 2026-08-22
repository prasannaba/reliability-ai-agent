"""2-parameter Weibull fitting: ranks, RRY, MLE, bootstrap bounds."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import minimize
from scipy.special import gamma

METHODS = ("rry", "mle")


def b_life(beta: float, eta: float, percentage: float) -> float:
    if beta <= 0 or eta <= 0:
        raise ValueError("beta and eta must be greater than zero")
    if not 0 < percentage < 100:
        raise ValueError("percentage must be between 0 and 100")
    return float(eta * (-np.log1p(-percentage / 100.0)) ** (1.0 / beta))


def mtbf(beta: float, eta: float) -> float:
    return float(eta * gamma(1.0 + 1.0 / beta))


def adjusted_median_ranks(
    failure_times: np.ndarray,
    censored_times: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Herd-Johnson adjusted ranks with Bernard median ranks.

    Returns failure times, median ranks F, and all suspension times.
    """
    failures = np.asarray(failure_times, dtype=float)
    censored = np.asarray(censored_times if censored_times is not None else [], dtype=float)
    if np.any(failures <= 0) or np.any(censored < 0):
        raise ValueError("times must be positive (censoring may be zero)")

    events = [(float(t), 1) for t in failures] + [(float(t), 0) for t in censored]
    events.sort(key=lambda item: (item[0], -item[1]))
    n = len(events)
    if n == 0:
        raise ValueError("no life data provided")

    failure_t: list[float] = []
    failure_f: list[float] = []
    ar_prev = 0.0
    for index, (time, is_failure) in enumerate(events, start=1):
        reverse_rank = n - index + 1
        if not is_failure:
            continue
        adjusted = (reverse_rank * ar_prev + (n + 1)) / (reverse_rank + 1)
        ar_prev = adjusted
        failure_t.append(time)
        failure_f.append((adjusted - 0.3) / (n + 0.4))
    if len(failure_t) < 2:
        raise ValueError("at least two failures are required")
    return np.asarray(failure_t), np.asarray(failure_f), censored


def fit_rry(failure_times: np.ndarray, ranks: np.ndarray) -> tuple[float, float]:
    clipped = np.clip(ranks, 1e-10, 1 - 1e-10)
    y = np.log(np.log(1.0 / (1.0 - clipped)))
    x = np.log(failure_times)
    slope, intercept = np.polyfit(x, y, 1)
    beta = float(slope)
    eta = float(np.exp(-intercept / beta))
    return beta, eta


def fit_mle(failure_times: np.ndarray, censored_times: np.ndarray) -> tuple[float, float]:
    failures = np.asarray(failure_times, dtype=float)
    censored = np.asarray(censored_times, dtype=float)

    def nll(params: np.ndarray) -> float:
        beta, eta = params
        if beta <= 1e-6 or eta <= 1e-6:
            return 1e12
        log_pdf = np.log(beta / eta) + (beta - 1.0) * np.log(failures / eta) - (failures / eta) ** beta
        log_sf = -((censored / eta) ** beta) if len(censored) else 0.0
        return float(-np.sum(log_pdf) - np.sum(log_sf))

    start_beta, start_eta = fit_rry(*adjusted_median_ranks(failures, censored)[:2])
    result = minimize(nll, x0=np.array([start_beta, start_eta]), method="Nelder-Mead")
    if not result.success:
        return start_beta, start_eta
    beta, eta = (float(value) for value in result.x)
    if beta <= 0 or eta <= 0:
        return start_beta, start_eta
    return beta, eta


def fit_weibull(
    failure_times: np.ndarray,
    censored_times: np.ndarray | None = None,
    method: str = "rry",
) -> dict[str, Any]:
    method_name = method.casefold()
    if method_name not in METHODS:
        raise ValueError("method must be 'rry' or 'mle'")
    times, ranks, censored = adjusted_median_ranks(failure_times, censored_times)
    if method_name == "mle":
        beta, eta = fit_mle(times, censored)
    else:
        beta, eta = fit_rry(times, ranks)
    return {
        "beta": beta,
        "eta": eta,
        "mtbf": mtbf(beta, eta),
        "failure_times": times,
        "ranks": ranks,
        "censored_times": censored,
        "method": method_name,
        "n_failures": int(len(times)),
        "n_censored": int(len(censored)),
    }


def bootstrap_bounds(
    failure_times: np.ndarray,
    censored_times: np.ndarray,
    method: str,
    confidence: float = 0.9,
    samples: int = 200,
    seed: int = 42,
) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    failures = np.asarray(failure_times, dtype=float)
    censored = np.asarray(censored_times, dtype=float)
    betas: list[float] = []
    etas: list[float] = []
    for _ in range(samples):
        fail_draw = rng.choice(failures, size=len(failures), replace=True)
        cens_draw = rng.choice(censored, size=len(censored), replace=True) if len(censored) else censored
        try:
            fit = fit_weibull(fail_draw, cens_draw, method=method)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            continue
        if fit["beta"] > 0 and fit["eta"] > 0:
            betas.append(fit["beta"])
            etas.append(fit["eta"])
    if len(betas) < 20:
        return {"available": False, "confidence": confidence, "n_successful": len(betas)}

    alpha = (1.0 - confidence) / 2.0
    lower_q, upper_q = 100 * alpha, 100 * (1.0 - alpha)
    beta_arr = np.asarray(betas)
    eta_arr = np.asarray(etas)
    b10 = np.asarray([b_life(b, e, 10) for b, e in zip(beta_arr, eta_arr)])
    b20 = np.asarray([b_life(b, e, 20) for b, e in zip(beta_arr, eta_arr)])
    return {
        "available": True,
        "confidence": confidence,
        "n_successful": len(betas),
        "bound_method": "bootstrap percentile",
        "beta": (float(np.percentile(beta_arr, lower_q)), float(np.percentile(beta_arr, upper_q))),
        "eta": (float(np.percentile(eta_arr, lower_q)), float(np.percentile(eta_arr, upper_q))),
        "b10": (float(np.percentile(b10, lower_q)), float(np.percentile(b10, upper_q))),
        "b20": (float(np.percentile(b20, lower_q)), float(np.percentile(b20, upper_q))),
        "samples": {"beta": beta_arr, "eta": eta_arr},
    }
