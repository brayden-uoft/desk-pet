import asyncio
from typing import Any

from desk_pet.agent.client import Message, OpenAIModelClient
from desk_pet.agent.tool_protocol import ToolSchema


class FakeOutputItem:
    def __init__(self, value: dict[str, Any]) -> None:
        self._value = value

    def to_dict(self) -> dict[str, Any]:
        return dict(self._value)


class FakeResponse:
    output_text = ""
    output = [
        FakeOutputItem(
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "get_current_time",
                "arguments": "{}",
            }
        )
    ]


class FakeResponsesAPI:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

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
    ) -> FakeResponse:
        self.arguments = {
            "model": model,
            "instructions": instructions,
            "input": input,
            "tools": tools,
            "parallel_tool_calls": parallel_tool_calls,
            "reasoning": reasoning,
            "max_output_tokens": max_output_tokens,
            "store": store,
        }
        return FakeResponse()


def test_openai_client_preserves_function_calls_and_disables_parallel_tools() -> None:
    responses = FakeResponsesAPI()
    client = OpenAIModelClient(
        model="test-model",
        reasoning_effort="low",
        request_timeout_seconds=10,
        maximum_output_tokens=250,
        responses=responses,
    )
    tools = [
        ToolSchema(
            type="function",
            name="get_current_time",
            description="Get time",
            strict=True,
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        )
    ]

    result = asyncio.run(
        client.create_response(
            [{"role": Message("user", "What time is it?").role, "content": "What time is it?"}],
            tools,
        )
    )

    assert result.output_text == ""
    assert result.tool_calls[0].call_id == "call-1"
    assert result.tool_calls[0].name == "get_current_time"
    assert result.output_items == [
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "get_current_time",
            "arguments": "{}",
        }
    ]
    assert responses.arguments["parallel_tool_calls"] is False
    assert responses.arguments["store"] is False
    assert responses.arguments["tools"] == tools
