from __future__ import annotations

from typing import Any

from desk_pet.skills.registry import SkillDefinition, reject_unknown_arguments


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
