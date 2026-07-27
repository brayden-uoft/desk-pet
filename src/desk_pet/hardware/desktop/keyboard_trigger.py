from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from typing import Any, cast

KeyState = tuple[bool, bool]


def _poll_windows_keys() -> KeyState:
    import ctypes

    user32 = cast(Any, ctypes).windll.user32
    space_pressed = bool(user32.GetAsyncKeyState(0x20) & 0x8000)
    escape_pressed = bool(user32.GetAsyncKeyState(0x1B) & 0x8000)
    return space_pressed, escape_pressed


class KeyboardTrigger:
    def __init__(
        self,
        key_reader: Callable[[], KeyState] | None = None,
        *,
        poll_interval_seconds: float = 0.02,
    ) -> None:
        if key_reader is None and sys.platform != "win32":
            raise RuntimeError("The Stage 1 keyboard adapter currently requires Windows")
        self._key_reader = key_reader or _poll_windows_keys
        self._poll_interval_seconds = poll_interval_seconds
        self._space_pressed = False
        self._escape_pressed = False

    async def wait_for_trigger(self) -> str:
        while True:
            space_pressed, escape_pressed = self._key_reader()
            action: str | None = None
            if escape_pressed and not self._escape_pressed:
                action = "exit"
            elif space_pressed and not self._space_pressed:
                action = "listen_start"
            elif not space_pressed and self._space_pressed:
                action = "listen_stop"
            self._space_pressed = space_pressed
            self._escape_pressed = escape_pressed
            if action is not None:
                return action
            await asyncio.sleep(self._poll_interval_seconds)
