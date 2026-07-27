import asyncio

from desk_pet.hardware.desktop.keyboard_trigger import KeyboardTrigger
from desk_pet.hardware.desktop.simulated_face import TerminalFace


def test_keyboard_ignores_unknown_keys() -> None:
    keys = iter([(False, False), (True, False)])
    trigger = KeyboardTrigger(key_reader=lambda: next(keys))

    assert asyncio.run(trigger.wait_for_trigger()) == "listen_start"


def test_keyboard_reports_space_release() -> None:
    keys = iter([(True, False), (True, False), (False, False)])
    trigger = KeyboardTrigger(key_reader=lambda: next(keys))

    assert asyncio.run(trigger.wait_for_trigger()) == "listen_start"
    assert asyncio.run(trigger.wait_for_trigger()) == "listen_stop"


def test_terminal_face_displays_state() -> None:
    output: list[str] = []
    face = TerminalFace(output.append)

    asyncio.run(face.set_state("listening"))

    assert output == ["[            LISTENING]  ◉     ◉"]
