import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from desk_pet.agent.client import Message, OpenAIModelClient
from desk_pet.agent.tool_protocol import MCPConnectorTool, ModelTool, ToolSchema


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
        tools: list[ModelTool],
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


def test_openai_client_adds_hosted_web_search_when_enabled() -> None:
    responses = FakeResponsesAPI()
    client = OpenAIModelClient(
        model="test-model",
        reasoning_effort="low",
        request_timeout_seconds=10,
        maximum_output_tokens=250,
        web_search_enabled=True,
        web_search_context_size="medium",
        responses=responses,
    )

    asyncio.run(client.create_response([{"role": "user", "content": "Toronto weather"}], []))

    assert responses.arguments["tools"] == [{"type": "web_search", "search_context_size": "medium"}]


def test_openai_client_adds_configured_connector_tools() -> None:
    responses = FakeResponsesAPI()
    connector = MCPConnectorTool(
        type="mcp",
        server_label="google_calendar",
        server_description="Read the calendar.",
        connector_id="connector_googlecalendar",
        authorization="secret-token",
        require_approval="never",
        allowed_tools=["search_events", "read_event"],
    )
    client = OpenAIModelClient(
        model="test-model",
        reasoning_effort="low",
        request_timeout_seconds=10,
        maximum_output_tokens=250,
        connector_tools=[connector],
        responses=responses,
    )

    asyncio.run(client.create_response([{"role": "user", "content": "Today?"}], []))

    assert responses.arguments["tools"] == [connector]


def test_openai_client_reloads_connector_tools_for_every_request() -> None:
    responses = FakeResponsesAPI()
    calls = 0

    async def load_connectors() -> list[MCPConnectorTool]:
        nonlocal calls
        calls += 1
        return [
            MCPConnectorTool(
                type="mcp",
                server_label="gmail",
                server_description="Read mail.",
                connector_id="connector_gmail",
                authorization=f"token-{calls}",
                require_approval="never",
                allowed_tools=["search_emails"],
            )
        ]

    client = OpenAIModelClient(
        model="test-model",
        reasoning_effort="low",
        request_timeout_seconds=10,
        maximum_output_tokens=250,
        connector_loader=load_connectors,
        responses=responses,
    )

    asyncio.run(client.create_response([{"role": "user", "content": "Mail?"}], []))
    first_token = responses.arguments["tools"][0]["authorization"]
    asyncio.run(client.create_response([{"role": "user", "content": "Again?"}], []))

    assert calls == 2
    assert first_token == "token-1"
    assert responses.arguments["tools"][0]["authorization"] == "token-2"


def test_openai_client_uses_supplied_runtime_instructions() -> None:
    responses = FakeResponsesAPI()
    client = OpenAIModelClient(
        model="test-model",
        reasoning_effort="low",
        request_timeout_seconds=10,
        maximum_output_tokens=250,
        instructions="DeskBob runtime context",
        clock=lambda: datetime(
            2026,
            7,
            27,
            23,
            5,
            tzinfo=timezone(timedelta(hours=-4), "EDT"),
        ),
        responses=responses,
    )

    asyncio.run(client.create_response([{"role": "user", "content": "Hello"}], []))

    instructions = responses.arguments["instructions"]
    assert instructions.startswith("DeskBob runtime context")
    assert "Monday, July 27, 2026 at 11:05:00 PM EDT (UTC-04:00)" in instructions
    assert "tomorrow" in instructions


def test_openai_client_refreshes_local_time_context_each_model_turn() -> None:
    responses = FakeResponsesAPI()
    current = datetime(
        2026,
        7,
        27,
        23,
        59,
        tzinfo=timezone(timedelta(hours=-4), "EDT"),
    )

    def clock() -> datetime:
        nonlocal current
        value = current
        current += timedelta(minutes=2)
        return value

    client = OpenAIModelClient(
        model="test-model",
        reasoning_effort="low",
        request_timeout_seconds=10,
        maximum_output_tokens=250,
        clock=clock,
        responses=responses,
    )

    asyncio.run(client.create_response([{"role": "user", "content": "Tomorrow?"}], []))
    assert "Monday, July 27, 2026 at 11:59:00 PM" in responses.arguments["instructions"]

    asyncio.run(client.create_response([{"role": "user", "content": "Tomorrow?"}], []))
    assert "Tuesday, July 28, 2026 at 12:01:00 AM" in responses.arguments["instructions"]
