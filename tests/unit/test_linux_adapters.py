from __future__ import annotations

import struct
from pathlib import Path

from desk_pet.hardware.linux.evdev_trigger import EvdevKeyStateReader, find_event_device

_INPUT_EVENT = struct.Struct("@llHHi")


def _key_event(code: int, value: int) -> bytes:
    return _INPUT_EVENT.pack(0, 0, 1, code, value)


def test_finds_exact_named_event_device() -> None:
    devices = """
I: Bus=0005 Vendor=05ac Product=022c Version=011b
N: Name="MINI-KEYBOARD"
H: Handlers=sysrq kbd leds event7

I: Bus=0019 Vendor=0001 Product=0001 Version=0100
N: Name="gpio-keys"
H: Handlers=kbd event1
"""

    assert find_event_device("MINI-KEYBOARD", devices) == Path("/dev/input/event7")


def test_fast_press_and_release_are_delivered_as_separate_states(
    tmp_path: Path,
) -> None:
    devices_path = tmp_path / "devices"
    devices_path.write_text(
        'N: Name="MINI-KEYBOARD"\nH: Handlers=kbd event2\n',
        encoding="utf-8",
    )
    chunks: list[bytes | BaseException] = [
        _key_event(25, 1) + _key_event(25, 0),
        BlockingIOError(),
    ]

    def read_device(_descriptor: int, _size: int) -> bytes:
        if not chunks:
            raise BlockingIOError
        result = chunks.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    closed: list[int] = []
    reader = EvdevKeyStateReader(
        device_name="MINI-KEYBOARD",
        devices_path=devices_path,
        event_root=tmp_path,
        retry_seconds=0,
        read_device=read_device,
        open_device=lambda _path, _flags: 9,
        close_device=closed.append,
    )

    assert reader() == (False, False, False, True, False, False)
    assert reader() == (False, False, False, False, False, False)
    reader.close()
    assert closed == [9]


def test_held_key_ignores_kernel_repeat_events(tmp_path: Path) -> None:
    devices_path = tmp_path / "devices"
    devices_path.write_text(
        'N: Name="MINI-KEYBOARD"\nH: Handlers=kbd event2\n',
        encoding="utf-8",
    )
    chunks: list[bytes | BaseException] = [
        _key_event(30, 1) + _key_event(30, 2),
        BlockingIOError(),
    ]

    def read_device(_descriptor: int, _size: int) -> bytes:
        if not chunks:
            raise BlockingIOError
        result = chunks.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    reader = EvdevKeyStateReader(
        device_name="MINI-KEYBOARD",
        devices_path=devices_path,
        retry_seconds=10,
        read_device=read_device,
        open_device=lambda _path, _flags: 9,
        close_device=lambda _descriptor: None,
    )

    assert reader() == (True, False, False, False, False, False)
    assert reader() == (True, False, False, False, False, False)
    reader.close()
