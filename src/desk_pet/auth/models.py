from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class OAuthClient:
    provider: str
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    scopes: tuple[str, ...]
    client_secret: str | None = None
    extra_authorization_parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class OAuthClientRegistration:
    provider: str
    client_id: str
    client_secret: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OAuthClientRegistration:
        return cls(
            provider=_required_string(value, "provider"),
            client_id=_required_string(value, "client_id"),
            client_secret=_optional_string(value.get("client_secret")),
        )


@dataclass(frozen=True, slots=True)
class OAuthSession:
    provider: str
    client_id: str
    authorization_endpoint: str
    token_endpoint: str
    scopes: tuple[str, ...]
    access_token: str
    refresh_token: str | None
    expires_at: float | None
    client_secret: str | None = None
    token_type: str = "Bearer"
    server_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> OAuthSession:
        return cls(
            provider=_required_string(value, "provider"),
            client_id=_required_string(value, "client_id"),
            client_secret=_optional_string(value.get("client_secret")),
            authorization_endpoint=_required_string(value, "authorization_endpoint"),
            token_endpoint=_required_string(value, "token_endpoint"),
            scopes=tuple(_string_list(value.get("scopes"))),
            access_token=_required_string(value, "access_token"),
            refresh_token=_optional_string(value.get("refresh_token")),
            expires_at=_optional_float(value.get("expires_at")),
            token_type=_optional_string(value.get("token_type")) or "Bearer",
            server_url=_optional_string(value.get("server_url")),
        )


def _required_string(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise ValueError(f"Stored OAuth session is missing {key}.")
    return result


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_float(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, str)]
