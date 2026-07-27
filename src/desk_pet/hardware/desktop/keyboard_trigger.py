from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from functools import partial
from typing import Any, cast

KeyState = tuple[bool, bool]
WINDOWS_VIRTUAL_KEYS = {
    "space": 0x20,
    "left_alt": 0xA4,
    "right_alt": 0xA5,
    "escape": 0x1B,
    "f13": 0x7C,
}


def windows_virtual_key(name: str) -> int:
    try:
        return WINDOWS_VIRTUAL_KEYS[name]
    except KeyError:
        supported = ", ".join(sorted(WINDOWS_VIRTUAL_KEYS))
        raise ValueError(f"Unsupported Windows key {name!r}; choose one of: {supported}") from None


def _poll_windows_keys(listen_virtual_key: int, cancel_virtual_key: int) -> KeyState:
    import ctypes

    user32 = cast(Any, ctypes).windll.user32
    listen_pressed = bool(user32.GetAsyncKeyState(listen_virtual_key) & 0x8000)
    cancel_pressed = bool(user32.GetAsyncKeyState(cancel_virtual_key) & 0x8000)
    return listen_pressed, cancel_pressed


class KeyboardTrigger:
    def __init__(
        self,
        key_reader: Callable[[], KeyState] | None = None,
        *,
        listen_key: str = "space",
        cancel_key: str = "escape",
        poll_interval_seconds: float = 0.02,
    ) -> None:
        if key_reader is None and sys.platform != "win32":
            raise RuntimeError("The Stage 1 keyboard adapter currently requires Windows")
        if key_reader is None:
            try:
                listen_virtual_key = windows_virtual_key(listen_key)
                cancel_virtual_key = windows_virtual_key(cancel_key)
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            key_reader = partial(
                _poll_windows_keys,
                listen_virtual_key,
                cancel_virtual_key,
            )
        self._key_reader = key_reader
        self._poll_interval_seconds = poll_interval_seconds
        self._listen_pressed = False
        self._cancel_pressed = False

    async def wait_for_trigger(self) -> str:
        while True:
            listen_pressed, cancel_pressed = self._key_reader()
            action: str | None = None
            if cancel_pressed and not self._cancel_pressed:
                action = "exit"
            elif listen_pressed and not self._listen_pressed:
                action = "listen_start"
            elif not listen_pressed and self._listen_pressed:
                action = "listen_stop"
            self._listen_pressed = listen_pressed
            self._cancel_pressed = cancel_pressed
            if action is not None:
                return action
            await asyncio.sleep(self._poll_interval_seconds)
