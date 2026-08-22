import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from main import infer_latest_image_url


def test_infer_latest_image_url_prefers_latest_generated_file(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    old_path = static_dir / "weibull_plot.png"
    old_path.write_bytes(b"old")
    newer_path = static_dir / "weibull_plot_2.png"
    newer_path.write_bytes(b"new")
    old_path.touch()
    newer_path.touch()

    # make sure the newer path is detected if the content mentions it
    response_content = "Here is the latest figure: weibull_plot_2.png"

    image_url = infer_latest_image_url(response_content, static_dir, base_url="")
    assert image_url == "/static/weibull_plot_2.png"


def test_infer_latest_image_url_falls_back_to_default_filename(tmp_path):
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    plot_path = static_dir / "weibull_plot.png"
    plot_path.write_bytes(b"plot")

    response_content = "Please see weibull_plot.png"
    image_url = infer_latest_image_url(response_content, static_dir, base_url="")
    assert image_url == "/static/weibull_plot.png"
