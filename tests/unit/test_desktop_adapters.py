import asyncio

from desk_pet.hardware.desktop.keyboard_trigger import KeyboardTrigger
from desk_pet.hardware.desktop.simulated_face import TerminalFace


def test_keyboard_ignores_unknown_keys() -> None:
    keys = iter(["unknown", "listen"])
    trigger = KeyboardTrigger(key_reader=lambda: next(keys))

    assert asyncio.run(trigger.wait_for_trigger()) == "listen"


def test_terminal_face_displays_state() -> None:
    output: list[str] = []
    face = TerminalFace(output.append)

    asyncio.run(face.set_state("listening"))

    assert output == ["[            LISTENING]  ◉     ◉"]
