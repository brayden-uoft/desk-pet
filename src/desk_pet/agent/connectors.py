from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from dataclasses import dataclass

from desk_pet.agent.tool_protocol import MCPConnectorTool, MCPTool, RemoteMCPTool
from desk_pet.auth.oauth import OAuthManager
from desk_pet.auth.store import CredentialStoreError


@dataclass(frozen=True, slots=True)
class ConnectorSpec:
    label: str
    description: str
    connector_id: str
    token_environment_variable: str
    read_only_tools: tuple[str, ...]


CONNECTOR_SPECS: tuple[ConnectorSpec, ...] = (
    ConnectorSpec(
        label="gmail",
        description="Search and read Brayden's Gmail when email context is useful.",
        connector_id="connector_gmail",
        token_environment_variable="DESKBOB_GMAIL_OAUTH_TOKEN",
        read_only_tools=(
            "get_profile",
            "search_emails",
            "search_email_ids",
            "get_recent_emails",
            "read_email",
            "batch_read_email",
        ),
    ),
    ConnectorSpec(
        label="google_calendar",
        description="Read Brayden's Google Calendar to understand his schedule.",
        connector_id="connector_googlecalendar",
        token_environment_variable="DESKBOB_GOOGLE_CALENDAR_OAUTH_TOKEN",
        read_only_tools=("get_profile", "search", "fetch", "search_events", "read_event"),
    ),
    ConnectorSpec(
        label="google_drive",
        description="Search and read documents from Brayden's Google Drive.",
        connector_id="connector_googledrive",
        token_environment_variable="DESKBOB_GOOGLE_DRIVE_OAUTH_TOKEN",
        read_only_tools=("get_profile", "list_drives", "search", "recent_documents", "fetch"),
    ),
    ConnectorSpec(
        label="outlook_calendar",
        description="Read Brayden's Outlook Calendar to understand his schedule.",
        connector_id="connector_outlookcalendar",
        token_environment_variable="DESKBOB_OUTLOOK_CALENDAR_OAUTH_TOKEN",
        read_only_tools=(
            "search_events",
            "fetch_event",
            "fetch_events_batch",
            "list_events",
            "get_profile",
        ),
    ),
    ConnectorSpec(
        label="outlook_email",
        description="Search and read Brayden's Outlook email when useful.",
        connector_id="connector_outlookemail",
        token_environment_variable="DESKBOB_OUTLOOK_EMAIL_OAUTH_TOKEN",
        read_only_tools=(
            "get_profile",
            "list_messages",
            "search_messages",
            "get_recent_emails",
            "fetch_message",
            "fetch_messages_batch",
        ),
    ),
    ConnectorSpec(
        label="microsoft_teams",
        description="Search and read Brayden's Microsoft Teams messages.",
        connector_id="connector_microsoftteams",
        token_environment_variable="DESKBOB_MICROSOFT_TEAMS_OAUTH_TOKEN",
        read_only_tools=("search", "fetch", "get_chat_members", "get_profile"),
    ),
    ConnectorSpec(
        label="sharepoint",
        description="Search and read Brayden's SharePoint and OneDrive documents.",
        connector_id="connector_sharepoint",
        token_environment_variable="DESKBOB_SHAREPOINT_OAUTH_TOKEN",
        read_only_tools=(
            "get_site",
            "search",
            "list_recent_documents",
            "fetch",
            "get_profile",
        ),
    ),
    ConnectorSpec(
        label="dropbox",
        description="Search and read files from Brayden's Dropbox.",
        connector_id="connector_dropbox",
        token_environment_variable="DESKBOB_DROPBOX_OAUTH_TOKEN",
        read_only_tools=(
            "search",
            "fetch",
            "search_files",
            "fetch_file",
            "list_recent_files",
            "get_profile",
        ),
    ),
)

PROVIDER_CONNECTORS: dict[str, tuple[str, ...]] = {
    "google": ("gmail", "google_calendar", "google_drive"),
    "microsoft": (
        "outlook_calendar",
        "outlook_email",
        "microsoft_teams",
        "sharepoint",
    ),
    "dropbox": ("dropbox",),
}

REMOTE_MCP_SPECS: dict[str, RemoteMCPTool] = {
    "github": RemoteMCPTool(
        type="mcp",
        server_label="github",
        server_description="Read repositories, issues, pull requests, and actions from GitHub.",
        server_url="https://api.githubcopilot.com/mcp/x/all/readonly",
        authorization="",
        require_approval="never",
    ),
    "notion": RemoteMCPTool(
        type="mcp",
        server_label="notion",
        server_description="Search and read Brayden's Notion workspace.",
        server_url="https://mcp.notion.com/mcp",
        authorization="",
        require_approval="never",
        allowed_tools=[
            "search",
            "fetch",
            "notion-get-self",
            "notion-get-comments",
            "notion-get-teams",
            "notion-get-users",
        ],
    ),
    "slack": RemoteMCPTool(
        type="mcp",
        server_label="slack",
        server_description="Search and read Brayden's Slack workspace.",
        server_url="https://mcp.slack.com/mcp",
        authorization="",
        require_approval="never",
        allowed_tools=[
            "search_messages",
            "search_files",
            "read_files",
            "search_emoji",
            "search_users",
            "search_channels",
            "read_channel",
            "read_thread",
            "read_canvas",
            "read_user_profile",
            "list_channel_members",
        ],
    ),
}


def connector_tools_from_environment(
    environment: Mapping[str, str] | None = None,
) -> list[MCPConnectorTool]:
    """Enable only connectors whose OAuth token is explicitly present."""
    values = os.environ if environment is None else environment
    tools: list[MCPConnectorTool] = []
    for spec in CONNECTOR_SPECS:
        authorization = values.get(spec.token_environment_variable, "").strip()
        if not authorization:
            continue
        tools.append(_connector_tool(spec, authorization))
    return tools


class OAuthConnectorLoader:
    """Build current read-only connector tools and refresh expiring tokens."""

    def __init__(
        self,
        manager: OAuthManager,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._manager = manager
        self._environment = os.environ if environment is None else environment

    async def __call__(self) -> list[MCPTool]:
        return await asyncio.to_thread(self.load)

    def load(self) -> list[MCPTool]:
        by_label = {spec.label: spec for spec in CONNECTOR_SPECS}
        tools: list[MCPTool] = list(connector_tools_from_environment(self._environment))
        enabled_labels = {tool["server_label"] for tool in tools}
        for provider, labels in PROVIDER_CONNECTORS.items():
            try:
                authorization = self._manager.access_token(provider)
            except CredentialStoreError:
                authorization = None
            if not authorization:
                continue
            for label in labels:
                if label in enabled_labels:
                    continue
                spec = by_label[label]
                tools.append(_connector_tool(spec, authorization))
                enabled_labels.add(label)
        for provider, template in REMOTE_MCP_SPECS.items():
            try:
                authorization = self._manager.access_token(provider)
            except CredentialStoreError:
                authorization = None
            if not authorization or provider in enabled_labels:
                continue
            tool = RemoteMCPTool(**template)
            tool["authorization"] = authorization
            tools.append(tool)
        return tools


def _connector_tool(spec: ConnectorSpec, authorization: str) -> MCPConnectorTool:
    return MCPConnectorTool(
        type="mcp",
        server_label=spec.label,
        server_description=spec.description,
        connector_id=spec.connector_id,
        authorization=authorization,
        require_approval="never",
        allowed_tools=list(spec.read_only_tools),
    )
