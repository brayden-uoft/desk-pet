import asyncio
from collections.abc import Sequence
from pathlib import Path

from desk_pet.agent.client import Message
from desk_pet.conversation import ConversationService
from desk_pet.main import DeskPetApplication
from desk_pet.memory.conversation_store import ConversationStore
from tests.fakes.agent import FakeModelClient
from tests.fakes.hardware import FakeFace, FakeTrigger


def test_text_question_runs_complete_interaction_loop(tmp_path: Path) -> None:
    async def scenario() -> None:
        face = FakeFace()
        output: list[str] = []
        conversation = ConversationService(
            model=FakeModelClient(["A deterministic answer."]),
            store=ConversationStore(tmp_path / "desk_pet.db"),
            history_limit=20,
            request_timeout_seconds=1,
        )
        app = DeskPetApplication(
            FakeTrigger(["listen", "exit"]),
            face,
            conversation=conversation,
            text_input=lambda prompt: "What can you do?",
            output=output.append,
        )

        await app.run()

        assert face.states == ["idle", "listening", "thinking", "speaking", "idle"]
        assert output == ["Desk Pet> A deterministic answer."]
        assert app.state.state == "idle"

    asyncio.run(scenario())


def test_model_failure_shows_error_and_returns_to_idle(tmp_path: Path) -> None:
    class FailingModel:
        async def complete(self, messages: Sequence[Message]) -> str:
            raise RuntimeError("network unavailable")

    async def scenario() -> None:
        face = FakeFace()
        output: list[str] = []
        conversation = ConversationService(
            model=FailingModel(),
            store=ConversationStore(tmp_path / "desk_pet.db"),
            history_limit=20,
            request_timeout_seconds=1,
        )
        app = DeskPetApplication(
            FakeTrigger(["listen", "exit"]),
            face,
            conversation=conversation,
            text_input=lambda prompt: "Hello?",
            output=output.append,
        )

        await app.run()

        assert face.states == ["idle", "listening", "thinking", "error", "idle"]
        assert output == [
            "Desk Pet> I couldn't reach the AI service. Check your connection and API key."
        ]
        assert app.state.state == "idle"

    asyncio.run(scenario())
