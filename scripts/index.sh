#!/usr/bin/env bash
# Build or refresh the knowledge index for a domain pack.
# Usage: ./scripts/index.sh [reliability] [--download-model] [--force]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${1:-reliability}"
shift || true

command -v uv >/dev/null || { echo "uv not found. Install it: https://docs.astral.sh/uv/" >&2; exit 1; }

cd "$ROOT/backend"
uv sync --all-groups
uv run python -m src.knowledge.base --domain "$DOMAIN" "$@"
