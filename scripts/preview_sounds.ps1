$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Run .\scripts\run_windows.ps1 once to create the environment."
    exit 2
}

& $VenvPython -m desk_pet.audio.preview_demo
exit $LASTEXITCODE
