#!/usr/bin/env bash
# Build the React frontend and copy it into backend/static/ui for FastAPI to serve.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install
fi
npm run build
DEST="$ROOT/backend/static/ui"
mkdir -p "$DEST"
# Clear previous bundle but keep .gitkeep
find "$DEST" -mindepth 1 -maxdepth 1 ! -name '.gitkeep' -exec rm -rf {} +
BROWSER="$ROOT/frontend/dist/frontend/browser"
if [ ! -d "$BROWSER" ]; then
  echo "Build output not found at $BROWSER" >&2
  exit 1
fi
cp -r "$BROWSER"/. "$DEST"/
echo "UI copied to $DEST"
