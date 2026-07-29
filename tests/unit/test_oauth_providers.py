from desk_pet.auth.models import OAuthClientRegistration
from desk_pet.auth.providers import microsoft_client


def test_personal_microsoft_profile_avoids_work_and_admin_scopes() -> None:
    client = microsoft_client(
        {},
        OAuthClientRegistration("microsoft", "client-id"),
        account_type="personal",
    )

    assert "Mail.Read" in client.scopes
    assert "Calendars.Read" in client.scopes
    assert "Sites.Read.All" not in client.scopes
    assert "ChannelMessage.Read.All" not in client.scopes


def test_work_microsoft_profile_adds_sharepoint_but_not_teams() -> None:
    client = microsoft_client(
        {},
        OAuthClientRegistration("microsoft", "client-id"),
        account_type="work",
    )

    assert "Files.Read.All" in client.scopes
    assert "Sites.Read.All" in client.scopes
    assert "Chat.Read" not in client.scopes
    assert "ChannelMessage.Read.All" not in client.scopes


def test_work_teams_profile_explicitly_adds_admin_prone_scopes() -> None:
    client = microsoft_client(
        {},
        OAuthClientRegistration("microsoft", "client-id"),
        account_type="work-teams",
    )

    assert "Chat.Read" in client.scopes
    assert "ChannelMessage.Read.All" in client.scopes
