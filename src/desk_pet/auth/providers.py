from __future__ import annotations

import os
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from desk_pet.auth.http import OAuthHTTPClient
from desk_pet.auth.models import OAuthClient, OAuthClientRegistration
from desk_pet.auth.oauth import AuthorizationBrowser, OAuthFlowError

MicrosoftAccountType = Literal["personal", "work", "work-teams"]


@dataclass(frozen=True, slots=True)
class ProviderRegistration:
    provider: str
    client_id_environment_variable: str
    client_secret_environment_variable: str | None
    setup_url: str


PROVIDER_REGISTRATIONS: tuple[ProviderRegistration, ...] = (
    ProviderRegistration(
        provider="google",
        client_id_environment_variable="DESKBOB_GOOGLE_CLIENT_ID",
        client_secret_environment_variable="DESKBOB_GOOGLE_CLIENT_SECRET",
        setup_url="https://console.cloud.google.com/auth/clients",
    ),
    ProviderRegistration(
        provider="microsoft",
        client_id_environment_variable="DESKBOB_MICROSOFT_CLIENT_ID",
        client_secret_environment_variable=None,
        setup_url="https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade",
    ),
    ProviderRegistration(
        provider="slack",
        client_id_environment_variable="DESKBOB_SLACK_CLIENT_ID",
        client_secret_environment_variable="DESKBOB_SLACK_CLIENT_SECRET",
        setup_url="https://api.slack.com/apps",
    ),
    ProviderRegistration(
        provider="dropbox",
        client_id_environment_variable="DESKBOB_DROPBOX_CLIENT_ID",
        client_secret_environment_variable=None,
        setup_url="https://www.dropbox.com/developers/apps",
    ),
)


def google_client(
    environment: Mapping[str, str] | None = None,
    registration: OAuthClientRegistration | None = None,
) -> OAuthClient:
    values = os.environ if environment is None else environment
    return OAuthClient(
        provider="google",
        client_id=registration.client_id
        if registration
        else _required_environment(values, "DESKBOB_GOOGLE_CLIENT_ID"),
        client_secret=registration.client_secret
        if registration
        else _optional_environment(values, "DESKBOB_GOOGLE_CLIENT_SECRET"),
        authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
        token_endpoint="https://oauth2.googleapis.com/token",
        scopes=(
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.events",
            "https://www.googleapis.com/auth/drive.readonly",
        ),
        extra_authorization_parameters=(
            ("access_type", "offline"),
            ("prompt", "consent"),
            ("include_granted_scopes", "true"),
        ),
    )


def microsoft_client(
    environment: Mapping[str, str] | None = None,
    registration: OAuthClientRegistration | None = None,
    *,
    account_type: MicrosoftAccountType = "personal",
) -> OAuthClient:
    values = os.environ if environment is None else environment
    tenant = values.get("DESKBOB_MICROSOFT_TENANT", "common").strip() or "common"
    base = f"https://login.microsoftonline.com/{urllib.parse.quote(tenant, safe='')}/oauth2/v2.0"
    scopes = [
        "offline_access",
        "openid",
        "profile",
        "email",
        "User.Read",
        "Mail.Read",
        "Calendars.Read",
    ]
    if account_type in {"work", "work-teams"}:
        scopes.extend(("Files.Read.All", "Sites.Read.All"))
    if account_type == "work-teams":
        scopes.extend(("Chat.Read", "ChannelMessage.Read.All"))
    return OAuthClient(
        provider="microsoft",
        client_id=registration.client_id
        if registration
        else _required_environment(values, "DESKBOB_MICROSOFT_CLIENT_ID"),
        authorization_endpoint=f"{base}/authorize",
        token_endpoint=f"{base}/token",
        scopes=tuple(scopes),
        extra_authorization_parameters=(("prompt", "select_account"),),
    )


def slack_client(
    environment: Mapping[str, str] | None = None,
    registration: OAuthClientRegistration | None = None,
) -> OAuthClient:
    values = os.environ if environment is None else environment
    return OAuthClient(
        provider="slack",
        client_id=registration.client_id
        if registration
        else _required_environment(values, "DESKBOB_SLACK_CLIENT_ID"),
        client_secret=(
            registration.client_secret
            if registration and registration.client_secret
            else _required_environment(values, "DESKBOB_SLACK_CLIENT_SECRET")
        ),
        authorization_endpoint="https://slack.com/oauth/v2_user/authorize",
        token_endpoint="https://slack.com/api/oauth.v2.user.access",
        scopes=(
            "search:read.public",
            "search:read.private",
            "search:read.mpim",
            "search:read.im",
            "search:read.files",
            "files:read",
            "search:read.users",
            "channels:history",
            "groups:history",
            "mpim:history",
            "im:history",
            "users:read",
            "users:read.email",
            "channels:read",
            "groups:read",
            "mpim:read",
        ),
    )


def dropbox_client(
    environment: Mapping[str, str] | None = None,
    registration: OAuthClientRegistration | None = None,
) -> OAuthClient:
    values = os.environ if environment is None else environment
    return OAuthClient(
        provider="dropbox",
        client_id=registration.client_id
        if registration
        else _required_environment(values, "DESKBOB_DROPBOX_CLIENT_ID"),
        authorization_endpoint="https://www.dropbox.com/oauth2/authorize",
        token_endpoint="https://api.dropboxapi.com/oauth2/token",
        scopes=(
            "account_info.read",
            "files.metadata.read",
            "files.content.read",
        ),
        extra_authorization_parameters=(
            ("token_access_type", "offline"),
            ("include_granted_scopes", "user"),
        ),
    )


def register_notion_client(
    http: OAuthHTTPClient,
    browser: AuthorizationBrowser,
) -> OAuthClient:
    server_url = "https://mcp.notion.com/mcp"
    protected_resource = _discover_protected_resource(http, server_url)
    authorization_servers = protected_resource.get("authorization_servers")
    if not isinstance(authorization_servers, list) or not authorization_servers:
        raise OAuthFlowError("Notion MCP did not advertise an OAuth authorization server.")
    authorization_server = authorization_servers[0]
    if not isinstance(authorization_server, str):
        raise OAuthFlowError("Notion MCP returned invalid authorization metadata.")
    metadata_url = f"{authorization_server.rstrip('/')}/.well-known/oauth-authorization-server"
    metadata = http.get_json(metadata_url)
    authorization_endpoint = _required_metadata(metadata, "authorization_endpoint")
    token_endpoint = _required_metadata(metadata, "token_endpoint")
    registration_endpoint = _required_metadata(metadata, "registration_endpoint")
    registration = http.post_json(
        registration_endpoint,
        {
            "client_name": "DeskBob",
            "client_uri": "https://github.com/brayden-uoft/desk-pet",
            "redirect_uris": [browser.redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    client_id = _required_metadata(registration, "client_id")
    client_secret = registration.get("client_secret")
    return OAuthClient(
        provider="notion",
        client_id=client_id,
        client_secret=client_secret if isinstance(client_secret, str) else None,
        authorization_endpoint=authorization_endpoint,
        token_endpoint=token_endpoint,
        scopes=(),
        extra_authorization_parameters=(("prompt", "consent"),),
    )


def _discover_protected_resource(
    http: OAuthHTTPClient,
    server_url: str,
) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(server_url)
    candidates = (
        f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource",
        f"{server_url.rstrip('/')}/.well-known/oauth-protected-resource",
    )
    error: RuntimeError | None = None
    for candidate in candidates:
        try:
            return http.get_json(candidate)
        except RuntimeError as exc:
            error = exc
    assert error is not None
    raise error


def _required_metadata(value: dict[str, Any], key: str) -> str:
    result = value.get(key)
    if not isinstance(result, str) or not result:
        raise OAuthFlowError(f"OAuth discovery response is missing {key}.")
    return result


def _required_environment(values: Mapping[str, str], name: str) -> str:
    value = values.get(name, "").strip()
    if not value:
        raise OAuthFlowError(f"{name} is not configured.")
    return value


def _optional_environment(values: Mapping[str, str], name: str) -> str | None:
    value = values.get(name, "").strip()
    return value or None
