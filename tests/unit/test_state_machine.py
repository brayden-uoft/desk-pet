import asyncio

from desk_pet.events import Event, EventBus, EventType
from desk_pet.state_machine import PetState, StateMachine


def test_transition_changes_state_and_emits_event() -> None:
    async def scenario() -> None:
        events = EventBus()
        received: list[Event] = []

        async def capture(event: Event) -> None:
            received.append(event)

        events.subscribe(capture)
        machine = StateMachine(events)

        await machine.transition_to(PetState.IDLE)

        assert machine.state is PetState.IDLE
        assert received[0].type is EventType.STATE_CHANGED
        assert received[0].payload == {"previous": "starting", "state": "idle"}

    asyncio.run(scenario())
