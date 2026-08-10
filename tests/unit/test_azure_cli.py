from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from desk_pet.auth.azure_cli import (
    CONSUMER_TENANT_ID,
    AzureCommandRunner,
    CommandResult,
    MicrosoftBootstrapError,
    SubprocessAzureCommandRunner,
    bootstrap_microsoft_client,
)
from desk_pet.auth.store import MemoryCredentialStore


class FakeAzureRunner(AzureCommandRunner):
    def __init__(self, results: Sequence[CommandResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[tuple[str, ...], bool]] = []

    def run(self, arguments: Sequence[str], *, capture: bool = False) -> CommandResult:
        self.calls.append((tuple(arguments), capture))
        if not self.results:
            raise AssertionError(f"Unexpected Azure CLI call: {arguments}")
        return self.results.pop(0)


def test_bootstrap_registers_and_saves_public_client() -> None:
    runner = FakeAzureRunner(
        [
            CommandResult(0),
            CommandResult(0),
            CommandResult(0),
            CommandResult(0, stdout="tenant-id\n"),
            CommandResult(0, stdout="client-id\n"),
        ]
    )
    store = MemoryCredentialStore()

    registration = bootstrap_microsoft_client(runner, store)

    assert registration.client_id == "client-id"
    assert store.load_client("microsoft") == registration
    assert runner.calls[-1][0][:4] == ("ad", "app", "create", "--display-name")
    assert "--only-show-errors" in runner.calls[-1][0]


def test_bootstrap_falls_back_to_device_code_after_browser_failure() -> None:
    runner = FakeAzureRunner(
        [
            CommandResult(0),
            CommandResult(0),
            CommandResult(1),
            CommandResult(0),
            CommandResult(0),
            CommandResult(0, stdout="tenant-id\n"),
            CommandResult(0, stdout="client-id\n"),
        ]
    )

    bootstrap_microsoft_client(runner, MemoryCredentialStore())

    assert (
        ("login", "--allow-no-subscriptions", "--use-device-code"),
        False,
    ) in runner.calls


def test_bootstrap_rejects_personal_account_without_entra_tenant() -> None:
    runner = FakeAzureRunner(
        [
            CommandResult(0),
            CommandResult(0),
            CommandResult(0),
            CommandResult(1, stderr="Please run az login"),
        ]
    )

    with pytest.raises(MicrosoftBootstrapError, match="no accessible Microsoft Entra tenant"):
        bootstrap_microsoft_client(runner, MemoryCredentialStore())


def test_bootstrap_rejects_consumer_directory() -> None:
    runner = FakeAzureRunner(
        [
            CommandResult(0),
            CommandResult(0),
            CommandResult(0),
            CommandResult(0, stdout=f"{CONSUMER_TENANT_ID}\n"),
        ]
    )

    with pytest.raises(MicrosoftBootstrapError, match="consumer account directory"):
        bootstrap_microsoft_client(runner, MemoryCredentialStore())


def test_bootstrap_reports_real_tenant_permission_denial() -> None:
    runner = FakeAzureRunner(
        [
            CommandResult(0),
            CommandResult(0),
            CommandResult(0),
            CommandResult(0, stdout="tenant-id\n"),
            CommandResult(1, stderr="Insufficient privileges to complete the operation"),
        ]
    )

    with pytest.raises(MicrosoftBootstrapError, match="Application Developer"):
        bootstrap_microsoft_client(runner, MemoryCredentialStore())


def test_bootstrap_reports_unknown_app_creation_failure_without_claiming_permission() -> None:
    runner = FakeAzureRunner(
        [
            CommandResult(0),
            CommandResult(0),
            CommandResult(0),
            CommandResult(0, stdout="tenant-id\n"),
            CommandResult(1, stderr="network unavailable"),
        ]
    )

    with pytest.raises(MicrosoftBootstrapError, match="failed to create"):
        bootstrap_microsoft_client(runner, MemoryCredentialStore())


def test_windows_cmd_launcher_uses_command_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[list[str]] = []

    def fake_run(command: list[str], **_kwargs: object) -> CompletedProcess[str]:
        captured.append(command)
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    monkeypatch.setattr("desk_pet.auth.azure_cli.subprocess.run", fake_run)

    result = SubprocessAzureCommandRunner(Path(r"C:\Program Files\Azure\az.cmd")).run(
        ("account", "show"),
        capture=True,
    )

    assert result.returncode == 0
    assert captured == [
        [
            r"C:\Windows\System32\cmd.exe",
            "/d",
            "/s",
            "/c",
            "call",
            r"C:\Program Files\Azure\az.cmd",
            "account",
            "show",
        ]
    ]
