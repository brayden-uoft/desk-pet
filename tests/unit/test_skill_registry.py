import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from desk_pet.skills.current_time import create_current_time_skill
from desk_pet.skills.registry import SkillRegistry, SkillValidationError
from desk_pet.skills.take_photo import create_camera_stub_skill
from desk_pet.skills.timer import TimerSkill


def test_registry_exposes_strict_schemas_and_executes_current_time() -> None:
    async def scenario() -> None:
        fixed_time = datetime(2026, 7, 27, 15, 30, tzinfo=timezone(timedelta(hours=-4)))
        registry = SkillRegistry()
        registry.register(create_current_time_skill(lambda: fixed_time))

        schemas = registry.schemas()
        result = json.loads(await registry.execute("get_current_time", "{}"))

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

        result = json.loads(await registry.execute("start_timer", '{"seconds": 5, "label": "tea"}'))
        await asyncio.sleep(0)

        assert result["ok"] is True
        assert result["seconds"] == 5
        assert notifications == ["\n⏰ Timer complete: tea"]

    asyncio.run(scenario())


def test_camera_stub_reports_unavailable() -> None:
    async def scenario() -> None:
        registry = SkillRegistry()
        registry.register(create_camera_stub_skill())

        result = json.loads(await registry.execute("capture_camera_image", "{}"))

        assert result == {
            "error": "camera_not_available",
            "message": "Camera capture will be enabled in Stage 5.",
            "ok": False,
        }

    asyncio.run(scenario())
