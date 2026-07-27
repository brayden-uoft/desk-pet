from __future__ import annotations

import asyncio
import importlib
from typing import Any

from desk_pet.camera.errors import CameraError


class OpenCVCameraDevice:
    def __init__(
        self,
        *,
        index: int,
        maximum_dimension: int,
        jpeg_quality: int,
        cv2_module: Any | None = None,
    ) -> None:
        self._index = index
        self._maximum_dimension = maximum_dimension
        self._jpeg_quality = jpeg_quality
        self._cv2 = cv2_module

    async def capture_jpeg(self) -> bytes:
        return await asyncio.to_thread(self._capture_jpeg)

    def _capture_jpeg(self) -> bytes:
        cv2 = self._cv2 or self._load_opencv()
        camera = cv2.VideoCapture(self._index)
        try:
            if not camera.isOpened():
                raise CameraError(f"Could not open camera index {self._index}.")
            captured, frame = camera.read()
            if not captured or frame is None:
                raise CameraError("The camera opened but did not return a frame.")

            height, width = frame.shape[:2]
            largest_dimension = max(height, width)
            if largest_dimension > self._maximum_dimension:
                scale = self._maximum_dimension / largest_dimension
                frame = cv2.resize(
                    frame,
                    (max(1, round(width * scale)), max(1, round(height * scale))),
                    interpolation=cv2.INTER_AREA,
                )

            encoded, jpeg = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality],
            )
            if not encoded:
                raise CameraError("OpenCV could not JPEG-compress the camera frame.")
            jpeg_bytes = bytes(jpeg.tobytes())
            if not jpeg_bytes:
                raise CameraError("OpenCV returned an empty JPEG image.")
            return jpeg_bytes
        except CameraError:
            raise
        except Exception as exc:
            raise CameraError(f"Camera capture failed: {exc}") from exc
        finally:
            camera.release()

    @staticmethod
    def _load_opencv() -> Any:
        try:
            return importlib.import_module("cv2")
        except ImportError as exc:
            raise CameraError("OpenCV is unavailable. Run the Windows launcher again.") from exc
