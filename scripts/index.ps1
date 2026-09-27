# Build or refresh the knowledge index for a domain pack.
# Usage: .\scripts\index.ps1 [-Domain reliability] [-DownloadModel] [-Force]
param(
  [string]$Domain = "reliability",
  [switch]$DownloadModel,
  [switch]$Force
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
  throw "uv not found. Install it: https://docs.astral.sh/uv/"
}

Set-Location (Join-Path $root "backend")
uv sync --all-groups
$indexArgs = @("--domain", $Domain)
if ($DownloadModel) { $indexArgs += "--download-model" }
if ($Force) { $indexArgs += "--force" }
uv run python -m src.knowledge.base @indexArgs
