#!/usr/bin/env bash
# Start the FastAPI backend (serves API + production UI at http://localhost:8000).
# Select the domain pack with --domain (default: reliability).
# Usage: ./scripts/start.sh [--domain physics]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for arg in "$@"; do
  case "$arg" in
    --domain=*) export ACTIVE_DOMAIN="${arg#--domain=}" ;;
    *) echo "Unknown argument: $arg (expected --domain=NAME)" >&2; exit 1 ;;
  esac
done
cd "$ROOT/backend"
uv sync --all-groups
uv run python -m src.host.app
