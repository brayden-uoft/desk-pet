import asyncio
import base64
import json
from pathlib import Path

from desk_pet.agent.loop import AgentLoop
from desk_pet.agent.tool_protocol import ModelTurn, ToolCall
from desk_pet.conversation import ConversationService
from desk_pet.events import Event, EventType
from desk_pet.main import DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from desk_pet.skills.registry import SkillRegistry
from desk_pet.skills.take_photo import create_camera_skill
from tests.fakes.agent import FakeResponseModelClient
from tests.fakes.hardware import (
    FakeCamera,
    FakeFace,
    FakePlayer,
    FakeRecorder,
    FakeSynthesizer,
    FakeTranscriber,
    QueueTrigger,
)


async def _wait_for_state_count(face: FakeFace, count: int) -> None:
    for _ in range(200):
        if len(face.states) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"Expected {count} states; saw {face.states!r}")


def test_voice_vision_question_captures_one_image_and_speaks_answer(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        trigger = QueueTrigger()
        face = FakeFace()
        output: list[str] = []
        camera = FakeCamera()
        synthesizer = FakeSynthesizer()
        player = FakePlayer()
        tool_item = {
            "type": "function_call",
            "call_id": "call-camera",
            "name": "capture_camera_image",
            "arguments": "{}",
        }
        model = FakeResponseModelClient(
            [
                ModelTurn(
                    output_items=[tool_item],
                    output_text="",
                    tool_calls=[
                        ToolCall(
                            "call-camera",
                            "capture_camera_image",
                            "{}",
                        )
                    ],
                ),
                ModelTurn(
                    output_items=[
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": "You're holding a red mug.",
                        }
                    ],
                    output_text="You're holding a red mug.",
                    tool_calls=[],
                ),
            ]
        )
        registry = SkillRegistry()
        registry.register(create_camera_skill(camera, image_detail="auto"))
        app = DeskPetApplication(
            trigger,
            face,
            output=output.append,
            interaction_mode="voice",
            recorder=FakeRecorder(),
            transcriber=FakeTranscriber("What am I holding?"),
            synthesizer=synthesizer,
            player=player,
        )

        async def on_tool_requested(name: str) -> None:
            await app.events.emit(Event.create(EventType.TOOL_REQUESTED, name=name))

        app.conversation = ConversationService(
            model=AgentLoop(
                model=model,
                skills=registry,
                on_tool_requested=on_tool_requested,
            ),
            store=ConversationStore(tmp_path / "desk_pet.db"),
            history_limit=20,
            request_timeout_seconds=1,
        )

        run_task = asyncio.create_task(app.run())
        await trigger.send("listen")
        await _wait_for_state_count(face, 7)
        await trigger.send("exit")
        await run_task

        assert face.states == [
            "idle",
            "listening",
            "transcribing",
            "thinking",
            "using_tool",
            "speaking",
            "idle",
        ]
        assert camera.calls == 1
        function_output = model.requests[1][-1]
        assert function_output["type"] == "function_call_output"
        assert function_output["call_id"] == "call-camera"
        content = function_output["output"]
        assert isinstance(content, list)
        assert json.loads(content[0]["text"])["ok"] is True
        prefix, encoded = content[1]["image_url"].split(",", 1)
        assert prefix == "data:image/jpeg;base64"
        assert base64.b64decode(encoded) == camera.jpeg
        assert synthesizer.texts == ["You're holding a red mug."]
        assert player.audio == [b"fake-speech-wav"]
        assert output == [
            "You> What am I holding?",
            "Desk Pet> You're holding a red mug.",
        ]
        assert not list(tmp_path.glob("*.jpg"))
        assert not list(tmp_path.glob("*.jpeg"))

    asyncio.run(scenario())
