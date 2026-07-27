from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from openai import AsyncOpenAI

from desk_pet.agent.prompts import DESK_PET_INSTRUCTIONS
from desk_pet.agent.tool_protocol import ModelTurn, ToolCall, ToolSchema


@dataclass(frozen=True, slots=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


class ModelClient(Protocol):
    async def complete(self, messages: Sequence[Message]) -> str:
        """Return one final text response."""


class ResponseModelClient(Protocol):
    async def create_response(
        self,
        input_items: Sequence[dict[str, Any]],
        tools: Sequence[ToolSchema],
    ) -> ModelTurn:
        """Return model output items, text, and any requested tool calls."""


class _ResponseOutputItem(Protocol):
    def to_dict(self) -> dict[str, Any]: ...


class _ResponseResult(Protocol):
    @property
    def output_text(self) -> str: ...

    @property
    def output(self) -> Sequence[_ResponseOutputItem]: ...


class _ResponsesAPI(Protocol):
    async def create(
        self,
        *,
        model: str,
        instructions: str,
        input: list[dict[str, Any]],
        tools: list[ToolSchema],
        parallel_tool_calls: bool,
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

    async def create_response(
        self,
        input_items: Sequence[dict[str, Any]],
        tools: Sequence[ToolSchema],
    ) -> ModelTurn:
        response = await self._responses.create(
            model=self._model,
            instructions=DESK_PET_INSTRUCTIONS,
            input=list(input_items),
            tools=list(tools),
            parallel_tool_calls=False,
            reasoning={"effort": self._reasoning_effort},
            max_output_tokens=self._maximum_output_tokens,
            store=False,
        )
        output_items = [item.to_dict() for item in response.output]
        tool_calls = [
            ToolCall(
                call_id=str(item["call_id"]),
                name=str(item["name"]),
                arguments=str(item["arguments"]),
            )
            for item in output_items
            if item.get("type") == "function_call"
        ]
        return ModelTurn(
            output_items=output_items,
            output_text=response.output_text.strip(),
            tool_calls=tool_calls,
        )
