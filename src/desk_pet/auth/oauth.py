from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import threading
import time
import urllib.parse
import webbrowser
from collections.abc import Callable
from typing import Any, Protocol

from desk_pet.auth.http import OAuthHTTPClient
from desk_pet.auth.models import OAuthClient, OAuthSession
from desk_pet.auth.store import CredentialStore


class OAuthFlowError(RuntimeError):
    """An OAuth sign-in was rejected, timed out, or returned invalid data."""


class AuthorizationBrowser(Protocol):
    @property
    def redirect_uri(self) -> str: ...

    def authorize(self, url: str, expected_state: str) -> str: ...


class LoopbackAuthorizationBrowser:
    def __init__(
        self,
        *,
        timeout_seconds: float = 300.0,
        browser_open: Callable[[str], bool] = webbrowser.open,
        host: str = "localhost",
        port: int = 0,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._browser_open = browser_open
        self._result: dict[str, str] = {}
        self._server = http.server.ThreadingHTTPServer((host, port), self._handler())
        self._server.timeout = timeout_seconds

    @property
    def redirect_uri(self) -> str:
        port = int(self._server.server_address[1])
        return f"http://localhost:{port}"

    def authorize(self, url: str, expected_state: str) -> str:
        try:
            if not self._browser_open(url):
                raise OAuthFlowError(
                    "The sign-in page could not be opened. Copy the displayed URL into a browser."
                )
            self._server.handle_request()
        finally:
            self._server.server_close()
        if not self._result:
            raise OAuthFlowError("Account sign-in timed out.")
        if self._result.get("state") != expected_state:
            raise OAuthFlowError("OAuth state validation failed; the response was discarded.")
        if error := self._result.get("error"):
            description = self._result.get("error_description", error)
            raise OAuthFlowError(f"Account authorization was not completed: {description}")
        code = self._result.get("code")
        if not code:
            raise OAuthFlowError("The account provider did not return an authorization code.")
        return code

    def _handler(self) -> type[http.server.BaseHTTPRequestHandler]:
        result = self._result

        class CallbackHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                values = urllib.parse.parse_qs(parsed.query)
                for key in ("code", "state", "error", "error_description"):
                    if key in values and values[key]:
                        result[key] = values[key][0]
                success = "code" in result and "error" not in result
                title = "DeskBob account connected" if success else "DeskBob connection failed"
                message = (
                    "You can close this tab and return to PowerShell."
                    if success
                    else "Return to PowerShell for the error details."
                )
                body = (
                    "<!doctype html><meta charset='utf-8'>"
                    f"<title>{title}</title>"
                    "<style>body{font-family:system-ui;margin:4rem;max-width:42rem}"
                    "h1{color:#b00020}</style>"
                    f"<h1>{title}</h1><p>{message}</p>"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_arguments: object) -> None:
                return

        return CallbackHandler


class OAuthManager:
    def __init__(
        self,
        store: CredentialStore,
        http: OAuthHTTPClient,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._http = http
        self._clock = clock
        self._locks: dict[str, threading.Lock] = {}

    def connect(
        self,
        client: OAuthClient,
        browser: AuthorizationBrowser,
        *,
        server_url: str | None = None,
    ) -> OAuthSession:
        verifier = _url_safe_secret(64)
        challenge = _base64_url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = _url_safe_secret(32)
        parameters = {
            "response_type": "code",
            "client_id": client.client_id,
            "redirect_uri": browser.redirect_uri,
            "scope": " ".join(client.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        parameters.update(dict(client.extra_authorization_parameters))
        authorization_url = f"{client.authorization_endpoint}?{urllib.parse.urlencode(parameters)}"
        code = browser.authorize(authorization_url, state)
        token_parameters = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client.client_id,
            "redirect_uri": browser.redirect_uri,
            "code_verifier": verifier,
        }
        if client.client_secret:
            token_parameters["client_secret"] = client.client_secret
        token_data = self._http.post_form(client.token_endpoint, token_parameters)
        session = self._session_from_token_data(client, token_data, server_url=server_url)
        self._store.save(session)
        return session

    def access_token(self, provider: str) -> str | None:
        session = self._store.load(provider)
        if session is None:
            return None
        if session.expires_at is None or session.expires_at > self._clock() + 300:
            return session.access_token
        if not session.refresh_token:
            return None
        lock = self._locks.setdefault(provider, threading.Lock())
        with lock:
            current = self._store.load(provider)
            if current is None:
                return None
            if current.expires_at is None or current.expires_at > self._clock() + 300:
                return current.access_token
            refreshed = self._refresh(current)
            self._store.save(refreshed)
            return refreshed.access_token

    def _refresh(self, session: OAuthSession) -> OAuthSession:
        assert session.refresh_token is not None
        parameters = {
            "grant_type": "refresh_token",
            "refresh_token": session.refresh_token,
            "client_id": session.client_id,
        }
        if session.client_secret:
            parameters["client_secret"] = session.client_secret
        token_data = _normalize_token_data(
            session.provider,
            self._http.post_form(session.token_endpoint, parameters),
        )
        access_token = _required_token(token_data, "access_token")
        refresh_token = _optional_token(token_data.get("refresh_token")) or session.refresh_token
        expires_at = _expires_at(token_data.get("expires_in"), self._clock())
        return OAuthSession(
            provider=session.provider,
            client_id=session.client_id,
            client_secret=session.client_secret,
            authorization_endpoint=session.authorization_endpoint,
            token_endpoint=session.token_endpoint,
            scopes=session.scopes,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            token_type=_optional_token(token_data.get("token_type")) or session.token_type,
            server_url=session.server_url,
        )

    def _session_from_token_data(
        self,
        client: OAuthClient,
        token_data: dict[str, Any],
        *,
        server_url: str | None,
    ) -> OAuthSession:
        normalized = _normalize_token_data(client.provider, token_data)
        return OAuthSession(
            provider=client.provider,
            client_id=client.client_id,
            client_secret=client.client_secret,
            authorization_endpoint=client.authorization_endpoint,
            token_endpoint=client.token_endpoint,
            scopes=client.scopes,
            access_token=_required_token(normalized, "access_token"),
            refresh_token=_optional_token(normalized.get("refresh_token")),
            expires_at=_expires_at(normalized.get("expires_in"), self._clock()),
            token_type=_optional_token(normalized.get("token_type")) or "Bearer",
            server_url=server_url,
        )


def _normalize_token_data(provider: str, value: dict[str, Any]) -> dict[str, Any]:
    if provider != "slack":
        return value
    if value.get("ok") is not True:
        error = _optional_token(value.get("error")) or "unknown_error"
        raise OAuthFlowError(f"Slack rejected the token exchange: {error}")
    authed_user = value.get("authed_user")
    if not isinstance(authed_user, dict):
        raise OAuthFlowError("Slack did not return an authenticated user token.")
    return authed_user


def _required_token(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise OAuthFlowError(f"OAuth token response is missing {key}.")
    return result


def _optional_token(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _expires_at(value: object, now: float) -> float | None:
    if isinstance(value, (int, float)):
        return now + float(value)
    if isinstance(value, str):
        try:
            return now + float(value)
        except ValueError:
            return None
    return None


def _url_safe_secret(length: int) -> str:
    return secrets.token_urlsafe(length)


def _base64_url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
