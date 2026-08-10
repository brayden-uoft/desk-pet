from __future__ import annotations

from datetime import datetime
from typing import Protocol, TypedDict


class OutlookStatus(TypedDict):
    available: bool
    profile_name: str
    stores: list[str]
    message: str


class OutlookMailMessage(TypedDict):
    account: str
    subject: str
    sender_name: str
    sender_address: str
    received_at: str
    body_excerpt: str | None


class OutlookCalendarEvent(TypedDict):
    account: str
    subject: str
    start: str
    end: str
    location: str
    organizer: str
    all_day: bool


class OutlookClassicService(Protocol):
    async def status(self) -> OutlookStatus:
        """Return local Outlook availability without exposing message content."""

    async def search_mail(
        self,
        query: str,
        *,
        maximum_results: int,
        include_body: bool,
    ) -> list[OutlookMailMessage]:
        """Search read-only mail across the configured Outlook stores."""

    async def calendar_events(
        self,
        start: datetime,
        end: datetime,
        *,
        maximum_results: int,
    ) -> list[OutlookCalendarEvent]:
        """Read calendar events across configured Outlook stores."""
