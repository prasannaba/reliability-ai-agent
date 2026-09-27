# One-command development: FastAPI backend (:8000) + Vite dev server (:4200).
# Ctrl+C stops both. Run from anywhere: .\scripts\dev.ps1 [-Domain physics]
param(
  [string]$Domain = ""
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

function Test-Command($name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "uv")) { throw "uv not found. Install it: https://docs.astral.sh/uv/" }
if (-not (Test-Command "npm")) { throw "npm not found. Install Node LTS first." }
if (-not (Test-Path (Join-Path $root ".env"))) {
  Write-Warning ".env not found at repo root. Copy .env.example to .env and set LLM_API_BASE."
}

# Fail fast if the ports are already taken.
foreach ($port in 8000, 4200) {
  $busy = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
  if ($busy) { throw "Port $port is already in use. Stop that process first." }
}

if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
  Write-Host "Installing frontend dependencies..."
  Push-Location (Join-Path $root "frontend")
  npm install
  Pop-Location
}

Write-Host "Starting backend (background) + Vite dev server (foreground)..."
$backend = Start-Job -Name "reliability-backend" -WorkingDirectory (Join-Path $root "backend") -ArgumentList $Domain -ScriptBlock {
  param([string]$JobDomain)
  if ($JobDomain) {
    $env:ACTIVE_DOMAIN = $JobDomain
  }
  uv sync --all-groups
  uv run python -m src.host.app
}
try {
  Push-Location (Join-Path $root "frontend")
  npm run dev
}
finally {
  Pop-Location
  Write-Host "Stopping backend..."
  Stop-Job $backend | Out-Null
  Remove-Job $backend | Out-Null
}
