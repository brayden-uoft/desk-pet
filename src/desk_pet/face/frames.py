from __future__ import annotations

import random
from collections.abc import Iterable
from dataclasses import dataclass

FACE_WIDTH = 32
FACE_HEIGHT = 16
PixelFrame = tuple[tuple[int, ...], ...]


@dataclass(frozen=True, slots=True)
class TimedFrame:
    pixels: PixelFrame
    duration_ms: int


class _FrameBuilder:
    def __init__(self) -> None:
        self._pixels = [[0 for _ in range(FACE_WIDTH)] for _ in range(FACE_HEIGHT)]

    def pixels(self, points: Iterable[tuple[int, int]]) -> None:
        for x, y in points:
            if 0 <= x < FACE_WIDTH and 0 <= y < FACE_HEIGHT:
                self._pixels[y][x] = 1

    def horizontal(self, x1: int, x2: int, y: int) -> None:
        self.pixels((x, y) for x in range(x1, x2 + 1))

    def vertical(self, x: int, y1: int, y2: int) -> None:
        self.pixels((x, y) for y in range(y1, y2 + 1))

    def frame(self) -> PixelFrame:
        return tuple(tuple(row) for row in self._pixels)


def _open_eyes(builder: _FrameBuilder, *, pupil_offset: int = 0) -> None:
    for left in (5, 21):
        builder.horizontal(left + 1, left + 4, 3)
        builder.horizontal(left + 1, left + 4, 8)
        builder.vertical(left, 4, 7)
        builder.vertical(left + 5, 4, 7)
        pupil_x = left + 2 + pupil_offset
        builder.pixels(((pupil_x, 5), (pupil_x, 6)))


def _happy_eyes(builder: _FrameBuilder) -> None:
    for left in (5, 21):
        builder.pixels(
            (
                (left, 6),
                (left + 1, 5),
                (left + 2, 4),
                (left + 3, 4),
                (left + 4, 5),
                (left + 5, 6),
            )
        )


def _smile(builder: _FrameBuilder) -> None:
    builder.pixels(((11, 11), (20, 11), (12, 12), (19, 12)))
    builder.horizontal(13, 18, 13)


def _idle(
    *,
    blink: bool = False,
    pupil_offset: int = 0,
    mouth: str = "smile",
) -> PixelFrame:
    builder = _FrameBuilder()
    if blink:
        builder.horizontal(5, 10, 6)
        builder.horizontal(21, 26, 6)
    else:
        _open_eyes(builder, pupil_offset=pupil_offset)
    if mouth == "smile":
        _smile(builder)
    elif mouth == "smirk":
        builder.horizontal(12, 18, 12)
        builder.pixels(((19, 11), (20, 10)))
    elif mouth == "tongue":
        builder.horizontal(12, 19, 11)
        builder.pixels(((14, 12), (15, 12), (16, 12), (17, 12)))
        builder.horizontal(15, 17, 13)
        builder.pixels(((16, 14),))
    elif mouth == "lick_left":
        builder.horizontal(13, 19, 12)
        builder.pixels(((12, 11), (11, 10), (10, 11)))
    elif mouth == "lick_right":
        builder.horizontal(12, 18, 12)
        builder.pixels(((19, 11), (20, 10), (21, 11)))
    return builder.frame()


def _listening(*, wave: int) -> PixelFrame:
    builder = _FrameBuilder()
    _open_eyes(builder)
    builder.pixels(((15, 11), (16, 11), (14, 12), (17, 12), (15, 13), (16, 13)))
    for x in range(wave + 1):
        builder.vertical(1 + x * 2, 5 - x, 6 + x)
        builder.vertical(30 - x * 2, 5 - x, 6 + x)
    return builder.frame()


def _thinking(*, pupil_offset: int, dot: int) -> PixelFrame:
    builder = _FrameBuilder()
    _open_eyes(builder, pupil_offset=pupil_offset)
    builder.pixels(((13, 12), (16, 12), (19, 12)))
    builder.pixels(((13 + dot * 3, 11),))
    return builder.frame()


def _using_tool(*, scanline: int) -> PixelFrame:
    builder = _FrameBuilder()
    builder.horizontal(4, 12, 2)
    builder.horizontal(4, 12, 10)
    builder.vertical(4, 2, 10)
    builder.vertical(12, 2, 10)
    builder.horizontal(6, 10, 6)
    builder.vertical(8, 4, 8)
    builder.horizontal(20, 26, 4 + scanline)
    builder.horizontal(20, 26, 9 - scanline)
    _smile(builder)
    return builder.frame()


def _speaking(*, mouth: str, eyes: str = "happy") -> PixelFrame:
    builder = _FrameBuilder()
    if eyes == "happy":
        _happy_eyes(builder)
    else:
        _open_eyes(builder, pupil_offset={"left": -1, "right": 1}.get(eyes, 0))
    if mouth == "closed":
        builder.horizontal(12, 19, 12)
    elif mouth == "small":
        builder.horizontal(14, 17, 11)
        builder.horizontal(14, 17, 13)
        builder.pixels(((13, 12), (18, 12)))
    elif mouth == "medium":
        builder.horizontal(12, 19, 11)
        builder.horizontal(12, 19, 14)
        builder.vertical(11, 12, 13)
        builder.vertical(20, 12, 13)
    elif mouth == "wide":
        builder.horizontal(10, 21, 11)
        builder.horizontal(12, 19, 15)
        builder.pixels(((10, 12), (11, 13), (20, 13), (21, 12), (12, 14), (19, 14)))
    elif mouth == "side":
        builder.horizontal(12, 18, 11)
        builder.horizontal(14, 20, 14)
        builder.pixels(((11, 12), (12, 13), (19, 12), (20, 13)))
    return builder.frame()


def _error() -> PixelFrame:
    builder = _FrameBuilder()
    for left in (5, 21):
        builder.pixels(
            (
                (left, 3),
                (left + 1, 4),
                (left + 2, 5),
                (left + 3, 6),
                (left + 4, 7),
                (left + 5, 8),
                (left + 5, 3),
                (left + 4, 4),
                (left + 3, 5),
                (left + 2, 6),
                (left + 1, 7),
                (left, 8),
            )
        )
    builder.horizontal(12, 19, 12)
    builder.pixels(((11, 13), (20, 13)))
    return builder.frame()


FACE_FRAMES: dict[str, PixelFrame] = {
    "idle": _idle(),
    "blink": _idle(blink=True),
    "look_left": _idle(pupil_offset=-1),
    "look_right": _idle(pupil_offset=1),
    "smirk": _idle(mouth="smirk"),
    "tongue": _idle(mouth="tongue"),
    "lick_left": _idle(mouth="lick_left"),
    "lick_right": _idle(mouth="lick_right"),
    "listen_0": _listening(wave=0),
    "listen_1": _listening(wave=1),
    "listen_2": _listening(wave=2),
    "think_left": _thinking(pupil_offset=-1, dot=0),
    "think_center": _thinking(pupil_offset=0, dot=1),
    "think_right": _thinking(pupil_offset=1, dot=2),
    "tool_0": _using_tool(scanline=0),
    "tool_1": _using_tool(scanline=1),
    "talk_closed": _speaking(mouth="closed", eyes="center"),
    "talk_small": _speaking(mouth="small", eyes="center"),
    "talk_medium": _speaking(mouth="medium", eyes="center"),
    "talk_wide": _speaking(mouth="wide", eyes="center"),
    "error": _error(),
}

FACE_ANIMATIONS: dict[str, tuple[PixelFrame, ...]] = {
    "idle": tuple(
        FACE_FRAMES[name]
        for name in (
            "idle",
            "blink",
            "look_left",
            "look_right",
            "smirk",
            "tongue",
            "lick_left",
            "lick_right",
        )
    ),
    "listening": tuple(FACE_FRAMES[f"listen_{index}"] for index in range(3)),
    "transcribing": (
        FACE_FRAMES["think_left"],
        FACE_FRAMES["think_center"],
        FACE_FRAMES["think_right"],
    ),
    "thinking": (
        FACE_FRAMES["think_left"],
        FACE_FRAMES["think_center"],
        FACE_FRAMES["think_right"],
    ),
    "using_tool": (FACE_FRAMES["tool_0"], FACE_FRAMES["tool_1"]),
    "speaking": tuple(
        FACE_FRAMES[f"talk_{mouth}"] for mouth in ("closed", "small", "medium", "wide")
    ),
    "error": (FACE_FRAMES["error"],),
    "starting": (FACE_FRAMES["think_center"],),
}


def frames_for_state(state: str) -> tuple[PixelFrame, ...]:
    return FACE_ANIMATIONS.get(state, FACE_ANIMATIONS["idle"])


def animation_cycle_for_state(
    state: str,
    rng: random.Random | None = None,
) -> tuple[TimedFrame, ...]:
    """Build one varied animation cycle with state-specific frame timing."""
    randomizer = rng or random.Random()
    if state == "idle" or state not in FACE_ANIMATIONS:
        return _idle_cycle(randomizer)
    if state == "speaking":
        names = ("talk_closed", "talk_small", "talk_medium", "talk_wide")
        mouth_levels = [0]
        for _ in range(randomizer.randint(2, 4)):
            peak = randomizer.choices((1, 2, 3), weights=(3, 5, 2), k=1)[0]
            mouth_levels.extend(range(1, peak + 1))
            mouth_levels.extend(range(peak - 1, -1, -1))
        sequence = [
            TimedFrame(
                FACE_FRAMES[names[level]],
                randomizer.randint(145, 245),
            )
            for level in mouth_levels
        ]
        return tuple(sequence)
    durations = {
        "listening": (120, 210),
        "transcribing": (180, 340),
        "thinking": (180, 340),
        "using_tool": (120, 220),
        "error": (650, 900),
        "starting": (250, 450),
    }
    low, high = durations[state]
    return tuple(
        TimedFrame(frame, randomizer.randint(low, high)) for frame in FACE_ANIMATIONS[state]
    )


def _idle_cycle(rng: random.Random) -> tuple[TimedFrame, ...]:
    resting = TimedFrame(FACE_FRAMES["idle"], rng.randint(2400, 6200))
    action: tuple[TimedFrame, ...]
    behavior = rng.choices(
        ("blink", "double_blink", "look", "lick", "tongue", "smirk"),
        weights=(28, 6, 32, 10, 8, 16),
        k=1,
    )[0]
    if behavior == "blink":
        action = (TimedFrame(FACE_FRAMES["blink"], rng.randint(80, 145)),)
    elif behavior == "double_blink":
        action = (
            TimedFrame(FACE_FRAMES["blink"], 90),
            TimedFrame(FACE_FRAMES["idle"], 125),
            TimedFrame(FACE_FRAMES["blink"], 95),
        )
    elif behavior == "look":
        direction = rng.choice(("look_left", "look_right"))
        action = (TimedFrame(FACE_FRAMES[direction], rng.randint(550, 1500)),)
    elif behavior == "lick":
        direction = rng.choice(("lick_left", "lick_right"))
        other = "lick_right" if direction == "lick_left" else "lick_left"
        action = (
            TimedFrame(FACE_FRAMES[direction], rng.randint(110, 190)),
            TimedFrame(FACE_FRAMES[other], rng.randint(110, 190)),
        )
    elif behavior == "tongue":
        action = (TimedFrame(FACE_FRAMES["tongue"], rng.randint(220, 520)),)
    else:
        action = (TimedFrame(FACE_FRAMES["smirk"], rng.randint(450, 1100)),)
    return (resting, *action, TimedFrame(FACE_FRAMES["idle"], rng.randint(220, 520)))
