param(
    [string]$Prompt = "Say hello in one sentence.",
    [string]$Name = "brayden-latency"
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
    $AudioPath = "data/private/voice-fixtures/$Name.wav"
    & $VenvPython -m desk_pet.voice_replay record `
        --config "configs/windows.yaml" `
        --audio $AudioPath `
        --prompt $Prompt
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
