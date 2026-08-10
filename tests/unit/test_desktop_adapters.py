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


def test_macropad_letters_have_windows_virtual_keys() -> None:
    assert windows_virtual_key("a") == 0x41
    assert windows_virtual_key("b") == 0x42
    assert windows_virtual_key("c") == 0x43
    assert windows_virtual_key("p") == 0x50
    assert windows_virtual_key("q") == 0x51
    assert windows_virtual_key("r") == 0x52


def test_macropad_b_tap_and_hold_have_distinct_actions() -> None:
    tap_keys = iter([(False, False, True, False, False, False), (False,) * 6])
    tap = KeyboardTrigger(key_reader=lambda: next(tap_keys), poll_interval_seconds=0)
    assert asyncio.run(tap.wait_for_trigger()) == "briefing"

    times = iter((0.0, 0.7))
    hold_keys = iter(
        [(False, False, True, False, False, False), (False, False, True, False, False, False)]
    )
    hold = KeyboardTrigger(
        key_reader=lambda: next(hold_keys),
        poll_interval_seconds=0,
        clock=lambda: next(times),
    )
    assert asyncio.run(hold.wait_for_trigger()) == "visual"


def test_macropad_cancel_privacy_and_dial_actions() -> None:
    times = iter((0.0, 0.7))
    cancel_keys = iter([(False, True), (False, True)])
    cancel = KeyboardTrigger(
        key_reader=lambda: next(cancel_keys),
        poll_interval_seconds=0,
        clock=lambda: next(times),
    )
    assert asyncio.run(cancel.wait_for_trigger()) == "cancel"
    assert asyncio.run(cancel.wait_for_trigger()) == "privacy_toggle"

    for state, expected in (
        ((False, False, False, True, False, False), "volume_down"),
        ((False, False, False, False, True, False), "mute_toggle"),
        ((False, False, False, False, False, True), "volume_up"),
    ):
        trigger = KeyboardTrigger(key_reader=iter((state,)).__next__, poll_interval_seconds=0)
        assert asyncio.run(trigger.wait_for_trigger()) == expected


def test_keyboard_ignores_press_that_started_while_window_was_unfocused() -> None:
    enabled = False
    keys = iter([(True, False), (True, False), (False, False), (True, False)])

    def read_keys() -> tuple[bool, bool]:
        nonlocal enabled
        value = next(keys)
        enabled = True
        return value

    trigger = KeyboardTrigger(
        key_reader=read_keys,
        enabled_reader=lambda: enabled,
        poll_interval_seconds=0,
    )

    assert asyncio.run(trigger.wait_for_trigger()) == "listen_start"


def test_losing_focus_stops_active_push_to_talk() -> None:
    enabled = True
    keys = iter([(True, False), (True, False)])

    def read_keys() -> tuple[bool, bool]:
        nonlocal enabled
        value = next(keys)
        if value == (True, False) and trigger._listen_active:  # noqa: SLF001
            enabled = False
        return value

    trigger = KeyboardTrigger(
        key_reader=read_keys,
        enabled_reader=lambda: enabled,
        poll_interval_seconds=0,
    )

    assert asyncio.run(trigger.wait_for_trigger()) == "listen_start"
    assert asyncio.run(trigger.wait_for_trigger()) == "listen_stop"


def test_terminal_face_displays_state() -> None:
    output: list[str] = []
    face = TerminalFace(output.append)

    asyncio.run(face.set_state("listening"))

    assert output == ["[            LISTENING]  ◉     ◉"]
