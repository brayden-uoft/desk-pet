param(
    [ValidateRange(1, 20)]
    [int]$Turns = 5,
    [switch]$NoPlayback,
    [string]$Audio = "data/private/voice-fixtures/brayden-latency.wav"
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
    $Arguments = @(
        "-m", "desk_pet.realtime_replay",
        "--config", "configs/windows.yaml",
        "--audio", $Audio,
        "--turns", $Turns
    )
    if ($NoPlayback) { $Arguments += "--no-playback" }
    & $VenvPython @Arguments
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
