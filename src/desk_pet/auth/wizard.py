from __future__ import annotations

import argparse
import dataclasses
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from dotenv import load_dotenv

from desk_pet.auth.http import UrllibOAuthHTTPClient
from desk_pet.auth.models import OAuthClient, OAuthClientRegistration, OAuthSession
from desk_pet.auth.oauth import LoopbackAuthorizationBrowser, OAuthFlowError, OAuthManager
from desk_pet.auth.providers import (
    PROVIDER_REGISTRATIONS,
    dropbox_client,
    google_client,
    microsoft_client,
    register_notion_client,
    slack_client,
)
from desk_pet.auth.store import CredentialStore, CredentialStoreError, KeyringCredentialStore

PROVIDERS = ("github", "google", "microsoft", "notion", "slack", "dropbox")
MULTI_ACCOUNT_PROVIDERS = frozenset({"google", "microsoft"})
ACCOUNT_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
FACTORIES: dict[
    str,
    Callable[[Mapping[str, str] | None, OAuthClientRegistration | None], OAuthClient],
] = {
    "google": google_client,
    "microsoft": microsoft_client,
    "slack": slack_client,
    "dropbox": dropbox_client,
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Connect DeskBob accounts using browser-based OAuth."
    )
    parser.add_argument(
        "providers",
        nargs="*",
        choices=PROVIDERS,
        help="Providers to connect. The default is every provider.",
    )
    parser.add_argument("--status", action="store_true", help="Show connection status.")
    parser.add_argument(
        "--account",
        help="Short account label for Google or Microsoft, such as personal or uoft.",
    )
    parser.add_argument(
        "--disconnect",
        choices=PROVIDERS,
        help="Remove a provider's saved OAuth session.",
    )
    parser.add_argument(
        "--import-google-client",
        type=Path,
        metavar="JSON",
        help="Import a Google desktop OAuth client JSON download.",
    )
    parser.add_argument(
        "--save-client",
        nargs=2,
        metavar=("PROVIDER", "CLIENT_ID"),
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--client-secret", help=argparse.SUPPRESS)
    return parser


def _save_google_client(path: Path, store: CredentialStore) -> None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        installed = value["installed"]
        client_id = installed["client_id"]
        client_secret = installed.get("client_secret")
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise OAuthFlowError("That is not a Google Desktop app OAuth client JSON file.") from exc
    if not isinstance(client_id, str) or not client_id:
        raise OAuthFlowError("The Google client JSON has no client_id.")
    store.save_client(
        OAuthClientRegistration(
            provider="google",
            client_id=client_id,
            client_secret=client_secret if isinstance(client_secret, str) else None,
        )
    )


def _registration_from_environment(
    provider: str,
    environment: Mapping[str, str],
) -> OAuthClientRegistration | None:
    spec = next(item for item in PROVIDER_REGISTRATIONS if item.provider == provider)
    client_id = environment.get(spec.client_id_environment_variable, "").strip()
    if not client_id:
        return None
    client_secret = (
        environment.get(spec.client_secret_environment_variable, "").strip() or None
        if spec.client_secret_environment_variable
        else None
    )
    return OAuthClientRegistration(provider, client_id, client_secret)


def _load_registration(
    provider: str,
    store: CredentialStore,
    environment: Mapping[str, str],
) -> OAuthClientRegistration | None:
    return store.load_client(provider) or _registration_from_environment(provider, environment)


def _show_status(store: CredentialStore, environment: Mapping[str, str]) -> None:
    print("\nDeskBob account status")
    print("----------------------")
    for provider in PROVIDERS:
        sessions = store.list_sessions(provider)
        if sessions:
            for session in sessions:
                account = _account_from_session_key(provider, session.provider)
                display = provider if account is None else f"{provider}:{account}"
                print(f"{display:24} connected")
            continue
        if provider in {"github", "notion"}:
            registration = True
        else:
            registration = _load_registration(provider, store, environment) is not None
        detail = "ready to sign in" if registration else "needs one-time OAuth app setup"
        print(f"{provider:24} {detail}")


def _connect_provider(
    provider: str,
    store: CredentialStore,
    manager: OAuthManager,
    http: UrllibOAuthHTTPClient,
    environment: Mapping[str, str],
    account: str | None,
) -> bool:
    if provider == "github":
        return _connect_github_cli(store)
    fixed_ports = {"slack": 53682, "dropbox": 53683}
    browser = LoopbackAuthorizationBrowser(port=fixed_ports.get(provider, 0))
    server_url: str | None
    if provider == "notion":
        client = register_notion_client(http, browser)
        server_url = "https://mcp.notion.com/mcp"
    else:
        registration = _load_registration(provider, store, environment)
        if registration is None:
            spec = next(item for item in PROVIDER_REGISTRATIONS if item.provider == provider)
            print(f"\n{provider.title()} needs a one-time OAuth app registration.")
            print(f"Setup page: {spec.setup_url}")
            return False
        client = FACTORIES[provider](environment, registration)
        if account is not None:
            client = dataclasses.replace(client, provider=f"{provider}:{account}")
        server_url = "https://mcp.slack.com/mcp" if provider == "slack" else None
    display = provider.title() if account is None else f"{provider.title()} [{account}]"
    print(f"\nOpening {display} sign-in...")
    manager.connect(client, browser, server_url=server_url)
    print(f"[OK] {display} connected. Tokens are in Windows Credential Manager.")
    return True


def _connect_github_cli(store: CredentialStore) -> bool:
    existing = store.load("github")
    if existing is not None:
        print("\n[OK] GitHub is already connected.")
        return True
    program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
    gh = shutil.which("gh") or str(program_files / "GitHub CLI" / "gh.exe")
    if not Path(gh).exists():
        print("\nGitHub CLI is not installed. Run: winget install --id GitHub.cli -e")
        return False
    status = subprocess.run(
        [gh, "auth", "status"],
        check=False,
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        print("\nA GitHub sign-in page will open.")
        login = subprocess.run(
            [gh, "auth", "login", "--web", "--git-protocol", "https"],
            check=False,
        )
        if login.returncode != 0:
            return False
    token_result = subprocess.run(
        [gh, "auth", "token"],
        check=False,
        capture_output=True,
        text=True,
    )
    token = token_result.stdout.strip()
    if token_result.returncode != 0 or not token:
        return False
    store.save(
        OAuthSession(
            provider="github",
            client_id="github-cli",
            authorization_endpoint="",
            token_endpoint="",
            scopes=(),
            access_token=token,
            refresh_token=None,
            expires_at=None,
            server_url="https://api.githubcopilot.com/mcp/x/all/readonly",
        )
    )
    print("[OK] GitHub connected using GitHub CLI authentication.")
    return True


def run(
    argv: Sequence[str] | None = None,
    *,
    store: CredentialStore | None = None,
    environment: Mapping[str, str] | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        account = _normalize_account(args.account)
    except OAuthFlowError as exc:
        _parser().error(str(exc))
    account_targets = [*args.providers]
    if args.disconnect:
        account_targets.append(args.disconnect)
    if account and any(provider not in MULTI_ACCOUNT_PROVIDERS for provider in account_targets):
        _parser().error("--account can only be used with Google or Microsoft.")
    load_dotenv()
    values = os.environ if environment is None else environment
    credentials = store or KeyringCredentialStore()
    try:
        if args.import_google_client:
            _save_google_client(args.import_google_client, credentials)
            print("[OK] Google OAuth app saved securely.")
        if args.save_client:
            provider, client_id = args.save_client
            if provider not in PROVIDERS:
                raise OAuthFlowError(f"Unknown provider: {provider}")
            credentials.save_client(
                OAuthClientRegistration(
                    provider,
                    client_id,
                    args.client_secret or values.get("DESKBOB_WIZARD_CLIENT_SECRET") or None,
                )
            )
            print(f"[OK] {provider.title()} OAuth app saved securely.")
        if args.disconnect:
            session_key = _session_key(args.disconnect, account)
            credentials.delete(session_key)
            print(f"[OK] {session_key} account disconnected.")
        if args.status:
            _show_status(credentials, values)
            return 0
        changed_credentials = args.import_google_client or args.save_client or args.disconnect
        if changed_credentials and not args.providers:
            _show_status(credentials, values)
            return 0

        requested = tuple(args.providers) or PROVIDERS
        http = UrllibOAuthHTTPClient()
        manager = OAuthManager(credentials, http)
        missing: list[str] = []
        for provider in requested:
            try:
                provider_account = account if provider in MULTI_ACCOUNT_PROVIDERS else None
                if not _connect_provider(
                    provider,
                    credentials,
                    manager,
                    http,
                    values,
                    provider_account,
                ):
                    missing.append(provider)
            except (OAuthFlowError, RuntimeError) as exc:
                print(f"[FAILED] {provider.title()}: {exc}", file=sys.stderr)
                missing.append(provider)
        _show_status(credentials, values)
        if missing:
            print(
                "\nSome providers still need attention: " + ", ".join(missing) + ".",
                file=sys.stderr,
            )
            return 2
        print("\nAll requested accounts are connected. Restart DeskBob to use them.")
        return 0
    except (CredentialStoreError, OAuthFlowError) as exc:
        print(f"OAuth setup failed: {exc}", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run())


def _normalize_account(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().replace(" ", "-")
    if not ACCOUNT_PATTERN.fullmatch(normalized):
        raise OAuthFlowError(
            "Account labels must be 1-32 lowercase letters, numbers, hyphens, or underscores."
        )
    return normalized


def _session_key(provider: str, account: str | None) -> str:
    return provider if account is None else f"{provider}:{account}"


def _account_from_session_key(provider: str, session_key: str) -> str | None:
    prefix = f"{provider}:"
    return session_key[len(prefix) :] if session_key.startswith(prefix) else None


if __name__ == "__main__":
    main()
