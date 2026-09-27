"""Open the Reliability Agent UI in a local WebView2 (Windows) or WebKit window."""

from __future__ import annotations

import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from src.host.app import app

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

HOST = os.getenv("DESKTOP_HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", "8000"))
URL = f"http://{HOST}:{PORT}"


def _serve() -> None:
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")


def _wait_until_ready(timeout_seconds: float = 60.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{URL}/health", timeout=1) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(0.25)
    raise RuntimeError(f"Backend did not become ready at {URL}")


def main() -> None:
    import webview

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    _wait_until_ready()
    webview.create_window("Reliability AI Agent", URL, width=1200, height=800)
    webview.start()


if __name__ == "__main__":
    main()
