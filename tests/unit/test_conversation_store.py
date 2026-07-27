import asyncio
from pathlib import Path

from desk_pet.memory.conversation_store import ConversationStore


def test_conversation_survives_store_restart(tmp_path: Path) -> None:
    async def scenario() -> None:
        database_path = tmp_path / "desk_pet.db"
        first_store = ConversationStore(database_path)
        await first_store.initialize()
        await first_store.append("Hello", "Hi there!")

        restarted_store = ConversationStore(database_path)
        await restarted_store.initialize()
        turns = await restarted_store.recent(20)

        assert len(turns) == 1
        assert turns[0].user_text == "Hello"
        assert turns[0].assistant_text == "Hi there!"

    asyncio.run(scenario())


def test_recent_returns_limited_turns_in_conversation_order(tmp_path: Path) -> None:
    async def scenario() -> None:
        store = ConversationStore(tmp_path / "desk_pet.db")
        await store.initialize()
        await store.append("one", "first")
        await store.append("two", "second")
        await store.append("three", "third")

        turns = await store.recent(2)

        assert [turn.user_text for turn in turns] == ["two", "three"]

    asyncio.run(scenario())
