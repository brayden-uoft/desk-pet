from __future__ import annotations

from typing import Any, Literal

from desk_pet.camera.errors import CameraError
from desk_pet.hardware.interfaces import CameraDevice
from desk_pet.skills.registry import SkillDefinition, SkillResult, reject_unknown_arguments


def create_camera_stub_skill() -> SkillDefinition:
    def validate(arguments: dict[str, Any]) -> None:
        reject_unknown_arguments(arguments, set())

    async def execute(arguments: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "camera_not_available",
            "message": "Camera capture will be enabled in Stage 5.",
        }

    return SkillDefinition(
        name="capture_camera_image",
        description=(
            "Capture one camera image when visual information is required. "
            "The current Stage 3 implementation reports that the camera is unavailable."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        validate=validate,
        execute=execute,
    )


def create_camera_skill(
    camera: CameraDevice,
    *,
    image_detail: Literal["low", "high", "auto"] = "auto",
) -> SkillDefinition:
    def validate(arguments: dict[str, Any]) -> None:
        reject_unknown_arguments(arguments, set())

    async def execute(arguments: dict[str, Any]) -> SkillResult:
        try:
            jpeg = await camera.capture_jpeg()
        except CameraError as exc:
            return SkillResult(
                {
                    "ok": False,
                    "error": "camera_capture_failed",
                    "message": str(exc),
                }
            )
        return SkillResult(
            {
                "ok": True,
                "mime_type": "image/jpeg",
                "message": "Captured one camera frame for visual analysis.",
            },
            jpeg=jpeg,
            image_detail=image_detail,
        )

    return SkillDefinition(
        name="capture_camera_image",
        description=(
            "Capture exactly one current camera frame when the user's question requires "
            "visual information. Do not call this tool for questions that can be answered "
            "without seeing the user's surroundings."
        ),
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        validate=validate,
        execute=execute,
    )
