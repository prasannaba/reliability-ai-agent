import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from reliability_report import build_reliability_report


def test_report_mentions_tools_and_not_reliasoft_replacement():
    markdown = build_reliability_report(
        {
            "beta": 2.0,
            "eta": 1000.0,
            "mtbf": 886.2,
            "b10": 325.0,
            "b20": 472.0,
            "b30": 588.0,
            "method": "rry",
            "n_failures": 8,
            "n_censored": 3,
            "file": "weibull_plot_1.png",
            "ks_stat": 0.1,
            "p_value": 0.5,
            "bounds": {
                "confidence": 0.9,
                "method": "bootstrap percentile",
                "b10": (200.0, 400.0),
                "b20": (300.0, 500.0),
                "beta": (1.5, 2.5),
                "eta": (800.0, 1200.0),
            },
        },
        question="Does B10 cover 200 h?",
        warranty_hours=200,
    )
    assert "Computed by MCP tools" in markdown
    assert "not a replacement" in markdown
    assert "325.0" in markdown
