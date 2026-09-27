# Serve one domain MCP server standalone (no FastAPI needed).
#   stdio            - local MCP clients (spawned process)
#   streamable-http  - Open Web UI, Unsloth Studio, ... at http://<host>:<port>/mcp
# Usage: .\scripts\mcp.ps1 [-Domain reliability] [-Transport streamable-http] [-Port 0]
param(
  [string]$Domain = "reliability",
  [ValidateSet("stdio", "sse", "streamable-http")][string]$Transport = "streamable-http",
  [int]$Port = 0
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Get-Command "uv" -ErrorAction SilentlyContinue)) {
  throw "uv not found. Install it: https://docs.astral.sh/uv/"
}

$defaultPorts = @{ reliability = 8001; physics = 8002 }
if ($Port -eq 0) {
  $Port = if ($defaultPorts.ContainsKey($Domain)) { $defaultPorts[$Domain] } else { 8001 }
}

Set-Location (Join-Path $root "backend")
uv sync --all-groups
uv run python -m "src.domains.$Domain.server" --transport $Transport --port $Port
