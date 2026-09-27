# One-command production-like run: single FastAPI process serves API + UI at
# http://localhost:8000. Builds the UI first unless it is already present.
# Usage: .\scripts\run.ps1 [--skip-build] [--rebuild] [-Domain physics]
param(
  [switch]$skipBuild,
  [switch]$rebuild,
  [string]$Domain = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if ($Domain) {
  # Select the domain pack (reliability default) without code changes.
  $env:ACTIVE_DOMAIN = $Domain
}

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
  throw "uv not found. Install it: https://docs.astral.sh/uv/"
}
if (-not (Test-Path (Join-Path $root ".env"))) {
  Write-Warning ".env not found at repo root. Copy .env.example to .env and set LLM_API_BASE."
}

$ui = Join-Path $root "backend\static\ui\index.html"
if ($rebuild -or ((-not $skipBuild) -and (-not (Test-Path $ui)))) {
  Write-Host "Building UI..."
  & (Join-Path $PSScriptRoot "build_ui.ps1")
}
elseif (-not (Test-Path $ui)) {
  Write-Warning "UI not built (backend will report 'ui: not built'). Run scripts\build_ui.ps1 to add it."
}

Set-Location (Join-Path $root "backend")
uv sync --all-groups
uv run python -m src.host.app
