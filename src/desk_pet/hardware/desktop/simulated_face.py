from __future__ import annotations

from collections.abc import Callable

_FACES = {
    "starting": "·     ·",
    "idle": "•     •",
    "listening": "◉     ◉",
    "transcribing": "•  ·  •",
    "thinking": "•  ·  •",
    "using_tool": "◉  ·  ◉",
    "speaking": "^     ^",
    "awaiting_confirmation": "?     ?",
    "muted": "—     —",
    "error": "×     ×",
}


class TerminalFace:
    def __init__(self, output: Callable[[str], None] = print) -> None:
        self._output = output

    async def set_state(self, state: str) -> None:
        face = _FACES.get(state, _FACES["error"])
        self._output(f"[{state.upper():>21}]  {face}")

    async def close(self) -> None:
        return None
