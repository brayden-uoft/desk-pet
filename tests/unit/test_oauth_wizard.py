from __future__ import annotations

import pytest

from desk_pet.auth.models import OAuthSession
from desk_pet.auth.store import MemoryCredentialStore
from desk_pet.auth.wizard import run


def _session(key: str) -> OAuthSession:
    return OAuthSession(
        provider=key,
        client_id="client",
        authorization_endpoint="https://example.test/authorize",
        token_endpoint="https://example.test/token",
        scopes=(),
        access_token="secret-token",
        refresh_token="secret-refresh",
        expires_at=None,
    )


def test_status_lists_named_accounts_without_printing_tokens(
    capsys: pytest.CaptureFixture[str],
) -> None:
    store = MemoryCredentialStore()
    store.save(_session("google:personal"))
    store.save(_session("google:uoft"))

    result = run(["--status"], store=store, environment={})

    output = capsys.readouterr().out
    assert result == 0
    assert "google:personal" in output
    assert "google:uoft" in output
    assert "secret-token" not in output
    assert "secret-refresh" not in output


def test_unknown_provider_is_rejected(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        run(["g"])

    assert raised.value.code == 2
    assert "unknown provider 'g'" in capsys.readouterr().err
