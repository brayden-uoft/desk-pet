from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from datetime import datetime
from typing import Any, TypeVar

import pytest

from desk_pet.integrations.interfaces import (
    OutlookCalendarEvent,
    OutlookMailMessage,
    OutlookStatus,
)
from desk_pet.skills.defaults import create_default_skill_registry
from desk_pet.skills.registry import SkillValidationError

T = TypeVar("T")


def _run(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


def _json_result(output: object) -> dict[str, object]:
    assert isinstance(output, str)
    result = json.loads(output)
    assert isinstance(result, dict)
    return result


class FakeOutlookService:
    def __init__(self) -> None:
        self.mail_calls: list[tuple[str, int, bool]] = []
        self.calendar_calls: list[tuple[datetime, datetime, int]] = []

    async def status(self) -> OutlookStatus:
        return OutlookStatus(
            available=True,
            profile_name="DeskBob",
            stores=["personal@example.com"],
            message="ready",
        )

    async def search_mail(
        self,
        query: str,
        *,
        maximum_results: int,
        include_body: bool,
    ) -> list[OutlookMailMessage]:
        self.mail_calls.append((query, maximum_results, include_body))
        return [
            OutlookMailMessage(
                account="personal@example.com",
                subject="Project update",
                sender_name="Grace",
                sender_address="grace@example.com",
                received_at="2026-07-28T18:00:00-04:00",
                body_excerpt="Ready for review." if include_body else None,
            )
        ]

    async def calendar_events(
        self,
        start: datetime,
        end: datetime,
        *,
        maximum_results: int,
    ) -> list[OutlookCalendarEvent]:
        self.calendar_calls.append((start, end, maximum_results))
        return [
            OutlookCalendarEvent(
                account="personal@example.com",
                subject="Dinner",
                start="2026-07-28T19:00:00-04:00",
                end="2026-07-28T20:00:00-04:00",
                location="Toronto",
                organizer="Grace",
                all_day=False,
            )
        ]


def test_outlook_skills_are_registered_and_read_from_service() -> None:
    service = FakeOutlookService()
    registry = create_default_skill_registry(outlook=service)

    mail = _json_result(
        _run(
            registry.execute(
                "search_outlook_mail",
                '{"query":"project","maximum_results":5,"include_body":true}',
            )
        )
    )
    calendar = _json_result(
        _run(
            registry.execute(
                "read_outlook_calendar",
                (
                    '{"start":"2026-07-28T00:00:00-04:00",'
                    '"end":"2026-07-29T00:00:00-04:00","maximum_results":10}'
                ),
            )
        )
    )

    messages = mail["messages"]
    events = calendar["events"]
    assert isinstance(messages, list)
    assert isinstance(events, list)
    assert messages[0]["subject"] == "Project update"
    assert events[0]["subject"] == "Dinner"
    assert service.mail_calls == [("project", 5, True)]
    assert service.calendar_calls[0][2] == 10


@pytest.mark.parametrize(
    ("skill", "arguments", "message"),
    [
        (
            "search_outlook_mail",
            '{"query":"","maximum_results":0,"include_body":false}',
            "maximum_results",
        ),
        (
            "search_outlook_mail",
            '{"query":"","maximum_results":1,"include_body":false,"extra":true}',
            "Unknown arguments",
        ),
        (
            "read_outlook_calendar",
            (
                '{"start":"2026-07-28T00:00:00",'
                '"end":"2026-07-29T00:00:00-04:00","maximum_results":10}'
            ),
            "UTC offset",
        ),
        (
            "read_outlook_calendar",
            (
                '{"start":"2026-07-29T00:00:00-04:00",'
                '"end":"2026-07-28T00:00:00-04:00","maximum_results":10}'
            ),
            "end must be after start",
        ),
    ],
)
def test_outlook_skills_reject_invalid_arguments(
    skill: str,
    arguments: str,
    message: str,
) -> None:
    registry = create_default_skill_registry(outlook=FakeOutlookService())

    with pytest.raises(SkillValidationError, match=message):
        _run(registry.execute(skill, arguments))


def test_outlook_skills_are_absent_without_local_service() -> None:
    names = {schema["name"] for schema in create_default_skill_registry().schemas()}

    assert "search_outlook_mail" not in names
    assert "read_outlook_calendar" not in names
