$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location "$root\frontend"
if (-not (Test-Path "node_modules")) {
    npm install
}
npm run build
$dest = "$root\backend\static\ui"
if (Test-Path $dest) {
    Get-ChildItem $dest -Force | Where-Object { $_.Name -ne ".gitkeep" } | Remove-Item -Recurse -Force
}
$browser = "$root\frontend\dist\frontend\browser"
if (-not (Test-Path $browser)) {
    throw "Angular build output not found at $browser"
}
Copy-Item "$browser\*" $dest -Recurse -Force
Write-Host "UI copied to $dest"
