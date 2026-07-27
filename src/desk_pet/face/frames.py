from __future__ import annotations

from collections.abc import Iterable

FACE_WIDTH = 32
FACE_HEIGHT = 16
PixelFrame = tuple[tuple[int, ...], ...]


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


def _smile(builder: _FrameBuilder) -> None:
    builder.pixels(((11, 11), (20, 11), (12, 12), (19, 12)))
    builder.horizontal(13, 18, 13)


def _idle(*, blink: bool = False) -> PixelFrame:
    builder = _FrameBuilder()
    if blink:
        builder.horizontal(5, 10, 6)
        builder.horizontal(21, 26, 6)
    else:
        _open_eyes(builder)
    _smile(builder)
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


def _speaking(*, open_mouth: bool) -> PixelFrame:
    builder = _FrameBuilder()
    builder.pixels(((6, 5), (7, 4), (8, 4), (9, 5)))
    builder.pixels(((22, 5), (23, 4), (24, 4), (25, 5)))
    if open_mouth:
        builder.horizontal(12, 19, 11)
        builder.horizontal(12, 19, 14)
        builder.vertical(11, 12, 13)
        builder.vertical(20, 12, 13)
    else:
        builder.pixels(((12, 12), (19, 12), (13, 13), (18, 13)))
        builder.horizontal(14, 17, 14)
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


FACE_ANIMATIONS: dict[str, tuple[PixelFrame, ...]] = {
    "idle": (_idle(), _idle(), _idle(blink=True), _idle()),
    "listening": (_listening(wave=0), _listening(wave=1), _listening(wave=2)),
    "transcribing": (
        _thinking(pupil_offset=-1, dot=0),
        _thinking(pupil_offset=0, dot=1),
        _thinking(pupil_offset=1, dot=2),
    ),
    "thinking": (
        _thinking(pupil_offset=-1, dot=0),
        _thinking(pupil_offset=0, dot=1),
        _thinking(pupil_offset=1, dot=2),
    ),
    "using_tool": (_using_tool(scanline=0), _using_tool(scanline=1)),
    "speaking": (_speaking(open_mouth=False), _speaking(open_mouth=True)),
    "error": (_error(),),
    "starting": (_thinking(pupil_offset=0, dot=0),),
}


def frames_for_state(state: str) -> tuple[PixelFrame, ...]:
    return FACE_ANIMATIONS.get(state, FACE_ANIMATIONS["idle"])
