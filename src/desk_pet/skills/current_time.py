from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from desk_pet.skills.registry import SkillDefinition, reject_unknown_arguments

Clock = Callable[[], datetime]


def create_current_time_skill(clock: Clock | None = None) -> SkillDefinition:
    get_now = clock or (lambda: datetime.now().astimezone())

    def validate(arguments: dict[str, Any]) -> None:
        reject_unknown_arguments(arguments, set())

    async def execute(arguments: dict[str, Any]) -> dict[str, Any]:
        now = get_now()
        timezone_name = now.tzname() or "unknown"
        return {
            "ok": True,
            "current_time": now.isoformat(),
            "timezone": timezone_name,
            "utc_offset_seconds": int((now.utcoffset() or UTC.utcoffset(now)).total_seconds()),
        }

    return SkillDefinition(
        name="get_current_time",
        description="Get the current local date, time, timezone, and UTC offset.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        validate=validate,
        execute=execute,
    )
