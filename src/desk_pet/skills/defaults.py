from __future__ import annotations

from collections.abc import Callable

from desk_pet.skills.current_time import create_current_time_skill
from desk_pet.skills.registry import SkillRegistry
from desk_pet.skills.take_photo import create_camera_stub_skill
from desk_pet.skills.timer import TimerSkill


def create_default_skill_registry(
    output: Callable[[str], None] = print,
) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(create_current_time_skill())
    registry.register(TimerSkill(notify=output).definition())
    registry.register(create_camera_stub_skill())
    return registry
