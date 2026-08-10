from __future__ import annotations

import importlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, cast

from desk_pet.auth.models import OAuthClientRegistration, OAuthSession

SERVICE_NAME = "DeskBob OAuth"
SESSION_INDEX_USERNAME = "session-index"
_CHUNK_MARKER = "deskbob-chunks:"
# Windows Credential Manager caps a generic credential blob at 2,560 bytes.
# The keyring backend encodes text as UTF-16, so keep plenty of headroom.
_CREDENTIAL_CHUNK_CHARACTERS = 900


class CredentialStoreError(RuntimeError):
    """Secure credential storage is unavailable or contains invalid data."""


class CredentialStore(Protocol):
    def load(self, provider: str) -> OAuthSession | None: ...

    def save(self, session: OAuthSession) -> None: ...

    def delete(self, provider: str) -> None: ...

    def list_sessions(self, provider: str) -> list[OAuthSession]: ...

    def load_client(self, provider: str) -> OAuthClientRegistration | None: ...

    def save_client(self, registration: OAuthClientRegistration) -> None: ...


class KeyringCredentialStore:
    """Store OAuth sessions in the operating system credential vault."""

    def __init__(self, *, service_name: str = SERVICE_NAME) -> None:
        self._service_name = service_name

    def load(self, provider: str) -> OAuthSession | None:
        encoded = self._get(provider)
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
        encoded = json.dumps(session.to_dict(), separators=(",", ":"), sort_keys=True)
        self._set(session.provider, encoded)
        keys = set(self._session_keys())
        keys.add(session.provider)
        self._save_session_keys(keys)

    def delete(self, provider: str) -> None:
        self._delete_encoded(provider)
        keys = set(self._session_keys())
        keys.discard(provider)
        self._save_session_keys(keys)

    def list_sessions(self, provider: str) -> list[OAuthSession]:
        keys = {
            key for key in self._session_keys() if key == provider or key.startswith(f"{provider}:")
        }
        # Sessions created before multi-account support are not in the index.
        if self.load(provider) is not None:
            keys.add(provider)
        return [session for key in sorted(keys) if (session := self.load(key)) is not None]

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
        encoded = self._raw_get(username)
        if not encoded or not encoded.startswith(_CHUNK_MARKER):
            return encoded
        try:
            chunk_count = int(encoded.removeprefix(_CHUNK_MARKER))
        except ValueError as exc:
            raise CredentialStoreError("The saved OAuth credential manifest is invalid.") from exc
        chunks = [
            self._raw_get(self._chunk_username(username, index)) for index in range(chunk_count)
        ]
        if any(chunk is None for chunk in chunks):
            raise CredentialStoreError("The saved OAuth credential is incomplete. Reconnect it.")
        return "".join(cast(str, chunk) for chunk in chunks)

    def _raw_get(self, username: str) -> str | None:
        keyring = _keyring()
        try:
            return cast(str | None, keyring.get_password(self._service_name, username))
        except Exception as exc:
            raise CredentialStoreError("Windows Credential Manager could not be read.") from exc

    def _set(self, username: str, encoded: str) -> None:
        previous_chunks = self._chunk_count(self._raw_get(username))
        if len(encoded) <= _CREDENTIAL_CHUNK_CHARACTERS:
            self._raw_set(username, encoded)
            self._delete_extra_chunks(username, previous_chunks, keep=0)
            return
        chunks = [
            encoded[start : start + _CREDENTIAL_CHUNK_CHARACTERS]
            for start in range(0, len(encoded), _CREDENTIAL_CHUNK_CHARACTERS)
        ]
        for index, chunk in enumerate(chunks):
            self._raw_set(self._chunk_username(username, index), chunk)
        self._raw_set(username, f"{_CHUNK_MARKER}{len(chunks)}")
        self._delete_extra_chunks(username, previous_chunks, keep=len(chunks))

    def _raw_set(self, username: str, encoded: str) -> None:
        keyring = _keyring()
        try:
            keyring.set_password(self._service_name, username, encoded)
        except Exception as exc:
            raise CredentialStoreError("Windows Credential Manager could not be updated.") from exc

    def _delete_encoded(self, username: str) -> None:
        encoded = self._raw_get(username)
        self._raw_delete(username)
        self._delete_extra_chunks(username, self._chunk_count(encoded), keep=0)

    def _raw_delete(self, username: str) -> None:
        keyring = _keyring()
        try:
            keyring.delete_password(self._service_name, username)
        except Exception as exc:
            # Backends disagree about the exception used for an absent item.
            if "not found" not in str(exc).lower():
                raise CredentialStoreError(
                    "Windows Credential Manager could not remove the account."
                ) from exc

    def _delete_extra_chunks(self, username: str, existing: int, *, keep: int) -> None:
        for index in range(keep, existing):
            self._raw_delete(self._chunk_username(username, index))

    @staticmethod
    def _chunk_username(username: str, index: int) -> str:
        return f"{username}:chunk:{index}"

    @staticmethod
    def _chunk_count(encoded: str | None) -> int:
        if not encoded or not encoded.startswith(_CHUNK_MARKER):
            return 0
        try:
            return max(0, int(encoded.removeprefix(_CHUNK_MARKER)))
        except ValueError:
            return 0

    def _session_keys(self) -> list[str]:
        encoded = self._get(SESSION_INDEX_USERNAME)
        if not encoded:
            return []
        try:
            parsed = json.loads(encoded)
        except json.JSONDecodeError as exc:
            raise CredentialStoreError("The saved OAuth account index is invalid.") from exc
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise CredentialStoreError("The saved OAuth account index is invalid.")
        return parsed

    def _save_session_keys(self, keys: set[str]) -> None:
        self._set(SESSION_INDEX_USERNAME, json.dumps(sorted(keys), separators=(",", ":")))


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

    def list_sessions(self, provider: str) -> list[OAuthSession]:
        return [
            session
            for key, session in sorted(self.sessions.items())
            if key == provider or key.startswith(f"{provider}:")
        ]

    def load_client(self, provider: str) -> OAuthClientRegistration | None:
        return self.clients.get(provider)

    def save_client(self, registration: OAuthClientRegistration) -> None:
        self.clients[registration.provider] = registration


class FileCredentialStore:
    """Store OAuth data in a private file for a dedicated Linux device."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser()

    def load(self, provider: str) -> OAuthSession | None:
        value = self._document()["sessions"].get(provider)
        if value is None:
            return None
        try:
            return OAuthSession.from_dict(value)
        except (TypeError, ValueError) as exc:
            raise CredentialStoreError(
                f"The saved {provider} OAuth credential is invalid. Reconnect that account."
            ) from exc

    def save(self, session: OAuthSession) -> None:
        document = self._document()
        document["sessions"][session.provider] = session.to_dict()
        self._write(document)

    def delete(self, provider: str) -> None:
        document = self._document()
        document["sessions"].pop(provider, None)
        self._write(document)

    def list_sessions(self, provider: str) -> list[OAuthSession]:
        sessions = self._document()["sessions"]
        keys = sorted(key for key in sessions if key == provider or key.startswith(f"{provider}:"))
        return [session for key in keys if (session := self.load(key)) is not None]

    def load_client(self, provider: str) -> OAuthClientRegistration | None:
        value = self._document()["clients"].get(provider)
        if value is None:
            return None
        try:
            return OAuthClientRegistration.from_dict(value)
        except (TypeError, ValueError) as exc:
            raise CredentialStoreError(
                f"The saved {provider} OAuth app registration is invalid."
            ) from exc

    def save_client(self, registration: OAuthClientRegistration) -> None:
        document = self._document()
        document["clients"][registration.provider] = registration.to_dict()
        self._write(document)

    def _document(self) -> dict[str, dict[str, Any]]:
        if not self._path.exists():
            return {"sessions": {}, "clients": {}}
        try:
            value = json.loads(self._path.read_text(encoding="utf-8"))
            sessions = value["sessions"]
            clients = value["clients"]
            if not isinstance(sessions, dict) or not isinstance(clients, dict):
                raise ValueError("Credential collections must be objects.")
            return {"sessions": sessions, "clients": clients}
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise CredentialStoreError(
                f"The OAuth credential file {self._path} is invalid."
            ) from exc

    def _write(self, document: dict[str, dict[str, Any]]) -> None:
        try:
            self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            temporary = self._path.with_suffix(f"{self._path.suffix}.tmp")
            temporary.write_text(
                json.dumps(document, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            os.chmod(temporary, 0o600)
            temporary.replace(self._path)
            os.chmod(self._path, 0o600)
        except OSError as exc:
            raise CredentialStoreError(
                f"The OAuth credential file {self._path} could not be updated."
            ) from exc


def credential_store_from_environment(
    environment: Mapping[str, str] | None = None,
) -> CredentialStore:
    values = os.environ if environment is None else environment
    path = values.get("DESKBOB_CREDENTIAL_FILE", "").strip()
    return FileCredentialStore(Path(path)) if path else KeyringCredentialStore()


def _keyring() -> Any:
    try:
        return importlib.import_module("keyring")
    except ImportError as exc:
        raise CredentialStoreError(
            "Secure account storage is unavailable. Run scripts/connect_accounts.ps1."
        ) from exc
