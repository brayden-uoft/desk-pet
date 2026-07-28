from __future__ import annotations

import urllib.parse
from collections.abc import Mapping
from typing import Any

from desk_pet.auth.models import OAuthClient, OAuthSession
from desk_pet.auth.oauth import OAuthManager
from desk_pet.auth.store import MemoryCredentialStore


class FakeBrowser:
    redirect_uri = "http://localhost:54321"

    def __init__(self) -> None:
        self.url = ""

    def authorize(self, url: str, expected_state: str) -> str:
        self.url = url
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        assert query["state"] == [expected_state]
        assert query["code_challenge_method"] == ["S256"]
        assert query["redirect_uri"] == [self.redirect_uri]
        return "authorization-code"


class FakeHTTP:
    def __init__(self) -> None:
        self.forms: list[tuple[str, Mapping[str, str]]] = []
        self.responses = [
            {
                "access_token": "initial-access",
                "refresh_token": "refresh",
                "expires_in": 60,
            },
            {"access_token": "refreshed-access", "expires_in": 3600},
        ]

    def get_json(self, url: str) -> dict[str, Any]:
        raise AssertionError(url)

    def post_form(
        self,
        url: str,
        values: Mapping[str, str],
    ) -> dict[str, Any]:
        self.forms.append((url, dict(values)))
        return self.responses.pop(0)

    def post_json(self, url: str, value: Mapping[str, Any]) -> dict[str, Any]:
        raise AssertionError((url, value))


def test_browser_oauth_uses_pkce_stores_and_refreshes_session() -> None:
    store = MemoryCredentialStore()
    http = FakeHTTP()
    manager = OAuthManager(store, http, clock=lambda: 1_000)
    client = OAuthClient(
        provider="example",
        client_id="desktop-client",
        client_secret=None,
        authorization_endpoint="https://example.test/authorize",
        token_endpoint="https://example.test/token",
        scopes=("read",),
    )

    session = manager.connect(client, FakeBrowser())
    token = manager.access_token("example")

    assert session.access_token == "initial-access"
    assert token == "refreshed-access"
    assert store.load("example") == OAuthSession(
        provider="example",
        client_id="desktop-client",
        client_secret=None,
        authorization_endpoint="https://example.test/authorize",
        token_endpoint="https://example.test/token",
        scopes=("read",),
        access_token="refreshed-access",
        refresh_token="refresh",
        expires_at=4_600,
        token_type="Bearer",
        server_url=None,
    )
    assert http.forms[0][1]["code_verifier"]
    assert http.forms[1][1] == {
        "grant_type": "refresh_token",
        "refresh_token": "refresh",
        "client_id": "desktop-client",
    }
