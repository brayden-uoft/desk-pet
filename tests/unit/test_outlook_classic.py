from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Iterator
from contextlib import contextmanager
from datetime import datetime
from types import SimpleNamespace
from typing import Any, TypeVar

from desk_pet.integrations.outlook_classic import WindowsOutlookClassicService

T = TypeVar("T")


def _run(awaitable: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(awaitable)


class Collection:
    def __init__(self, values: list[Any]) -> None:
        self.values = values
        self.Count = len(values)
        self.IncludeRecurrences = False

    def Item(self, index: int) -> Any:
        return self.values[index - 1]

    def Sort(self, _field: str, _descending: bool = False) -> None:
        return None

    def Restrict(self, _restriction: str) -> Collection:
        return self


class Store:
    def __init__(self, name: str, inbox: Collection, calendar: Collection) -> None:
        self.DisplayName = name
        self._folders = {6: inbox, 9: calendar}

    def GetDefaultFolder(self, folder: int) -> Any:
        return SimpleNamespace(Items=self._folders[folder])


def _service() -> WindowsOutlookClassicService:
    mail = SimpleNamespace(
        Subject="Project update",
        SenderName="Grace",
        SenderEmailAddress="grace@example.com",
        ReceivedTime=datetime.fromisoformat("2026-07-28T18:00:00-04:00"),
        Body="The prototype project is ready for review.",
    )
    event = SimpleNamespace(
        Subject="Dinner",
        Start=datetime.fromisoformat("2026-07-28T19:00:00-04:00"),
        End=datetime.fromisoformat("2026-07-28T20:00:00-04:00"),
        Location="Toronto",
        Organizer="Grace",
        AllDayEvent=False,
    )
    namespace = SimpleNamespace(
        CurrentUser=SimpleNamespace(Name="Brayden"),
        Stores=Collection([Store("personal@example.com", Collection([mail]), Collection([event]))]),
    )

    @contextmanager
    def namespace_factory() -> Iterator[Any]:
        yield namespace

    return WindowsOutlookClassicService(namespace_factory)


def test_status_lists_local_outlook_stores_without_message_content() -> None:
    status = _run(_service().status())

    assert status["available"] is True
    assert status["profile_name"] == "Brayden"
    assert status["stores"] == ["personal@example.com"]


def test_mail_search_is_read_only_and_can_omit_body() -> None:
    matches = _run(
        _service().search_mail(
            "prototype",
            maximum_results=5,
            include_body=False,
        )
    )

    assert matches[0]["subject"] == "Project update"
    assert matches[0]["body_excerpt"] is None
    assert matches[0]["account"] == "personal@example.com"


def test_calendar_query_reads_one_time_range() -> None:
    events = _run(
        _service().calendar_events(
            datetime.fromisoformat("2026-07-28T00:00:00-04:00"),
            datetime.fromisoformat("2026-07-29T00:00:00-04:00"),
            maximum_results=5,
        )
    )

    assert events[0]["subject"] == "Dinner"
    assert events[0]["all_day"] is False


def test_status_turns_profile_failure_into_safe_guidance() -> None:
    @contextmanager
    def broken_factory() -> Iterator[Any]:
        raise RuntimeError("private COM details")
        yield

    status = _run(WindowsOutlookClassicService(broken_factory).status())

    assert status["available"] is False
    assert "private COM details" not in status["message"]
    assert "Open Outlook Classic" in status["message"]
