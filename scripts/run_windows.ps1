$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating Desk Pet virtual environment..."
    python -m venv (Join-Path $RepoRoot ".venv")
}

& $VenvPython -m pip install --quiet --editable $RepoRoot
& $VenvPython -m desk_pet --config (Join-Path $RepoRoot "configs\windows.yaml")
exit $LASTEXITCODE

