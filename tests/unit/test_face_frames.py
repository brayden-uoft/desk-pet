import random

from desk_pet.face.frames import (
    FACE_ANIMATIONS,
    FACE_FRAMES,
    FACE_HEIGHT,
    FACE_WIDTH,
    animation_cycle_for_state,
    frames_for_state,
)
from desk_pet.hardware.desktop.preview_face import RED_OFF, RED_ON


def test_every_face_frame_is_a_binary_32_by_16_matrix() -> None:
    for name, frame in FACE_FRAMES.items():
        assert len(frame) == FACE_HEIGHT, name
        assert all(len(row) == FACE_WIDTH for row in frame)
        assert {pixel for row in frame for pixel in row} <= {0, 1}


def test_idle_cycles_hold_for_seconds_and_vary_irregularly() -> None:
    rng = random.Random(12)
    cycles = [animation_cycle_for_state("idle", rng) for _ in range(40)]
    resting_durations = {cycle[0].duration_ms for cycle in cycles}
    action_frames = {frame.pixels for cycle in cycles for frame in cycle[1:-1]}

    assert all(2400 <= cycle[0].duration_ms <= 6200 for cycle in cycles)
    assert len(resting_durations) > 20
    assert FACE_FRAMES["blink"] in action_frames
    assert FACE_FRAMES["look_left"] in action_frames
    assert FACE_FRAMES["tongue"] in action_frames
    assert FACE_FRAMES["lick_left"] in action_frames


def test_speaking_cycles_use_multiple_mouth_shapes_and_irregular_timing() -> None:
    cycle = animation_cycle_for_state("speaking", random.Random(4))

    assert len({frame.pixels for frame in cycle}) >= 3
    assert len({frame.duration_ms for frame in cycle}) >= 3


def test_preview_palette_is_monochrome_red_and_off() -> None:
    assert RED_ON == "#ff2020"
    assert RED_OFF == "#170303"


def test_unknown_state_falls_back_to_idle() -> None:
    assert frames_for_state("unknown") == FACE_ANIMATIONS["idle"]
    assert animation_cycle_for_state("unknown", random.Random(1))[0].duration_ms >= 2400
