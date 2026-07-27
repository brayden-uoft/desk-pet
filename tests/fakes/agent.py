from collections.abc import Sequence

from desk_pet.agent.client import Message


class FakeModelClient:
    def __init__(self, responses: Sequence[str]) -> None:
        self._responses = iter(responses)
        self.requests: list[list[Message]] = []

    async def complete(self, messages: Sequence[Message]) -> str:
        self.requests.append(list(messages))
        return next(self._responses)
