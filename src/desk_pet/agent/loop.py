from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from desk_pet.agent.client import Message, ResponseModelClient
from desk_pet.agent.tool_protocol import ToolOutput
from desk_pet.skills.registry import SkillError, SkillRegistry

LOGGER = logging.getLogger(__name__)

ToolCallback = Callable[[str], Awaitable[None]]


class AgentLoopError(RuntimeError):
    """The controlled model/tool loop could not produce a final response."""


class AgentLoop:
    def __init__(
        self,
        *,
        model: ResponseModelClient,
        skills: SkillRegistry,
        maximum_tool_iterations: int = 5,
        on_tool_requested: ToolCallback | None = None,
    ) -> None:
        self._model = model
        self._skills = skills
        self._maximum_tool_iterations = maximum_tool_iterations
        self._on_tool_requested = on_tool_requested

    async def complete(self, messages: Sequence[Message]) -> str:
        input_items: list[dict[str, Any]] = [
            {"role": message.role, "content": message.content} for message in messages
        ]
        seen_calls: set[str] = set()
        tool_call_count = 0

        for _ in range(self._maximum_tool_iterations + 1):
            turn = await self._model.create_response(input_items, self._skills.schemas())
            input_items.extend(turn.output_items)

            if not turn.tool_calls:
                if turn.output_text:
                    return turn.output_text
                raise AgentLoopError("The model returned neither text nor a tool request")

            for call in turn.tool_calls:
                tool_call_count += 1
                if tool_call_count > self._maximum_tool_iterations:
                    raise AgentLoopError(
                        f"Tool loop exceeded {self._maximum_tool_iterations} iterations"
                    )

                fingerprint = self._fingerprint(call.name, call.arguments)
                if fingerprint in seen_calls:
                    LOGGER.warning("Rejected duplicate tool call: %s", call.name)
                    output: ToolOutput = json.dumps(
                        {
                            "ok": False,
                            "error": "duplicate_tool_call",
                            "message": f"Duplicate call to {call.name} was not executed.",
                        }
                    )
                else:
                    seen_calls.add(fingerprint)
                    if self._on_tool_requested is not None:
                        await self._on_tool_requested(call.name)
                    try:
                        output = await self._skills.execute(call.name, call.arguments)
                    except SkillError as exc:
                        output = json.dumps(
                            {
                                "ok": False,
                                "error": exc.code,
                                "message": str(exc),
                            }
                        )

                input_items.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": output,
                    }
                )

        raise AgentLoopError("Tool loop terminated without a final response")

    @staticmethod
    def _fingerprint(name: str, arguments: str) -> str:
        try:
            normalized = json.dumps(json.loads(arguments), sort_keys=True, separators=(",", ":"))
        except json.JSONDecodeError:
            normalized = arguments
        return hashlib.sha256(f"{name}\0{normalized}".encode()).hexdigest()
