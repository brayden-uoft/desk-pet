import asyncio
from typing import Any

from desk_pet.agent.client import Message, OpenAIModelClient


class FakeResponse:
    output_text = "  Hello from the pet.  "


class FakeResponsesAPI:
    def __init__(self) -> None:
        self.arguments: dict[str, Any] = {}

    async def create(
        self,
        *,
        model: str,
        instructions: str,
        input: list[dict[str, str]],
        reasoning: dict[str, str],
        max_output_tokens: int,
        store: bool,
    ) -> FakeResponse:
        self.arguments = {
            "model": model,
            "instructions": instructions,
            "input": input,
            "reasoning": reasoning,
            "max_output_tokens": max_output_tokens,
            "store": store,
        }
        return FakeResponse()


def test_openai_client_uses_responses_api_without_remote_storage() -> None:
    responses = FakeResponsesAPI()
    client = OpenAIModelClient(
        model="test-model",
        reasoning_effort="low",
        request_timeout_seconds=10,
        maximum_output_tokens=250,
        responses=responses,
    )

    result = asyncio.run(
        client.complete(
            [
                Message("user", "Hello"),
                Message("assistant", "Hi"),
                Message("user", "How are you?"),
            ]
        )
    )

    assert result == "Hello from the pet."
    assert responses.arguments["model"] == "test-model"
    assert responses.arguments["reasoning"] == {"effort": "low"}
    assert responses.arguments["store"] is False
    assert responses.arguments["input"] == [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
        {"role": "user", "content": "How are you?"},
    ]
