#!/usr/bin/env bash
# One-command development: FastAPI backend (:8000) + Vite dev server (:4200).
# Ctrl+C stops both.
# Usage: ./scripts/dev.sh [--domain physics]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for arg in "$@"; do
  case "$arg" in
    --domain=*) export ACTIVE_DOMAIN="${arg#--domain=}" ;;
    *) echo "Unknown argument: $arg (expected --domain=NAME)" >&2; exit 1 ;;
  esac
done

command -v uv >/dev/null || { echo "uv not found. Install it: https://docs.astral.sh/uv/" >&2; exit 1; }
command -v npm >/dev/null || { echo "npm not found. Install Node LTS first." >&2; exit 1; }
if [ ! -f "$ROOT/.env" ]; then
  echo "WARNING: .env not found at repo root. Copy .env.example to .env and set LLM_API_BASE." >&2
fi

for port in 8000 4200; do
  if (command -v ss >/dev/null && ss -ltn | grep -q ":$port ") || \
     (command -v lsof >/dev/null && lsof -i ":$port" -sTCP:LISTEN -t >/dev/null 2>&1); then
    echo "Port $port is already in use. Stop that process first." >&2
    exit 1
  fi
done

if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "Installing frontend dependencies..."
  (cd "$ROOT/frontend" && npm install)
fi

echo "Starting backend (background) + Vite dev server (foreground)..."
(cd "$ROOT/backend" && uv sync --all-groups && uv run python -m src.host.app) &
BACKEND_PID=$!
trap 'kill $BACKEND_PID 2>/dev/null || true' EXIT INT TERM

(cd "$ROOT/frontend" && npm run dev)
