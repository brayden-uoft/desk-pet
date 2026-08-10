from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from desk_pet.hardware.interfaces import CameraDevice
from desk_pet.integrations.interfaces import OutlookClassicService
from desk_pet.skills.current_time import create_current_time_skill
from desk_pet.skills.outlook_classic import (
    create_outlook_calendar_skill,
    create_outlook_mail_skill,
)
from desk_pet.skills.registry import SkillRegistry
from desk_pet.skills.take_photo import create_camera_skill, create_camera_stub_skill
from desk_pet.skills.timer import TimerSkill


def create_default_skill_registry(
    output: Callable[[str], None] = print,
    *,
    camera: CameraDevice | None = None,
    image_detail: Literal["low", "high", "auto"] = "auto",
    outlook: OutlookClassicService | None = None,
) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(create_current_time_skill())
    registry.register(TimerSkill(notify=output).definition())
    if camera is None:
        registry.register(create_camera_stub_skill())
    else:
        registry.register(create_camera_skill(camera, image_detail=image_detail))
    if outlook is not None:
        registry.register(create_outlook_mail_skill(outlook))
        registry.register(create_outlook_calendar_skill(outlook))
    return registry
