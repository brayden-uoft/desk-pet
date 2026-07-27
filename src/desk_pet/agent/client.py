from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from openai import AsyncOpenAI

from desk_pet.agent.prompts import DESK_PET_INSTRUCTIONS


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


class ModelClient(Protocol):
    async def complete(self, messages: Sequence[Message]) -> str:
        """Return one final text response."""


class _ResponseResult(Protocol):
    @property
    def output_text(self) -> str: ...


class _ResponsesAPI(Protocol):
    async def create(
        self,
        *,
        model: str,
        instructions: str,
        input: list[dict[str, str]],
        reasoning: dict[str, str],
        max_output_tokens: int,
        store: bool,
    ) -> _ResponseResult: ...


class OpenAIModelClient:
    def __init__(
        self,
        *,
        model: str,
        reasoning_effort: str,
        request_timeout_seconds: float,
        maximum_output_tokens: int,
        responses: _ResponsesAPI | None = None,
    ) -> None:
        if responses is None:
            sdk = AsyncOpenAI(timeout=request_timeout_seconds, max_retries=1)
            responses = cast(_ResponsesAPI, sdk.responses)
        self._responses = responses
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._maximum_output_tokens = maximum_output_tokens

    async def complete(self, messages: Sequence[Message]) -> str:
        response = await self._responses.create(
            model=self._model,
            instructions=DESK_PET_INSTRUCTIONS,
            input=[{"role": item.role, "content": item.content} for item in messages],
            reasoning={"effort": self._reasoning_effort},
            max_output_tokens=self._maximum_output_tokens,
            store=False,
        )
        text = response.output_text.strip()
        if not text:
            raise RuntimeError("The model returned an empty response")
        return text
