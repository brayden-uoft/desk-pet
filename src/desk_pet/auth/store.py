from __future__ import annotations

import importlib
import json
from typing import Any, Protocol, cast

from desk_pet.auth.models import OAuthClientRegistration, OAuthSession

SERVICE_NAME = "DeskBob OAuth"


class CredentialStoreError(RuntimeError):
    """Secure credential storage is unavailable or contains invalid data."""


class CredentialStore(Protocol):
    def load(self, provider: str) -> OAuthSession | None: ...

    def save(self, session: OAuthSession) -> None: ...

    def delete(self, provider: str) -> None: ...

    def load_client(self, provider: str) -> OAuthClientRegistration | None: ...

    def save_client(self, registration: OAuthClientRegistration) -> None: ...


class KeyringCredentialStore:
    """Store OAuth sessions in the operating system credential vault."""

    def __init__(self, *, service_name: str = SERVICE_NAME) -> None:
        self._service_name = service_name

    def load(self, provider: str) -> OAuthSession | None:
        keyring = _keyring()
        try:
            encoded = keyring.get_password(self._service_name, provider)
        except Exception as exc:
            raise CredentialStoreError("Windows Credential Manager could not be read.") from exc
        if not encoded:
            return None
        try:
            parsed = json.loads(encoded)
            if not isinstance(parsed, dict):
                raise ValueError("Credential payload must be an object.")
            return OAuthSession.from_dict(parsed)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CredentialStoreError(
                f"The saved {provider} OAuth credential is invalid. Reconnect that account."
            ) from exc

    def save(self, session: OAuthSession) -> None:
        keyring = _keyring()
        encoded = json.dumps(session.to_dict(), separators=(",", ":"), sort_keys=True)
        try:
            keyring.set_password(self._service_name, session.provider, encoded)
        except Exception as exc:
            raise CredentialStoreError("Windows Credential Manager could not be updated.") from exc

    def delete(self, provider: str) -> None:
        keyring = _keyring()
        try:
            keyring.delete_password(self._service_name, provider)
        except Exception as exc:
            # Backends disagree about the exception used for an absent item.
            if "not found" not in str(exc).lower():
                raise CredentialStoreError(
                    "Windows Credential Manager could not remove the account."
                ) from exc

    def load_client(self, provider: str) -> OAuthClientRegistration | None:
        encoded = self._get(f"client:{provider}")
        if not encoded:
            return None
        try:
            parsed = json.loads(encoded)
            if not isinstance(parsed, dict):
                raise ValueError("Credential payload must be an object.")
            return OAuthClientRegistration.from_dict(parsed)
        except (json.JSONDecodeError, ValueError) as exc:
            raise CredentialStoreError(
                f"The saved {provider} OAuth app registration is invalid."
            ) from exc

    def save_client(self, registration: OAuthClientRegistration) -> None:
        encoded = json.dumps(
            registration.to_dict(),
            separators=(",", ":"),
            sort_keys=True,
        )
        self._set(f"client:{registration.provider}", encoded)

    def _get(self, username: str) -> str | None:
        keyring = _keyring()
        try:
            return cast(str | None, keyring.get_password(self._service_name, username))
        except Exception as exc:
            raise CredentialStoreError("Windows Credential Manager could not be read.") from exc

    def _set(self, username: str, encoded: str) -> None:
        keyring = _keyring()
        try:
            keyring.set_password(self._service_name, username, encoded)
        except Exception as exc:
            raise CredentialStoreError("Windows Credential Manager could not be updated.") from exc


class MemoryCredentialStore:
    """In-memory store used by tests and simulated setup flows."""

    def __init__(self) -> None:
        self.sessions: dict[str, OAuthSession] = {}
        self.clients: dict[str, OAuthClientRegistration] = {}

    def load(self, provider: str) -> OAuthSession | None:
        return self.sessions.get(provider)

    def save(self, session: OAuthSession) -> None:
        self.sessions[session.provider] = session

    def delete(self, provider: str) -> None:
        self.sessions.pop(provider, None)

    def load_client(self, provider: str) -> OAuthClientRegistration | None:
        return self.clients.get(provider)

    def save_client(self, registration: OAuthClientRegistration) -> None:
        self.clients[registration.provider] = registration


def _keyring() -> Any:
    try:
        return importlib.import_module("keyring")
    except ImportError as exc:
        raise CredentialStoreError(
            "Secure account storage is unavailable. Run scripts/connect_accounts.ps1."
        ) from exc
