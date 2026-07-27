from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    STATE_CHANGED = "state_changed"
    TRIGGER_RECEIVED = "trigger_received"
    TRANSCRIPT_READY = "transcript_ready"
    TOOL_REQUESTED = "tool_requested"
    RESPONSE_READY = "response_ready"


@dataclass(frozen=True, slots=True)
class Event:
    type: EventType
    payload: dict[str, Any]
    created_at: datetime

    @classmethod
    def create(cls, event_type: EventType, **payload: Any) -> Event:
        return cls(event_type, payload, datetime.now(UTC))


EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    async def emit(self, event: Event) -> None:
        for handler in tuple(self._handlers):
            await handler(event)
