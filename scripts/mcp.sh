#!/usr/bin/env bash
# Serve one domain MCP server standalone (no FastAPI needed).
#   stdio            — local MCP clients (spawned process)
#   streamable-http  — Open Web UI, Unsloth Studio, ... at http://<host>:<port>/mcp
# Usage: ./scripts/mcp.sh [reliability] [streamable-http] [8001]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${1:-reliability}"
TRANSPORT="${2:-streamable-http}"

case "$DOMAIN" in
  reliability) DEFAULT_PORT=8001 ;;
  physics) DEFAULT_PORT=8002 ;;
  *) DEFAULT_PORT=8001 ;;
esac
PORT="${3:-$DEFAULT_PORT}"

command -v uv >/dev/null || { echo "uv not found. Install it: https://docs.astral.sh/uv/" >&2; exit 1; }

cd "$ROOT/backend"
uv sync --all-groups
uv run python -m "src.domains.${DOMAIN}.server" --transport "$TRANSPORT" --port "$PORT"
