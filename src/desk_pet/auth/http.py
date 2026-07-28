from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any, Protocol


class OAuthHTTPError(RuntimeError):
    """An OAuth discovery, registration, or token request failed."""


class OAuthHTTPClient(Protocol):
    def get_json(self, url: str) -> dict[str, Any]: ...

    def post_form(self, url: str, values: Mapping[str, str]) -> dict[str, Any]: ...

    def post_json(self, url: str, value: Mapping[str, Any]) -> dict[str, Any]: ...


class UrllibOAuthHTTPClient:
    def __init__(self, *, timeout_seconds: float = 30.0) -> None:
        self._timeout_seconds = timeout_seconds

    def get_json(self, url: str) -> dict[str, Any]:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "DeskBob/0.1"},
        )
        return self._send(request)

    def post_form(self, url: str, values: Mapping[str, str]) -> dict[str, Any]:
        body = urllib.parse.urlencode(values).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "DeskBob/0.1",
            },
            method="POST",
        )
        return self._send(request)

    def post_json(self, url: str, value: Mapping[str, Any]) -> dict[str, Any]:
        body = json.dumps(dict(value)).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "DeskBob/0.1",
            },
            method="POST",
        )
        return self._send(request)

    def _send(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise OAuthHTTPError(
                f"OAuth service returned HTTP {exc.code} for {request.full_url}."
            ) from exc
        except urllib.error.URLError as exc:
            raise OAuthHTTPError(f"Could not reach OAuth service at {request.full_url}.") from exc
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise OAuthHTTPError("OAuth service returned an invalid JSON response.") from exc
        if not isinstance(parsed, dict):
            raise OAuthHTTPError("OAuth service returned an unexpected response shape.")
        return parsed
