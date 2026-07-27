import asyncio
import json
from typing import Any

import pytest

from desk_pet.agent.client import Message
from desk_pet.agent.loop import AgentLoop, AgentLoopError
from desk_pet.agent.tool_protocol import ModelTurn, ToolCall
from desk_pet.skills.registry import SkillDefinition, SkillRegistry, reject_unknown_arguments
from tests.fakes.agent import FakeResponseModelClient


def tool_turn(call_id: str, arguments: str = '{"value":1}') -> ModelTurn:
    item = {
        "type": "function_call",
        "call_id": call_id,
        "name": "test_skill",
        "arguments": arguments,
    }
    return ModelTurn(
        output_items=[item],
        output_text="",
        tool_calls=[ToolCall(call_id, "test_skill", arguments)],
    )


def final_turn(text: str = "Done.") -> ModelTurn:
    return ModelTurn(
        output_items=[{"type": "message", "role": "assistant", "content": text}],
        output_text=text,
        tool_calls=[],
    )


def create_counting_registry(counter: list[dict[str, Any]]) -> SkillRegistry:
    def validate(arguments: dict[str, Any]) -> None:
        reject_unknown_arguments(arguments, {"value"})
        if set(arguments) != {"value"} or not isinstance(arguments["value"], int):
            raise AssertionError("value must be an integer")

    async def execute(arguments: dict[str, Any]) -> dict[str, Any]:
        counter.append(arguments)
        return {"ok": True}

    registry = SkillRegistry()
    registry.register(
        SkillDefinition(
            name="test_skill",
            description="A deterministic test skill.",
            parameters={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
                "additionalProperties": False,
            },
            validate=validate,
            execute=execute,
        )
    )
    return registry


def test_loop_executes_tool_and_returns_final_text() -> None:
    async def scenario() -> None:
        counter: list[dict[str, Any]] = []
        requested: list[str] = []

        async def on_tool(name: str) -> None:
            requested.append(name)

        model = FakeResponseModelClient([tool_turn("call-1"), final_turn("Finished.")])
        loop = AgentLoop(
            model=model,
            skills=create_counting_registry(counter),
            on_tool_requested=on_tool,
        )

        result = await loop.complete([Message("user", "Run it")])

        assert result == "Finished."
        assert counter == [{"value": 1}]
        assert requested == ["test_skill"]
        assert model.requests[1][-1] == {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": '{"ok":true}',
        }

    asyncio.run(scenario())


def test_duplicate_call_is_not_executed_twice() -> None:
    async def scenario() -> None:
        counter: list[dict[str, Any]] = []
        model = FakeResponseModelClient([tool_turn("call-1"), tool_turn("call-2"), final_turn()])
        loop = AgentLoop(model=model, skills=create_counting_registry(counter))

        await loop.complete([Message("user", "Run it twice")])

        assert counter == [{"value": 1}]
        duplicate_output = json.loads(str(model.requests[2][-1]["output"]))
        assert duplicate_output["error"] == "duplicate_tool_call"

    asyncio.run(scenario())


def test_invalid_arguments_are_returned_to_model() -> None:
    async def scenario() -> None:
        counter: list[dict[str, Any]] = []
        model = FakeResponseModelClient([tool_turn("call-1", "not-json"), final_turn("Recovered.")])
        loop = AgentLoop(model=model, skills=create_counting_registry(counter))

        result = await loop.complete([Message("user", "Run it")])

        assert result == "Recovered."
        assert counter == []
        error_output = json.loads(str(model.requests[1][-1]["output"]))
        assert error_output["error"] == "invalid_arguments"

    asyncio.run(scenario())


def test_loop_stops_after_maximum_tool_iterations() -> None:
    async def scenario() -> None:
        counter: list[dict[str, Any]] = []
        turns = [tool_turn(f"call-{index}", json.dumps({"value": index})) for index in range(1, 7)]
        loop = AgentLoop(
            model=FakeResponseModelClient(turns),
            skills=create_counting_registry(counter),
            maximum_tool_iterations=5,
        )

        with pytest.raises(AgentLoopError, match="exceeded 5"):
            await loop.complete([Message("user", "Never stop")])

        assert len(counter) == 5

    asyncio.run(scenario())
