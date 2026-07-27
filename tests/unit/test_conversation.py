import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest

from desk_pet.agent.client import Message
from desk_pet.conversation import ConversationError, ConversationService
from desk_pet.memory.conversation_store import ConversationStore
from tests.fakes.agent import FakeModelClient


def test_reply_includes_history_and_persists_result(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = ConversationStore(tmp_path / "desk_pet.db")
        await store.initialize()
        await store.append("My name is Brayden.", "Nice to meet you, Brayden.")
        model = FakeModelClient(["You told me your name is Brayden."])
        conversation = ConversationService(
            model=model,
            store=store,
            history_limit=20,
            request_timeout_seconds=1,
        )

        response = await conversation.reply("What is my name?")

        assert response == "You told me your name is Brayden."
        assert model.requests == [
            [
                Message("user", "My name is Brayden."),
                Message("assistant", "Nice to meet you, Brayden."),
                Message("user", "What is my name?"),
            ]
        ]
        turns = await store.recent(20)
        assert len(turns) == 2
        assert turns[-1].assistant_text == response

    asyncio.run(scenario())


def test_timeout_is_user_friendly_and_does_not_store_turn(tmp_path: Path) -> None:
    class SlowModel:
        async def complete(self, messages: Sequence[Message]) -> str:
            await asyncio.sleep(0.1)
            return "too late"

    async def scenario() -> None:
        store = ConversationStore(tmp_path / "desk_pet.db")
        await store.initialize()
        conversation = ConversationService(
            model=SlowModel(),
            store=store,
            history_limit=20,
            request_timeout_seconds=0.01,
        )

        with pytest.raises(ConversationError, match="response in time"):
            await conversation.reply("Hello?")

        assert await store.recent(20) == []

    asyncio.run(scenario())
