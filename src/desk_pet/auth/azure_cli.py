from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from desk_pet.auth.models import OAuthClientRegistration
from desk_pet.auth.store import CredentialStore, KeyringCredentialStore

CONSUMER_TENANT_ID = "9188040d-6c67-4c5b-b112-36a304b66dad"


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class AzureCommandRunner(Protocol):
    def run(self, arguments: Sequence[str], *, capture: bool = False) -> CommandResult: ...


class SubprocessAzureCommandRunner:
    def __init__(self, executable: Path) -> None:
        self._executable = executable

    def run(self, arguments: Sequence[str], *, capture: bool = False) -> CommandResult:
        command = [str(self._executable), *arguments]
        if self._executable.suffix.casefold() in {".cmd", ".bat"}:
            command = [
                os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
                "/d",
                "/s",
                "/c",
                "call",
                *command,
            ]
        completed = subprocess.run(
            command,
            check=False,
            capture_output=capture,
            text=True,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )


class MicrosoftBootstrapError(RuntimeError):
    """Microsoft app registration could not be completed."""


def bootstrap_microsoft_client(
    runner: AzureCommandRunner,
    store: CredentialStore,
) -> OAuthClientRegistration:
    runner.run(("account", "clear"))
    configured = runner.run(
        (
            "config",
            "set",
            "core.enable_broker_on_windows=false",
            "core.login_experience_v2=off",
        )
    )
    if configured.returncode != 0:
        raise MicrosoftBootstrapError(
            "Azure CLI could not enable browser-login compatibility mode."
        )

    login = runner.run(("login", "--allow-no-subscriptions"))
    if login.returncode != 0:
        print(
            "Browser login failed. Retrying with Microsoft's device-code flow.",
            file=sys.stderr,
        )
        runner.run(("account", "clear"))
        login = runner.run(("login", "--allow-no-subscriptions", "--use-device-code"))
    if login.returncode != 0:
        raise MicrosoftBootstrapError(
            "Microsoft sign-in failed in both browser and device-code modes."
        )

    tenant = runner.run(
        ("account", "show", "--query", "tenantId", "--output", "tsv"),
        capture=True,
    )
    tenant_id = tenant.stdout.strip()
    if tenant.returncode != 0 or not tenant_id:
        raise MicrosoftBootstrapError(
            "Sign-in succeeded, but this account has no accessible Microsoft Entra tenant. "
            "A consumer Outlook/Hotmail account cannot register DeskBob by itself. Supply a "
            "DeskBob Application (client) ID created in an Entra tenant."
        )
    if tenant_id.casefold() == CONSUMER_TENANT_ID:
        raise MicrosoftBootstrapError(
            "This is Microsoft's consumer account directory, which cannot own a DeskBob app "
            "registration. Supply a DeskBob Application (client) ID created in an Entra tenant."
        )

    created = runner.run(
        (
            "ad",
            "app",
            "create",
            "--display-name",
            "DeskBob Local",
            "--sign-in-audience",
            "AzureADandPersonalMicrosoftAccount",
            "--is-fallback-public-client",
            "true",
            "--public-client-redirect-uris",
            "http://localhost",
            "--query",
            "appId",
            "--output",
            "tsv",
            "--only-show-errors",
        ),
        capture=True,
    )
    client_id = created.stdout.strip()
    if created.returncode != 0 or not client_id:
        error = f"{created.stderr}\n{created.stdout}".casefold()
        if "insufficient privileges" in error or "directory permission" in error:
            raise MicrosoftBootstrapError(
                "The signed-in Entra tenant forbids you from registering applications. "
                "Ask an administrator for the Application Developer role, or ask them to "
                "create the DeskBob public-client app and provide its Application (client) ID."
            )
        raise MicrosoftBootstrapError(
            "Azure CLI failed to create the DeskBob app registration. "
            "Run the wizard again with -ClientId if an administrator creates it manually."
        )

    registration = OAuthClientRegistration("microsoft", client_id)
    store.save_client(registration)
    return registration


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap DeskBob's Microsoft OAuth app.")
    parser.add_argument("--az", type=Path, required=True, help="Path to az.cmd or az.exe.")
    return parser


def run(
    argv: Sequence[str] | None = None,
    *,
    store: CredentialStore | None = None,
    runner: AzureCommandRunner | None = None,
) -> int:
    args = _parser().parse_args(argv)
    command_runner = runner or SubprocessAzureCommandRunner(args.az)
    credentials = store or KeyringCredentialStore()
    try:
        registration = bootstrap_microsoft_client(command_runner, credentials)
    except MicrosoftBootstrapError as exc:
        print(f"Microsoft OAuth app setup blocked: {exc}", file=sys.stderr)
        return 2
    print(
        f"[OK] Microsoft OAuth app registered and saved securely ({registration.client_id[:8]}...)."
    )
    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
