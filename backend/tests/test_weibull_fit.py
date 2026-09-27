import sys
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.domains.reliability.weibull_fit import adjusted_median_ranks, b_life, fit_weibull, mtbf


def test_bernard_ranks_without_censoring_match_classic_formula():
    times, ranks, censored = adjusted_median_ranks([10.0, 20.0, 30.0])
    assert list(np.round(times, 1)) == [10.0, 20.0, 30.0]
    assert len(censored) == 0
    expected = (np.arange(1, 4) - 0.3) / (3 + 0.4)
    np.testing.assert_allclose(ranks, expected)


def test_suspensions_do_not_count_as_failures():
    times, ranks, censored = adjusted_median_ranks([10.0, 30.0], censored_times=[20.0, 40.0])
    assert len(times) == 2
    assert len(censored) == 2
    assert ranks[0] < ranks[1]


def test_rry_recovers_order_of_magnitude():
    fit = fit_weibull(np.array([100.0, 200.0, 300.0, 400.0, 500.0]), method="rry")
    assert fit["beta"] > 0.5
    assert 150 < fit["eta"] < 600
    assert fit["mtbf"] == mtbf(fit["beta"], fit["eta"])
    assert b_life(fit["beta"], fit["eta"], 10) < fit["eta"]


def test_mle_accepts_censoring():
    fit = fit_weibull(
        np.array([100.0, 180.0, 250.0, 400.0]),
        censored_times=np.array([500.0, 500.0]),
        method="mle",
    )
    assert fit["n_failures"] == 4
    assert fit["n_censored"] == 2
    assert fit["beta"] > 0
    assert fit["eta"] > 0
