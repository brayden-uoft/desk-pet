import asyncio
import base64
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from desk_pet.camera.errors import CameraError
from desk_pet.skills.current_time import create_current_time_skill
from desk_pet.skills.registry import SkillRegistry, SkillValidationError
from desk_pet.skills.take_photo import create_camera_skill, create_camera_stub_skill
from desk_pet.skills.timer import TimerSkill
from tests.fakes.hardware import FakeCamera


def _json_result(output: object) -> dict[str, object]:
    assert isinstance(output, str)
    result = json.loads(output)
    assert isinstance(result, dict)
    return result


def test_registry_exposes_strict_schemas_and_executes_current_time() -> None:
    async def scenario() -> None:
        fixed_time = datetime(2026, 7, 27, 15, 30, tzinfo=timezone(timedelta(hours=-4)))
        registry = SkillRegistry()
        registry.register(create_current_time_skill(lambda: fixed_time))

        schemas = registry.schemas()
        result = _json_result(await registry.execute("get_current_time", "{}"))

        assert schemas[0]["strict"] is True
        assert schemas[0]["parameters"]["additionalProperties"] is False
        assert result["current_time"] == "2026-07-27T15:30:00-04:00"
        assert result["utc_offset_seconds"] == -14400

    asyncio.run(scenario())


def test_registry_rejects_non_strict_schema() -> None:
    registry = SkillRegistry()
    skill = replace(
        create_current_time_skill(),
        parameters={
            "type": "object",
            "properties": {"optional": {"type": "string"}},
            "required": [],
            "additionalProperties": False,
        },
    )

    with pytest.raises(ValueError, match="strict object schema"):
        registry.register(skill)


def test_timer_rejects_invalid_arguments() -> None:
    async def scenario() -> None:
        registry = SkillRegistry()
        registry.register(TimerSkill().definition())

        with pytest.raises(SkillValidationError, match="1 to 86400"):
            await registry.execute("start_timer", '{"seconds": 0, "label": null}')

    asyncio.run(scenario())


def test_timer_completes_without_blocking_tool_result() -> None:
    async def scenario() -> None:
        notifications: list[str] = []

        async def instant_sleep(seconds: float) -> None:
            return None

        registry = SkillRegistry()
        registry.register(TimerSkill(notify=notifications.append, sleep=instant_sleep).definition())

        result = _json_result(
            await registry.execute("start_timer", '{"seconds": 5, "label": "tea"}')
        )
        await asyncio.sleep(0)

        assert result["ok"] is True
        assert result["seconds"] == 5
        assert notifications == ["\n⏰ Timer complete: tea"]

    asyncio.run(scenario())


def test_camera_stub_reports_unavailable() -> None:
    async def scenario() -> None:
        registry = SkillRegistry()
        registry.register(create_camera_stub_skill())

        result = _json_result(await registry.execute("capture_camera_image", "{}"))

        assert result == {
            "error": "camera_not_available",
            "message": "Camera capture will be enabled in Stage 5.",
            "ok": False,
        }

    asyncio.run(scenario())


def test_camera_skill_returns_one_in_memory_jpeg_to_the_model() -> None:
    async def scenario() -> None:
        camera = FakeCamera()
        registry = SkillRegistry()
        registry.register(create_camera_skill(camera, image_detail="high"))

        output = await registry.execute("capture_camera_image", "{}")

        assert camera.calls == 1
        assert isinstance(output, list)
        text_item = output[0]
        assert text_item["type"] == "input_text"
        assert json.loads(text_item["text"]) == {
            "message": "Captured one camera frame for visual analysis.",
            "mime_type": "image/jpeg",
            "ok": True,
        }
        image_item = output[1]
        assert image_item["type"] == "input_image"
        assert image_item["detail"] == "high"
        prefix, encoded = image_item["image_url"].split(",", 1)
        assert prefix == "data:image/jpeg;base64"
        assert base64.b64decode(encoded) == camera.jpeg

    asyncio.run(scenario())


def test_camera_failure_is_returned_as_a_safe_text_result() -> None:
    class FailingCamera:
        async def capture_jpeg(self) -> bytes:
            raise CameraError("Camera is busy.")

    async def scenario() -> None:
        registry = SkillRegistry()
        registry.register(create_camera_skill(FailingCamera()))

        result = _json_result(await registry.execute("capture_camera_image", "{}"))

        assert result == {
            "error": "camera_capture_failed",
            "message": "Camera is busy.",
            "ok": False,
        }

    asyncio.run(scenario())
