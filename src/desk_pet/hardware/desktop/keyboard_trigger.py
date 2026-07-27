from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable


def _read_windows_key() -> str:
    import msvcrt

    key = msvcrt.getwch()
    if key in {"\x00", "\xe0"}:
        msvcrt.getwch()
        return "unknown"
    if key == " ":
        return "listen"
    if key == "\x1b":
        return "exit"
    return "unknown"


class KeyboardTrigger:
    def __init__(self, key_reader: Callable[[], str] | None = None) -> None:
        if key_reader is None and sys.platform != "win32":
            raise RuntimeError("The Stage 1 keyboard adapter currently requires Windows")
        self._key_reader = key_reader or _read_windows_key

    async def wait_for_trigger(self) -> str:
        while True:
            action = await asyncio.to_thread(self._key_reader)
            if action != "unknown":
                return action
