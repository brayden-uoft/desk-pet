from __future__ import annotations

import os
import struct
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from time import monotonic

from desk_pet.hardware.desktop.keyboard_trigger import KeyState

_INPUT_EVENT = struct.Struct("@llHHi")
_EV_KEY = 1
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_KEY_CODES = {
    30: 0,  # A: push-to-talk
    46: 1,  # C: cancel/privacy
    48: 2,  # B: briefing/vision
    25: 3,  # P: volume down
    16: 4,  # Q: mute
    19: 5,  # R: volume up
}


def find_event_device(
    device_name: str,
    devices_text: str,
    *,
    event_root: Path = Path("/dev/input"),
) -> Path | None:
    """Return the evdev path for an exact input-device name."""
    expected_name = f'N: Name="{device_name}"'
    for block in devices_text.split("\n\n"):
        if expected_name not in block:
            continue
        for line in block.splitlines():
            if not line.startswith("H: Handlers="):
                continue
            for handler in line.split("=", 1)[1].split():
                if handler.startswith("event") and handler[5:].isdigit():
                    return event_root / handler
    return None


def decode_input_events(data: bytes) -> tuple[list[tuple[int, int, int]], bytes]:
    """Decode complete native Linux input_event records and retain a partial tail."""
    complete_size = len(data) - len(data) % _INPUT_EVENT.size
    events = [
        _INPUT_EVENT.unpack_from(data, offset)[2:]
        for offset in range(0, complete_size, _INPUT_EVENT.size)
    ]
    return events, data[complete_size:]


class EvdevKeyStateReader:
    """Expose a Bluetooth HID keyboard as the six-state macropad contract."""

    def __init__(
        self,
        *,
        device_name: str,
        devices_path: Path = Path("/proc/bus/input/devices"),
        event_root: Path = Path("/dev/input"),
        retry_seconds: float = 1.0,
        clock: Callable[[], float] = monotonic,
        read_device: Callable[[int, int], bytes] = os.read,
        open_device: Callable[[Path, int], int] = os.open,
        close_device: Callable[[int], None] = os.close,
    ) -> None:
        self._device_name = device_name
        self._devices_path = devices_path
        self._event_root = event_root
        self._retry_seconds = retry_seconds
        self._clock = clock
        self._read_device = read_device
        self._open_device = open_device
        self._close_device = close_device
        self._file_descriptor: int | None = None
        self._next_open_at = 0.0
        self._buffer = b""
        self._state = [False] * 6
        self._pending: deque[KeyState] = deque()

    def __call__(self) -> KeyState:
        if self._pending:
            return self._pending.popleft()
        self._ensure_open()
        if self._file_descriptor is None:
            return tuple(self._state)
        try:
            while True:
                chunk = self._read_device(self._file_descriptor, 4096)
                if not chunk:
                    self._disconnect()
                    break
                self._buffer += chunk
                events, self._buffer = decode_input_events(self._buffer)
                self._apply(events)
        except BlockingIOError:
            pass
        except OSError:
            self._disconnect()
        if self._pending:
            return self._pending.popleft()
        return tuple(self._state)

    def close(self) -> None:
        self._close_descriptor()

    def _ensure_open(self) -> None:
        if self._file_descriptor is not None or self._clock() < self._next_open_at:
            return
        self._next_open_at = self._clock() + self._retry_seconds
        try:
            devices_text = self._devices_path.read_text(encoding="utf-8")
            event_path = find_event_device(
                self._device_name,
                devices_text,
                event_root=self._event_root,
            )
            if event_path is not None:
                self._file_descriptor = self._open_device(
                    event_path,
                    os.O_RDONLY | _O_NONBLOCK,
                )
        except OSError:
            self._file_descriptor = None

    def _apply(self, events: list[tuple[int, int, int]]) -> None:
        for event_type, code, value in events:
            state_index = _KEY_CODES.get(code)
            if event_type != _EV_KEY or state_index is None or value == 2:
                continue
            pressed = value == 1
            if self._state[state_index] == pressed:
                continue
            self._state[state_index] = pressed
            self._pending.append(tuple(self._state))

    def _disconnect(self) -> None:
        was_pressed = any(self._state)
        self._close_descriptor()
        self._buffer = b""
        self._state = [False] * 6
        if was_pressed:
            self._pending.append(tuple(self._state))

    def _close_descriptor(self) -> None:
        if self._file_descriptor is None:
            return
        with suppress(OSError):
            self._close_device(self._file_descriptor)
        self._file_descriptor = None
