from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, cast, runtime_checkable

from openai import AsyncOpenAI

from desk_pet.agent.prompts import DESK_PET_INSTRUCTIONS
from desk_pet.agent.tool_protocol import (
    MCPTool,
    ModelTool,
    ModelTurn,
    ToolCall,
    ToolSchema,
    WebSearchTool,
)
from desk_pet.agent.tool_routing import should_offer_external_tools

LOGGER = logging.getLogger(__name__)
_MISSING_CONNECTOR_PATTERN = re.compile(r"Connector with ID '([^']+)' not found")


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


TextDeltaCallback = Callable[[str], Awaitable[None]]


@runtime_checkable
class StreamingResponseModelClient(Protocol):
    async def create_response_stream(
        self,
        input_items: Sequence[dict[str, Any]],
        tools: Sequence[ToolSchema],
        on_text_delta: TextDeltaCallback,
    ) -> ModelTurn:
        """Stream text deltas and return the completed model turn."""


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
        tools: list[ModelTool],
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
        web_search_enabled: bool = False,
        web_search_context_size: Literal["low", "medium", "high"] = "low",
        connector_tools: Sequence[MCPTool] = (),
        connector_loader: Callable[[], Awaitable[Sequence[MCPTool]]] | None = None,
        instructions: str = DESK_PET_INSTRUCTIONS,
        clock: Callable[[], datetime] | None = None,
        sdk: AsyncOpenAI | None = None,
        responses: _ResponsesAPI | None = None,
    ) -> None:
        if responses is None:
            client = sdk or AsyncOpenAI(timeout=request_timeout_seconds, max_retries=1)
            responses = cast(_ResponsesAPI, client.responses)
        self._responses = responses
        self._model = model
        self._reasoning_effort = reasoning_effort
        self._maximum_output_tokens = maximum_output_tokens
        self._web_search_enabled = web_search_enabled
        self._web_search_context_size = web_search_context_size
        self._connector_tools = list(connector_tools)
        self._connector_loader = connector_loader
        self._instructions = instructions
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._unavailable_connector_ids: set[str] = set()

    async def create_response(
        self,
        input_items: Sequence[dict[str, Any]],
        tools: Sequence[ToolSchema],
    ) -> ModelTurn:
        model_tools = await self._model_tools(input_items, tools)
        try:
            response = await self._request(input_items, model_tools)
        except Exception as exc:
            connector_id = _missing_connector_id(exc)
            if connector_id is None:
                raise
            filtered_tools = self._without_connector(model_tools, connector_id)
            if len(filtered_tools) == len(model_tools):
                raise
            self._mark_connector_unavailable(connector_id)
            response = await self._request(input_items, filtered_tools)
        return self._model_turn(
            [item.to_dict() for item in response.output],
            response.output_text,
        )

    async def create_response_stream(
        self,
        input_items: Sequence[dict[str, Any]],
        tools: Sequence[ToolSchema],
        on_text_delta: TextDeltaCallback,
    ) -> ModelTurn:
        model_tools = await self._model_tools(input_items, tools)
        try:
            return await self._request_stream(input_items, model_tools, on_text_delta)
        except Exception as exc:
            connector_id = _missing_connector_id(exc)
            if connector_id is None:
                raise
            filtered_tools = self._without_connector(model_tools, connector_id)
            if len(filtered_tools) == len(model_tools):
                raise
            self._mark_connector_unavailable(connector_id)
            return await self._request_stream(input_items, filtered_tools, on_text_delta)

    async def _model_tools(
        self,
        input_items: Sequence[dict[str, Any]],
        tools: Sequence[ToolSchema],
    ) -> list[ModelTool]:
        model_tools: list[ModelTool] = list(tools)
        use_external_tools = should_offer_external_tools(input_items)
        if self._web_search_enabled and use_external_tools:
            model_tools.append(
                WebSearchTool(
                    type="web_search",
                    search_context_size=self._web_search_context_size,
                )
            )
        if use_external_tools:
            model_tools.extend(self._connector_tools)
            if self._connector_loader is not None:
                model_tools.extend(await self._connector_loader())
        model_tools = [
            tool
            for tool in model_tools
            if not (
                tool.get("type") == "mcp"
                and tool.get("connector_id") in self._unavailable_connector_ids
            )
        ]

        return model_tools

    @staticmethod
    def _model_turn(output_items: list[dict[str, Any]], output_text: str) -> ModelTurn:
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
            output_text=output_text.strip(),
            tool_calls=tool_calls,
        )

    @staticmethod
    def _without_connector(
        model_tools: list[ModelTool], connector_id: str
    ) -> list[ModelTool]:
        return [
            tool
            for tool in model_tools
            if not (tool.get("type") == "mcp" and tool.get("connector_id") == connector_id)
        ]

    def _mark_connector_unavailable(self, connector_id: str) -> None:
        self._unavailable_connector_ids.add(connector_id)
        LOGGER.warning(
            "OpenAI connector %s is unavailable; continuing without it",
            connector_id,
        )

    async def _request(
        self,
        input_items: Sequence[dict[str, Any]],
        model_tools: list[ModelTool],
    ) -> _ResponseResult:
        return await self._responses.create(
            model=self._model,
            instructions=self._instructions + _local_time_instructions(self._clock()),
            input=list(input_items),
            tools=model_tools,
            parallel_tool_calls=False,
            reasoning={"effort": self._reasoning_effort},
            max_output_tokens=self._maximum_output_tokens,
            store=False,
        )

    async def _request_stream(
        self,
        input_items: Sequence[dict[str, Any]],
        model_tools: list[ModelTool],
        on_text_delta: TextDeltaCallback,
    ) -> ModelTurn:
        stream = await cast(Any, self._responses).create(
            model=self._model,
            instructions=self._instructions + _local_time_instructions(self._clock()),
            input=list(input_items),
            tools=model_tools,
            parallel_tool_calls=False,
            reasoning={"effort": self._reasoning_effort},
            max_output_tokens=self._maximum_output_tokens,
            store=False,
            stream=True,
        )
        output_items: list[dict[str, Any]] = []
        text_parts: list[str] = []
        async for event in stream:
            event_type = getattr(event, "type", "")
            if event_type == "response.output_text.delta":
                delta = str(event.delta)
                text_parts.append(delta)
                await on_text_delta(delta)
            elif event_type == "response.output_item.done":
                output_items.append(event.item.to_dict())
        return self._model_turn(output_items, "".join(text_parts))


def _local_time_instructions(now: datetime) -> str:
    local_now = now.astimezone() if now.tzinfo is None else now
    timezone_name = local_now.tzname() or "local time"
    return (
        "\n\nAuthoritative current local date and time: "
        f"{local_now.strftime('%A, %B %d, %Y at %I:%M:%S %p')} "
        f"{timezone_name} (UTC{local_now.strftime('%z')[:3]}:{local_now.strftime('%z')[3:]}). "
        "Resolve words such as today, tonight, tomorrow, and weekday names from this value. "
        "Use get_current_time when the exact current time is material."
    )


def _missing_connector_id(exc: Exception) -> str | None:
    match = _MISSING_CONNECTOR_PATTERN.search(str(exc))
    return match.group(1) if match else None
