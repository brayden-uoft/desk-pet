from __future__ import annotations

import argparse
import json
import os
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
        connected = store.load(provider) is not None
        if provider in {"github", "notion"}:
            registration = True
        else:
            registration = _load_registration(provider, store, environment) is not None
        if connected:
            detail = "connected"
        elif registration:
            detail = "ready to sign in"
        else:
            detail = "needs one-time OAuth app setup"
        print(f"{provider:10} {detail}")


def _connect_provider(
    provider: str,
    store: CredentialStore,
    manager: OAuthManager,
    http: UrllibOAuthHTTPClient,
    environment: Mapping[str, str],
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
        server_url = "https://mcp.slack.com/mcp" if provider == "slack" else None
    print(f"\nOpening {provider.title()} sign-in...")
    manager.connect(client, browser, server_url=server_url)
    print(f"[OK] {provider.title()} connected. Tokens are in Windows Credential Manager.")
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
            credentials.delete(args.disconnect)
            print(f"[OK] {args.disconnect.title()} account disconnected.")
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
                if not _connect_provider(provider, credentials, manager, http, values):
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


if __name__ == "__main__":
    main()
