param(
    [ValidateRange(1, 20)]
    [int]$Turns = 1
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Run .\scripts\run_windows.ps1 once to create the environment."
    exit 2
}

Push-Location $RepoRoot
try {
    & $VenvPython -m desk_pet.voice_replay replay --config "configs/windows.yaml" --turns $Turns
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
