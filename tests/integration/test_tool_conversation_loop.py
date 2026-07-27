import asyncio
from datetime import UTC, datetime
from pathlib import Path

from desk_pet.agent.loop import AgentLoop
from desk_pet.agent.tool_protocol import ModelTurn, ToolCall
from desk_pet.conversation import ConversationService
from desk_pet.events import Event, EventType
from desk_pet.main import DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from desk_pet.skills.current_time import create_current_time_skill
from desk_pet.skills.registry import SkillRegistry
from tests.fakes.agent import FakeResponseModelClient
from tests.fakes.hardware import FakeFace, FakeTrigger


def test_tool_request_transitions_through_using_tool(tmp_path: Path) -> None:
    async def scenario() -> None:
        face = FakeFace()
        output: list[str] = []
        registry = SkillRegistry()
        registry.register(
            create_current_time_skill(lambda: datetime(2026, 7, 27, 12, 0, tzinfo=UTC))
        )
        tool_item = {
            "type": "function_call",
            "call_id": "call-time",
            "name": "get_current_time",
            "arguments": "{}",
        }
        model = FakeResponseModelClient(
            [
                ModelTurn(
                    output_items=[tool_item],
                    output_text="",
                    tool_calls=[ToolCall("call-time", "get_current_time", "{}")],
                ),
                ModelTurn(
                    output_items=[
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": "It is noon.",
                        }
                    ],
                    output_text="It is noon.",
                    tool_calls=[],
                ),
            ]
        )

        app = DeskPetApplication(
            FakeTrigger(["listen", "exit"]),
            face,
            text_input=lambda prompt: "What time is it?",
            output=output.append,
        )

        async def on_tool_requested(name: str) -> None:
            await app.events.emit(Event.create(EventType.TOOL_REQUESTED, name=name))

        agent = AgentLoop(
            model=model,
            skills=registry,
            on_tool_requested=on_tool_requested,
        )
        app.conversation = ConversationService(
            model=agent,
            store=ConversationStore(tmp_path / "desk_pet.db"),
            history_limit=20,
            request_timeout_seconds=1,
        )

        await app.run()

        assert face.states == [
            "idle",
            "listening",
            "thinking",
            "using_tool",
            "speaking",
            "idle",
        ]
        assert output == ["Desk Pet> It is noon."]

    asyncio.run(scenario())
