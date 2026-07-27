$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython)) {
    Write-Host "Creating Desk Pet virtual environment..."
    python -m venv (Join-Path $RepoRoot ".venv")
}

& $VenvPython -m pip install --quiet --editable "$RepoRoot[dev]"
& $VenvPython -m ruff check $RepoRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m ruff format --check $RepoRoot
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m mypy (Join-Path $RepoRoot "src") (Join-Path $RepoRoot "tests")
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $VenvPython -m pytest
exit $LASTEXITCODE

