#!/usr/bin/env bash
# Open the Reliability Copilot UI in a local WebView window (pywebview).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
uv sync --all-groups
uv run python desktop_app.py
