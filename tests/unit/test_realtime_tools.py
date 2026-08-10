from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any, cast

from desk_pet.audio.realtime import OpenAIRealtimeVoice
from desk_pet.hardware.interfaces import CancellationToken
from desk_pet.skills.current_time import create_current_time_skill
from desk_pet.skills.registry import SkillRegistry


class FakeStreamingPlayer:
    async def play_pcm_stream(
        self,
        chunks: AsyncIterator[bytes],
        cancellation: CancellationToken,
        on_audio_started: Callable[[], None],
    ) -> None:
        started = False
        async for _chunk in chunks:
            if not started:
                started = True
                on_audio_started()


class FakeResponseResource:
    def __init__(self) -> None:
        self.create_count = 0

    async def create(self, **_arguments: Any) -> None:
        self.create_count += 1


class FakeConversationItem:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    async def create(self, *, item: dict[str, Any]) -> None:
        self.items.append(item)


class FakeConnection:
    def __init__(self, events: list[Any]) -> None:
        self.events = events
        self.response = FakeResponseResource()
        self.conversation = SimpleNamespace(item=FakeConversationItem())

    async def recv(self) -> Any:
        return self.events.pop(0)


def _event(event_type: str, **fields: Any) -> Any:
    return SimpleNamespace(type=event_type, **fields)


def test_realtime_executes_registered_skill_and_continues_same_response() -> None:
    async def scenario() -> None:
        registry = SkillRegistry()
        registry.register(create_current_time_skill())
        requested: list[str] = []
        voice = OpenAIRealtimeVoice(
            client=cast(Any, None),
            player=FakeStreamingPlayer(),
            model="realtime-test",
            voice="echo",
            speed=1.5,
            instructions="Test",
            prewarm=False,
            skills=registry,
            on_tool_requested=lambda name: _record(requested, name),
        )
        connection = FakeConnection(
            [
                _event("input_audio_buffer.committed", item_id="input-1"),
                _event(
                    "conversation.item.input_audio_transcription.completed",
                    item_id="input-1",
                    transcript="What time is it?",
                ),
                _event(
                    "response.function_call_arguments.done",
                    name="get_current_time",
                    arguments="{}",
                    call_id="call-1",
                ),
                _event(
                    "response.done",
                    response=SimpleNamespace(status="completed", status_details=None),
                ),
                _event(
                    "response.output_audio.delta",
                    delta=base64.b64encode(b"\x00\x00").decode(),
                ),
                _event("response.output_audio_transcript.delta", delta="It is noon."),
                _event(
                    "response.done",
                    response=SimpleNamespace(status="completed", status_details=None),
                ),
            ]
        )

        result = await voice._consume_response(  # noqa: SLF001
            connection,
            CancellationToken(),
            lambda: None,
            turn_started_at=1.0,
            committed_at=1.1,
        )

        assert requested == ["get_current_time"]
        assert connection.response.create_count == 1
        assert connection.conversation.item.items[0]["type"] == "function_call_output"
        assert result.assistant_transcript == "It is noon."
        assert result.user_transcript == "What time is it?"

    asyncio.run(scenario())


async def _record(target: list[str], name: str) -> None:
    target.append(name)


def test_realtime_session_advertises_registry_tools() -> None:
    registry = SkillRegistry()
    registry.register(create_current_time_skill())
    voice = OpenAIRealtimeVoice(
        client=cast(Any, None),
        player=FakeStreamingPlayer(),
        model="realtime-test",
        voice="echo",
        speed=1.5,
        instructions="Test",
        prewarm=False,
        skills=registry,
    )

    tool_names = {tool["name"] for tool in voice._session_config()["tools"]}  # noqa: SLF001
    assert tool_names == {"get_current_time", "delegate_to_full_agent"}
