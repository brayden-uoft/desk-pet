from collections.abc import Sequence
from typing import Any

from desk_pet.agent.client import Message
from desk_pet.agent.tool_protocol import ModelTurn, ToolSchema


class FakeModelClient:
    def __init__(self, responses: Sequence[str]) -> None:
        self._responses = iter(responses)
        self.requests: list[list[Message]] = []

    async def complete(self, messages: Sequence[Message]) -> str:
        self.requests.append(list(messages))
        return next(self._responses)


class FakeResponseModelClient:
    def __init__(self, turns: Sequence[ModelTurn]) -> None:
        self._turns = iter(turns)
        self.requests: list[list[dict[str, Any]]] = []
        self.tools: list[list[ToolSchema]] = []

    async def create_response(
        self,
        input_items: Sequence[dict[str, Any]],
        tools: Sequence[ToolSchema],
    ) -> ModelTurn:
        self.requests.append([dict(item) for item in input_items])
        self.tools.append(list(tools))
        return next(self._turns)
