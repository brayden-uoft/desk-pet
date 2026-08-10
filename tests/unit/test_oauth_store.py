from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import desk_pet.auth.store as store_module
from desk_pet.auth.models import OAuthClientRegistration, OAuthSession
from desk_pet.auth.store import (
    FileCredentialStore,
    KeyringCredentialStore,
    MemoryCredentialStore,
    credential_store_from_environment,
)


def _session(key: str) -> OAuthSession:
    return OAuthSession(
        provider=key,
        client_id="client",
        authorization_endpoint="https://example.test/authorize",
        token_endpoint="https://example.test/token",
        scopes=(),
        access_token=f"token-{key}",
        refresh_token=None,
        expires_at=None,
    )


def test_store_lists_named_accounts_without_mixing_providers() -> None:
    store = MemoryCredentialStore()
    store.save(_session("google:personal"))
    store.save(_session("google:uoft"))
    store.save(_session("microsoft:uoft"))

    sessions = store.list_sessions("google")

    assert [session.provider for session in sessions] == [
        "google:personal",
        "google:uoft",
    ]


def test_legacy_single_account_is_still_listed() -> None:
    store = MemoryCredentialStore()
    store.save(_session("google"))

    assert store.list_sessions("google") == [store.load("google")]


class FakeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.values[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_keyring_store_persists_named_account_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = FakeKeyring()
    monkeypatch.setattr(store_module, "_keyring", lambda: keyring)
    store = KeyringCredentialStore(service_name="test")
    store.save(_session("google:personal"))
    store.save(_session("google:uoft"))

    reopened = KeyringCredentialStore(service_name="test")

    assert [session.provider for session in reopened.list_sessions("google")] == [
        "google:personal",
        "google:uoft",
    ]


def test_keyring_store_chunks_large_oauth_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = FakeKeyring()
    monkeypatch.setattr(store_module, "_keyring", lambda: keyring)
    store = KeyringCredentialStore(service_name="test")
    large_session = OAuthSession(
        provider="dropbox",
        client_id="client",
        authorization_endpoint="https://www.dropbox.com/oauth2/authorize",
        token_endpoint="https://api.dropboxapi.com/oauth2/token",
        scopes=("account_info.read", "files.metadata.read", "files.content.read"),
        access_token="a" * 6_000,
        refresh_token="r" * 3_000,
        expires_at=None,
    )

    store.save(large_session)

    assert store.load("dropbox") == large_session
    manifest = keyring.values[("test", "dropbox")]
    assert manifest.startswith("deskbob-chunks:")
    assert all(len(value) <= 900 for value in keyring.values.values())

    store.delete("dropbox")

    assert not any(username.startswith("dropbox") for _, username in keyring.values)


def test_keyring_store_removes_chunks_when_session_becomes_small(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = FakeKeyring()
    monkeypatch.setattr(store_module, "_keyring", lambda: keyring)
    store = KeyringCredentialStore(service_name="test")
    large_session = OAuthSession(
        provider="dropbox",
        client_id="client",
        authorization_endpoint="https://www.dropbox.com/oauth2/authorize",
        token_endpoint="https://api.dropboxapi.com/oauth2/token",
        scopes=(),
        access_token="a" * 6_000,
        refresh_token=None,
        expires_at=None,
    )
    store.save(large_session)

    store.save(_session("dropbox"))

    assert store.load("dropbox") == _session("dropbox")
    assert not any(":chunk:" in username for _, username in keyring.values)


def test_legacy_github_session_with_empty_endpoints_is_repaired_on_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keyring = FakeKeyring()
    legacy = _session("github").to_dict()
    legacy["authorization_endpoint"] = ""
    legacy["token_endpoint"] = ""

    keyring.set_password("test", "github", json.dumps(legacy))
    monkeypatch.setattr(store_module, "_keyring", lambda: keyring)

    session = KeyringCredentialStore(service_name="test").load("github")

    assert session is not None
    assert session.authorization_endpoint == "https://github.com/login/oauth/authorize"
    assert session.token_endpoint == "https://github.com/login/oauth/access_token"


def test_file_store_persists_sessions_and_clients_privately(tmp_path: Path) -> None:
    path = tmp_path / "private" / "oauth.json"
    store = FileCredentialStore(path)
    session = _session("google:personal")
    registration = OAuthClientRegistration(
        provider="google",
        client_id="client-id",
        client_secret="client-secret",
    )

    store.save(session)
    store.save_client(registration)
    reopened = FileCredentialStore(path)

    assert reopened.load("google:personal") == session
    assert reopened.list_sessions("google") == [session]
    assert reopened.load_client("google") == registration
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700

    reopened.delete("google:personal")
    assert reopened.list_sessions("google") == []


def test_environment_selects_file_store(tmp_path: Path) -> None:
    path = tmp_path / "oauth.json"

    store = credential_store_from_environment({"DESKBOB_CREDENTIAL_FILE": str(path)})

    assert isinstance(store, FileCredentialStore)
