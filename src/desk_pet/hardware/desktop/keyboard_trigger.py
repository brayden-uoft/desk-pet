from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Sequence
from functools import partial
from time import monotonic
from typing import Any, cast

KeyState = Sequence[bool]
WINDOWS_VIRTUAL_KEYS = {
    "space": 0x20,
    "left_alt": 0xA4,
    "right_alt": 0xA5,
    "escape": 0x1B,
    "f13": 0x7C,
    "a": 0x41,
    "b": 0x42,
    "c": 0x43,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
}


def windows_virtual_key(name: str) -> int:
    try:
        return WINDOWS_VIRTUAL_KEYS[name]
    except KeyError:
        supported = ", ".join(sorted(WINDOWS_VIRTUAL_KEYS))
        raise ValueError(f"Unsupported Windows key {name!r}; choose one of: {supported}") from None


def _poll_windows_keys(
    listen_virtual_key: int,
    cancel_virtual_keys: tuple[int, ...],
    briefing_virtual_key: int,
    volume_down_virtual_key: int,
    mute_virtual_key: int,
    volume_up_virtual_key: int,
) -> KeyState:
    import ctypes

    user32 = cast(Any, ctypes).windll.user32
    listen_pressed = bool(user32.GetAsyncKeyState(listen_virtual_key) & 0x8000)
    cancel_pressed = any(
        bool(user32.GetAsyncKeyState(virtual_key) & 0x8000) for virtual_key in cancel_virtual_keys
    )
    return (
        listen_pressed,
        cancel_pressed,
        bool(user32.GetAsyncKeyState(briefing_virtual_key) & 0x8000),
        bool(user32.GetAsyncKeyState(volume_down_virtual_key) & 0x8000),
        bool(user32.GetAsyncKeyState(mute_virtual_key) & 0x8000),
        bool(user32.GetAsyncKeyState(volume_up_virtual_key) & 0x8000),
    )


class KeyboardTrigger:
    def __init__(
        self,
        key_reader: Callable[[], KeyState] | None = None,
        *,
        listen_key: str = "space",
        cancel_key: str = "escape",
        extra_cancel_keys: Sequence[str] = (),
        briefing_key: str = "b",
        volume_down_key: str = "p",
        mute_key: str = "q",
        volume_up_key: str = "r",
        enabled_reader: Callable[[], bool] | None = None,
        poll_interval_seconds: float = 0.02,
        hold_seconds: float = 0.65,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if key_reader is None and sys.platform != "win32":
            raise RuntimeError("The Stage 1 keyboard adapter currently requires Windows")
        if key_reader is None:
            try:
                listen_virtual_key = windows_virtual_key(listen_key)
                cancel_virtual_keys = tuple(
                    windows_virtual_key(key) for key in (cancel_key, *extra_cancel_keys)
                )
                briefing_virtual_key = windows_virtual_key(briefing_key)
                volume_down_virtual_key = windows_virtual_key(volume_down_key)
                mute_virtual_key = windows_virtual_key(mute_key)
                volume_up_virtual_key = windows_virtual_key(volume_up_key)
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc
            key_reader = partial(
                _poll_windows_keys,
                listen_virtual_key,
                cancel_virtual_keys,
                briefing_virtual_key,
                volume_down_virtual_key,
                mute_virtual_key,
                volume_up_virtual_key,
            )
        self._key_reader = key_reader
        self._enabled_reader = enabled_reader or (lambda: True)
        self._poll_interval_seconds = poll_interval_seconds
        self._hold_seconds = hold_seconds
        self._clock = clock
        self._listen_pressed = False
        self._cancel_pressed = False
        self._briefing_pressed = False
        self._volume_down_pressed = False
        self._mute_pressed = False
        self._volume_up_pressed = False
        self._listen_active = False
        self._briefing_pressed_at = 0.0
        self._briefing_hold_emitted = False
        self._cancel_pressed_at = 0.0
        self._privacy_emitted = False
        self._enabled = self._enabled_reader()

    @staticmethod
    def _normalize_keys(state: KeyState) -> tuple[bool, bool, bool, bool, bool, bool]:
        values = [bool(value) for value in state[:6]]
        values.extend([False] * (6 - len(values)))
        return cast(tuple[bool, bool, bool, bool, bool, bool], tuple(values))

    async def wait_for_trigger(self) -> str:
        while True:
            (
                listen_pressed,
                cancel_pressed,
                briefing_pressed,
                volume_down_pressed,
                mute_pressed,
                volume_up_pressed,
            ) = self._normalize_keys(self._key_reader())
            enabled = self._enabled_reader()
            if not enabled:
                should_stop = self._listen_active
                self._listen_pressed = listen_pressed
                self._cancel_pressed = cancel_pressed
                self._briefing_pressed = briefing_pressed
                self._volume_down_pressed = volume_down_pressed
                self._mute_pressed = mute_pressed
                self._volume_up_pressed = volume_up_pressed
                self._listen_active = False
                self._enabled = False
                if should_stop:
                    return "listen_stop"
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            if not self._enabled:
                # Ignore keys that were already held when the DeskBob window
                # regained focus. A fresh press is required.
                self._listen_pressed = listen_pressed
                self._cancel_pressed = cancel_pressed
                self._briefing_pressed = briefing_pressed
                self._volume_down_pressed = volume_down_pressed
                self._mute_pressed = mute_pressed
                self._volume_up_pressed = volume_up_pressed
                self._enabled = True
                await asyncio.sleep(self._poll_interval_seconds)
                continue
            action: str | None = None
            now = self._clock()
            if cancel_pressed and not self._cancel_pressed:
                self._cancel_pressed_at = now
                self._privacy_emitted = False
                action = "cancel"
            elif (
                cancel_pressed
                and not self._privacy_emitted
                and now - self._cancel_pressed_at >= self._hold_seconds
            ):
                self._privacy_emitted = True
                action = "privacy_toggle"
            elif listen_pressed and not self._listen_pressed:
                action = "listen_start"
                self._listen_active = True
            elif not listen_pressed and self._listen_pressed and self._listen_active:
                action = "listen_stop"
                self._listen_active = False
            elif briefing_pressed and not self._briefing_pressed:
                self._briefing_pressed_at = now
                self._briefing_hold_emitted = False
            elif (
                briefing_pressed
                and not self._briefing_hold_emitted
                and now - self._briefing_pressed_at >= self._hold_seconds
            ):
                self._briefing_hold_emitted = True
                action = "visual"
            elif not briefing_pressed and self._briefing_pressed:
                if not self._briefing_hold_emitted:
                    action = "briefing"
            elif volume_down_pressed and not self._volume_down_pressed:
                action = "volume_down"
            elif volume_up_pressed and not self._volume_up_pressed:
                action = "volume_up"
            elif mute_pressed and not self._mute_pressed:
                action = "mute_toggle"
            self._listen_pressed = listen_pressed
            self._cancel_pressed = cancel_pressed
            self._briefing_pressed = briefing_pressed
            self._volume_down_pressed = volume_down_pressed
            self._mute_pressed = mute_pressed
            self._volume_up_pressed = volume_up_pressed
            if action is not None:
                return action
            await asyncio.sleep(self._poll_interval_seconds)
