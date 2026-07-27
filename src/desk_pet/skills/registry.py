from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from desk_pet.agent.tool_protocol import ToolSchema

LOGGER = logging.getLogger(__name__)

SkillHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
SkillValidator = Callable[[dict[str, Any]], None]


class SkillError(RuntimeError):
    code = "skill_error"


class SkillNotFoundError(SkillError):
    code = "skill_not_found"


class SkillValidationError(SkillError):
    code = "invalid_arguments"


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    validate: SkillValidator
    execute: SkillHandler

    def schema(self) -> ToolSchema:
        return ToolSchema(
            type="function",
            name=self.name,
            description=self.description,
            strict=True,
            parameters=self.parameters,
        )


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        properties = skill.parameters.get("properties")
        required = skill.parameters.get("required")
        if (
            skill.parameters.get("type") != "object"
            or not isinstance(properties, dict)
            or not isinstance(required, list)
            or skill.parameters.get("additionalProperties") is not False
            or set(required) != set(properties)
        ):
            raise ValueError(
                f"Skill {skill.name} must use a strict object schema with every property required"
            )
        self._skills[skill.name] = skill

    def schemas(self) -> list[ToolSchema]:
        return [skill.schema() for skill in self._skills.values()]

    async def execute(self, name: str, arguments_json: str) -> str:
        skill = self._skills.get(name)
        if skill is None:
            raise SkillNotFoundError(f"Unknown skill: {name}")
        try:
            arguments = json.loads(arguments_json)
        except json.JSONDecodeError as exc:
            raise SkillValidationError("Arguments must be valid JSON") from exc
        if not isinstance(arguments, dict):
            raise SkillValidationError("Arguments must be a JSON object")

        skill.validate(arguments)
        LOGGER.info("Executing approved skill: %s", name)
        result = await skill.execute(arguments)
        return json.dumps(result, separators=(",", ":"), sort_keys=True)


def reject_unknown_arguments(arguments: dict[str, Any], allowed: set[str]) -> None:
    unknown = set(arguments) - allowed
    if unknown:
        raise SkillValidationError(f"Unknown arguments: {', '.join(sorted(unknown))}")
