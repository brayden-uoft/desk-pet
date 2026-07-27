import asyncio

from desk_pet.hardware.desktop.keyboard_trigger import KeyboardTrigger, windows_virtual_key
from desk_pet.hardware.desktop.simulated_face import TerminalFace


def test_keyboard_ignores_unknown_keys() -> None:
    keys = iter([(False, False), (True, False)])
    trigger = KeyboardTrigger(key_reader=lambda: next(keys))

    assert asyncio.run(trigger.wait_for_trigger()) == "listen_start"


def test_keyboard_reports_push_to_talk_release() -> None:
    keys = iter([(True, False), (True, False), (False, False)])
    trigger = KeyboardTrigger(key_reader=lambda: next(keys))

    assert asyncio.run(trigger.wait_for_trigger()) == "listen_start"
    assert asyncio.run(trigger.wait_for_trigger()) == "listen_stop"


def test_right_alt_has_its_own_windows_virtual_key() -> None:
    assert windows_virtual_key("right_alt") == 0xA5
    assert windows_virtual_key("right_alt") != windows_virtual_key("left_alt")


def test_terminal_face_displays_state() -> None:
    output: list[str] = []
    face = TerminalFace(output.append)

    asyncio.run(face.set_state("listening"))

    assert output == ["[            LISTENING]  ◉     ◉"]
