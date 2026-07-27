from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from desk_pet.skills.registry import (
    SkillDefinition,
    SkillValidationError,
    reject_unknown_arguments,
)

Notifier = Callable[[str], None]
Sleeper = Callable[[float], Awaitable[None]]


class TimerSkill:
    def __init__(
        self,
        *,
        notify: Notifier = print,
        sleep: Sleeper = asyncio.sleep,
    ) -> None:
        self._notify = notify
        self._sleep = sleep
        self._tasks: set[asyncio.Task[None]] = set()

    def definition(self) -> SkillDefinition:
        return SkillDefinition(
            name="start_timer",
            description="Start a countdown timer for 1 to 86400 seconds.",
            parameters={
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 86400,
                        "description": "Timer duration in whole seconds.",
                    },
                    "label": {
                        "type": ["string", "null"],
                        "description": "Optional short name for the timer.",
                    },
                },
                "required": ["seconds", "label"],
                "additionalProperties": False,
            },
            validate=self._validate,
            execute=self._execute,
        )

    @staticmethod
    def _validate(arguments: dict[str, Any]) -> None:
        reject_unknown_arguments(arguments, {"seconds", "label"})
        if set(arguments) != {"seconds", "label"}:
            raise SkillValidationError("seconds and label are required")
        seconds = arguments["seconds"]
        label = arguments["label"]
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not 1 <= seconds <= 86400:
            raise SkillValidationError("seconds must be an integer from 1 to 86400")
        if label is not None and (not isinstance(label, str) or len(label) > 80):
            raise SkillValidationError("label must be null or a string up to 80 characters")

    async def _execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        seconds = int(arguments["seconds"])
        label_value = arguments["label"]
        label = label_value.strip() if isinstance(label_value, str) else ""
        timer_id = uuid.uuid4().hex[:8]
        task = asyncio.create_task(self._run_timer(timer_id, seconds, label))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return {
            "ok": True,
            "timer_id": timer_id,
            "seconds": seconds,
            "label": label or None,
        }

    async def _run_timer(self, timer_id: str, seconds: int, label: str) -> None:
        await self._sleep(seconds)
        display_name = label or timer_id
        self._notify(f"\n⏰ Timer complete: {display_name}")
