from __future__ import annotations

import pytest

import desk_pet.auth.store as store_module
from desk_pet.auth.models import OAuthSession
from desk_pet.auth.store import KeyringCredentialStore, MemoryCredentialStore


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
