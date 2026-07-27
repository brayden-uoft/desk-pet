from desk_pet.face.frames import FACE_ANIMATIONS, FACE_HEIGHT, FACE_WIDTH, frames_for_state
from desk_pet.hardware.desktop.preview_face import RED_OFF, RED_ON


def test_every_face_frame_is_a_binary_32_by_16_matrix() -> None:
    for state, frames in FACE_ANIMATIONS.items():
        assert frames, state
        for frame in frames:
            assert len(frame) == FACE_HEIGHT
            assert all(len(row) == FACE_WIDTH for row in frame)
            assert {pixel for row in frame for pixel in row} <= {0, 1}


def test_preview_palette_is_monochrome_red_and_off() -> None:
    assert RED_ON == "#ff2020"
    assert RED_OFF == "#170303"


def test_unknown_state_falls_back_to_idle() -> None:
    assert frames_for_state("unknown") == FACE_ANIMATIONS["idle"]
