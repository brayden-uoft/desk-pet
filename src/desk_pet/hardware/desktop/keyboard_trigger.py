from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable


def _poll_windows_key() -> str | None:
    import msvcrt

    if not msvcrt.kbhit():
        return None
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
    def __init__(
        self,
        key_reader: Callable[[], str | None] | None = None,
        *,
        poll_interval_seconds: float = 0.02,
    ) -> None:
        if key_reader is None and sys.platform != "win32":
            raise RuntimeError("The Stage 1 keyboard adapter currently requires Windows")
        self._key_reader = key_reader or _poll_windows_key
        self._poll_interval_seconds = poll_interval_seconds

    async def wait_for_trigger(self) -> str:
        while True:
            action = self._key_reader()
            if action is not None and action != "unknown":
                return action
            await asyncio.sleep(self._poll_interval_seconds)
