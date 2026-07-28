import asyncio
from typing import cast

from desk_pet.agent.connectors import (
    CONNECTOR_SPECS,
    OAuthConnectorLoader,
    connector_tools_from_environment,
)
from desk_pet.agent.tool_protocol import RemoteMCPTool
from desk_pet.auth.http import OAuthHTTPClient
from desk_pet.auth.models import OAuthSession
from desk_pet.auth.oauth import OAuthManager
from desk_pet.auth.store import MemoryCredentialStore


def test_no_connector_tokens_means_no_private_tools() -> None:
    assert connector_tools_from_environment({}) == []


def test_each_supported_connector_can_be_enabled_independently() -> None:
    for spec in CONNECTOR_SPECS:
        tools = connector_tools_from_environment(
            {spec.token_environment_variable: f"token-for-{spec.label}"}
        )

        assert len(tools) == 1
        tool = tools[0]
        assert tool["connector_id"] == spec.connector_id
        assert tool["authorization"] == f"token-for-{spec.label}"
        assert tool["allowed_tools"] == list(spec.read_only_tools)
        assert tool["require_approval"] == "never"


def test_connector_tool_lists_are_read_only() -> None:
    forbidden_words = ("send", "create", "update", "delete", "modify", "move")

    for spec in CONNECTOR_SPECS:
        assert spec.read_only_tools
        assert all(
            not any(word in tool_name for word in forbidden_words)
            for tool_name in spec.read_only_tools
        )


def test_oauth_loader_expands_one_google_login_into_three_connectors() -> None:
    store = MemoryCredentialStore()
    store.save(_session("google", "google-token"))
    loader = OAuthConnectorLoader(OAuthManager(store, _UnusedHTTP()), {})

    tools = asyncio.run(loader())

    assert [tool["server_label"] for tool in tools] == [
        "gmail",
        "google_calendar",
        "google_drive",
    ]
    assert all(tool["authorization"] == "google-token" for tool in tools)


def test_oauth_loader_labels_multiple_google_accounts_separately() -> None:
    store = MemoryCredentialStore()
    store.save(_session("google:personal", "personal-token"))
    store.save(_session("google:uoft", "uoft-token"))
    loader = OAuthConnectorLoader(OAuthManager(store, _UnusedHTTP()), {})

    tools = asyncio.run(loader())

    assert [tool["server_label"] for tool in tools] == [
        "gmail_personal",
        "google_calendar_personal",
        "google_drive_personal",
        "gmail_uoft",
        "google_calendar_uoft",
        "google_drive_uoft",
    ]
    assert {tool["authorization"] for tool in tools} == {
        "personal-token",
        "uoft-token",
    }
    assert all("Account label:" in tool["server_description"] for tool in tools)


def test_oauth_loader_adds_read_only_notion_remote_mcp() -> None:
    store = MemoryCredentialStore()
    store.save(_session("notion", "notion-token"))
    loader = OAuthConnectorLoader(OAuthManager(store, _UnusedHTTP()), {})

    tools = asyncio.run(loader())

    assert tools == [
        {
            "type": "mcp",
            "server_label": "notion",
            "server_description": "Search and read Brayden's Notion workspace.",
            "server_url": "https://mcp.notion.com/mcp",
            "authorization": "notion-token",
            "require_approval": "never",
            "allowed_tools": [
                "search",
                "fetch",
                "notion-get-self",
                "notion-get-comments",
                "notion-get-teams",
                "notion-get-users",
            ],
        }
    ]


def test_github_uses_server_enforced_read_only_endpoint() -> None:
    store = MemoryCredentialStore()
    store.save(_session("github", "github-token"))
    loader = OAuthConnectorLoader(OAuthManager(store, _UnusedHTTP()), {})

    tools = asyncio.run(loader())
    github = cast(RemoteMCPTool, tools[0])

    assert github["server_url"] == "https://api.githubcopilot.com/mcp/x/all/readonly"
    assert "allowed_tools" not in github


def _session(provider: str, access_token: str) -> OAuthSession:
    return OAuthSession(
        provider=provider,
        client_id="client-id",
        authorization_endpoint="https://example.test/authorize",
        token_endpoint="https://example.test/token",
        scopes=(),
        access_token=access_token,
        refresh_token=None,
        expires_at=None,
    )


class _UnusedHTTP(OAuthHTTPClient):
    def get_json(self, url: str) -> dict[str, object]:
        raise AssertionError(url)

    def post_form(self, url: str, values: object) -> dict[str, object]:
        raise AssertionError((url, values))

    def post_json(self, url: str, value: object) -> dict[str, object]:
        raise AssertionError((url, value))
