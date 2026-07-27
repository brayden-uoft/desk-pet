from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from desk_pet.memory.database import connect

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL
)
"""


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    id: int
    created_at: str
    user_text: str
    assistant_text: str


class ConversationStore:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        with connect(self._database_path) as connection:
            connection.execute(_SCHEMA)

    async def append(self, user_text: str, assistant_text: str) -> None:
        await asyncio.to_thread(self._append_sync, user_text, assistant_text)

    def _append_sync(self, user_text: str, assistant_text: str) -> None:
        with connect(self._database_path) as connection:
            connection.execute(
                """
                INSERT INTO conversations (created_at, user_text, assistant_text)
                VALUES (?, ?, ?)
                """,
                (datetime.now(UTC).isoformat(), user_text, assistant_text),
            )

    async def recent(self, limit: int) -> list[ConversationTurn]:
        return await asyncio.to_thread(self._recent_sync, limit)

    def _recent_sync(self, limit: int) -> list[ConversationTurn]:
        with connect(self._database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, created_at, user_text, assistant_text
                FROM (
                    SELECT id, created_at, user_text, assistant_text
                    FROM conversations
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (limit,),
            ).fetchall()
        return [
            ConversationTurn(
                id=int(row["id"]),
                created_at=str(row["created_at"]),
                user_text=str(row["user_text"]),
                assistant_text=str(row["assistant_text"]),
            )
            for row in rows
        ]
