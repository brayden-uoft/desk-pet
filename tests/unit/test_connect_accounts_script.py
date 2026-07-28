from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "connect_accounts.ps1"


def _dry_run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-File",
            str(SCRIPT),
            "-DryRun",
            "-SkipInstall",
            *arguments,
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_single_provider_is_not_split_into_characters() -> None:
    result = _dry_run("-Provider", "notion")

    assert result.returncode == 0, result.stderr
    assert "desk_pet.auth.wizard notion --no-status" in result.stdout
    assert "desk_pet.auth.wizard n " not in result.stdout


def test_all_provider_dry_run_routes_account_only_to_multi_account_services() -> None:
    result = _dry_run(
        "-Account",
        "test",
        "-MicrosoftAccountType",
        "personal",
    )

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.startswith("DRY RUN:")]
    assert len(lines) == 6
    assert "github --no-status --account" not in result.stdout
    assert "notion --no-status --account" not in result.stdout
    assert "slack --no-status --account" not in result.stdout
    assert "dropbox --no-status --account" not in result.stdout
    assert (
        "microsoft --no-status --account test --microsoft-account-type personal"
        in result.stdout
    )
    assert "google --no-status --account test" in result.stdout


def test_disconnect_named_account_routes_to_wizard() -> None:
    result = _dry_run(
        "-Provider",
        "google",
        "-Account",
        "personal",
        "-Disconnect",
    )

    assert result.returncode == 0, result.stderr
    assert (
        "desk_pet.auth.wizard --disconnect google --account personal"
        in result.stdout
    )
