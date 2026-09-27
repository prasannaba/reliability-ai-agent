#!/usr/bin/env bash
# One-command production-like run: single FastAPI process serves API + UI at
# http://localhost:8000. Builds the UI first unless it is already present.
# Usage: ./scripts/run.sh [--skip-build] [--rebuild] [--domain physics]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKIP_BUILD=0
REBUILD=0
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=1 ;;
    --rebuild) REBUILD=1 ;;
    --domain=*) export ACTIVE_DOMAIN="${arg#--domain=}" ;;
    *) echo "Unknown argument: $arg (expected --skip-build, --rebuild, --domain=NAME)" >&2; exit 1 ;;
  esac
done

command -v uv >/dev/null || { echo "uv not found. Install it: https://docs.astral.sh/uv/" >&2; exit 1; }
if [ ! -f "$ROOT/.env" ]; then
  echo "WARNING: .env not found at repo root. Copy .env.example to .env and set LLM_API_BASE." >&2
fi

if [ "$REBUILD" = 1 ] || { [ "$SKIP_BUILD" = 0 ] && [ ! -f "$ROOT/backend/static/ui/index.html" ]; }; then
  echo "Building UI..."
  "$ROOT/scripts/build_ui.sh"
elif [ ! -f "$ROOT/backend/static/ui/index.html" ]; then
  echo "WARNING: UI not built (backend will report 'ui: not built'). Run scripts/build_ui.sh to add it." >&2
fi

cd "$ROOT/backend"
uv sync --all-groups
uv run python -m src.host.app
