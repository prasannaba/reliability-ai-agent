# Start the FastAPI host (API + UI). Select the domain pack with -Domain.
# Usage: .\scripts\start.ps1 [-Domain physics]
param(
  [string]$Domain = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if ($Domain) {
  $env:ACTIVE_DOMAIN = $Domain
}
Set-Location (Join-Path $root "backend")
uv sync --all-groups
uv run python -m src.host.app
