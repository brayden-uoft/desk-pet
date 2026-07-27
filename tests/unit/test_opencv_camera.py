import asyncio
from typing import Any

import pytest

from desk_pet.camera.errors import CameraError
from desk_pet.hardware.desktop.opencv_camera import OpenCVCameraDevice


class FakeFrame:
    def __init__(self, height: int, width: int) -> None:
        self.shape = (height, width, 3)


class FakeEncodedImage:
    def tobytes(self) -> bytes:
        return b"\xff\xd8compressed-jpeg\xff\xd9"


class FakeVideoCapture:
    def __init__(
        self,
        *,
        opened: bool = True,
        captured: bool = True,
        frame: FakeFrame | None = None,
    ) -> None:
        self.opened = opened
        self.captured = captured
        self.frame = frame or FakeFrame(1080, 1920)
        self.read_calls = 0
        self.release_calls = 0

    def isOpened(self) -> bool:
        return self.opened

    def read(self) -> tuple[bool, FakeFrame | None]:
        self.read_calls += 1
        return self.captured, self.frame if self.captured else None

    def release(self) -> None:
        self.release_calls += 1


class FakeCV2:
    INTER_AREA = 3
    IMWRITE_JPEG_QUALITY = 1

    def __init__(self, capture: FakeVideoCapture) -> None:
        self.capture = capture
        self.opened_indices: list[int] = []
        self.resize_calls: list[tuple[Any, tuple[int, int], int]] = []
        self.encode_calls: list[tuple[str, Any, list[int]]] = []

    def VideoCapture(self, index: int) -> FakeVideoCapture:
        self.opened_indices.append(index)
        return self.capture

    def resize(
        self,
        frame: Any,
        dimensions: tuple[int, int],
        *,
        interpolation: int,
    ) -> FakeFrame:
        self.resize_calls.append((frame, dimensions, interpolation))
        return FakeFrame(dimensions[1], dimensions[0])

    def imencode(
        self,
        extension: str,
        frame: Any,
        parameters: list[int],
    ) -> tuple[bool, FakeEncodedImage]:
        self.encode_calls.append((extension, frame, parameters))
        return True, FakeEncodedImage()


def test_captures_exactly_one_frame_resizes_and_compresses() -> None:
    capture = FakeVideoCapture(frame=FakeFrame(1080, 1920))
    cv2 = FakeCV2(capture)
    camera = OpenCVCameraDevice(
        index=2,
        maximum_dimension=1024,
        jpeg_quality=80,
        cv2_module=cv2,
    )

    jpeg = asyncio.run(camera.capture_jpeg())

    assert jpeg == b"\xff\xd8compressed-jpeg\xff\xd9"
    assert cv2.opened_indices == [2]
    assert capture.read_calls == 1
    assert capture.release_calls == 1
    assert cv2.resize_calls[0][1] == (1024, 576)
    assert cv2.encode_calls[0][0] == ".jpg"
    assert cv2.encode_calls[0][2] == [cv2.IMWRITE_JPEG_QUALITY, 80]


@pytest.mark.parametrize(
    ("capture", "message"),
    [
        (FakeVideoCapture(opened=False), "Could not open camera"),
        (FakeVideoCapture(captured=False), "did not return a frame"),
    ],
)
def test_releases_camera_after_capture_failures(
    capture: FakeVideoCapture,
    message: str,
) -> None:
    camera = OpenCVCameraDevice(
        index=0,
        maximum_dimension=1024,
        jpeg_quality=80,
        cv2_module=FakeCV2(capture),
    )

    with pytest.raises(CameraError, match=message):
        asyncio.run(camera.capture_jpeg())

    assert capture.read_calls == (1 if capture.opened else 0)
    assert capture.release_calls == 1
