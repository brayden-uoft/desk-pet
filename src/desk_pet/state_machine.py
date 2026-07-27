from __future__ import annotations

from enum import StrEnum

from desk_pet.events import Event, EventBus, EventType


class PetState(StrEnum):
    STARTING = "starting"
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    USING_TOOL = "using_tool"
    SPEAKING = "speaking"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    MUTED = "muted"
    ERROR = "error"


class StateMachine:
    def __init__(self, events: EventBus) -> None:
        self._state = PetState.STARTING
        self._events = events

    @property
    def state(self) -> PetState:
        return self._state

    async def transition_to(self, state: PetState) -> None:
        previous = self._state
        self._state = state
        await self._events.emit(
            Event.create(
                EventType.STATE_CHANGED,
                previous=previous.value,
                state=state.value,
            )
        )
