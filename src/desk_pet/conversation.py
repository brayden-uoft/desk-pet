from __future__ import annotations

import asyncio
import logging

from desk_pet.agent.client import Message, ModelClient
from desk_pet.memory.conversation_store import ConversationStore

LOGGER = logging.getLogger(__name__)


class ConversationError(RuntimeError):
    """A user-facing conversation failure."""


class ConversationService:
    def __init__(
        self,
        *,
        model: ModelClient,
        store: ConversationStore,
        history_limit: int,
        request_timeout_seconds: float,
    ) -> None:
        self._model = model
        self._store = store
        self._history_limit = history_limit
        self._request_timeout_seconds = request_timeout_seconds

    async def initialize(self) -> None:
        try:
            await self._store.initialize()
        except Exception as exc:
            LOGGER.exception("Could not initialize conversation storage")
            raise ConversationError("I couldn't open my conversation history.") from exc

    async def reply(self, user_text: str) -> str:
        user_text = user_text.strip()
        if not user_text:
            raise ConversationError("Please type a message before sending.")

        try:
            history = await self._store.recent(self._history_limit)
        except Exception as exc:
            LOGGER.exception("Could not read conversation history")
            raise ConversationError("I couldn't read my conversation history.") from exc
        messages: list[Message] = []
        for turn in history:
            messages.extend(
                [
                    Message("user", turn.user_text),
                    Message("assistant", turn.assistant_text),
                ]
            )
        messages.append(Message("user", user_text))

        try:
            assistant_text = await asyncio.wait_for(
                self._model.complete(messages),
                timeout=self._request_timeout_seconds,
            )
        except TimeoutError as exc:
            LOGGER.warning("Model request timed out")
            raise ConversationError("I couldn't get a response in time. Please try again.") from exc
        except Exception as exc:
            LOGGER.exception("Model request failed")
            raise ConversationError(
                "I couldn't reach the AI service. Check your connection and API key."
            ) from exc

        try:
            await self._store.append(user_text, assistant_text)
        except Exception as exc:
            LOGGER.exception("Could not save conversation turn")
            raise ConversationError("I got a response, but couldn't save it.") from exc
        return assistant_text
