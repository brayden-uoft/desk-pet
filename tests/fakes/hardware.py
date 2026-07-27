from collections.abc import Iterable


class FakeTrigger:
    def __init__(self, actions: Iterable[str]) -> None:
        self._actions = iter(actions)

    async def wait_for_trigger(self) -> str:
        return next(self._actions)


class FakeFace:
    def __init__(self) -> None:
        self.states: list[str] = []

    async def set_state(self, state: str) -> None:
        self.states.append(state)
