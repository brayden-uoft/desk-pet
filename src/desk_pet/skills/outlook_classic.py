from __future__ import annotations

from datetime import datetime
from typing import Any

from desk_pet.integrations.interfaces import OutlookClassicService
from desk_pet.integrations.outlook_classic import OutlookClassicError
from desk_pet.skills.registry import (
    SkillDefinition,
    SkillValidationError,
    reject_unknown_arguments,
)


def create_outlook_mail_skill(service: OutlookClassicService) -> SkillDefinition:
    async def execute(arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            messages = await service.search_mail(
                str(arguments["query"]),
                maximum_results=int(arguments["maximum_results"]),
                include_body=bool(arguments["include_body"]),
            )
        except OutlookClassicError as exc:
            return {"ok": False, "error": "outlook_unavailable", "message": str(exc)}
        return {"ok": True, "messages": messages, "count": len(messages)}

    return SkillDefinition(
        name="search_outlook_mail",
        description=(
            "Search recent read-only email in the Outlook Classic accounts signed in on "
            "this Windows computer. Use an empty query to retrieve the newest messages."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "maxLength": 200,
                    "description": "Words to match in sender, subject, or message body.",
                },
                "maximum_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                },
                "include_body": {
                    "type": "boolean",
                    "description": "Include a short body excerpt only when needed.",
                },
            },
            "required": ["query", "maximum_results", "include_body"],
            "additionalProperties": False,
        },
        validate=_validate_mail,
        execute=execute,
    )


def create_outlook_calendar_skill(service: OutlookClassicService) -> SkillDefinition:
    async def execute(arguments: dict[str, Any]) -> dict[str, Any]:
        start = _parse_datetime(str(arguments["start"]), "start")
        end = _parse_datetime(str(arguments["end"]), "end")
        try:
            events = await service.calendar_events(
                start,
                end,
                maximum_results=int(arguments["maximum_results"]),
            )
        except OutlookClassicError as exc:
            return {"ok": False, "error": "outlook_unavailable", "message": str(exc)}
        return {"ok": True, "events": events, "count": len(events)}

    return SkillDefinition(
        name="read_outlook_calendar",
        description=(
            "Read Outlook Classic calendar events from signed-in accounts for an explicit "
            "time range. This tool cannot create, update, or delete events."
        ),
        parameters={
            "type": "object",
            "properties": {
                "start": {
                    "type": "string",
                    "description": "Inclusive ISO 8601 timestamp with UTC offset.",
                },
                "end": {
                    "type": "string",
                    "description": "Exclusive ISO 8601 timestamp with UTC offset.",
                },
                "maximum_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                },
            },
            "required": ["start", "end", "maximum_results"],
            "additionalProperties": False,
        },
        validate=_validate_calendar,
        execute=execute,
    )


def _validate_mail(arguments: dict[str, Any]) -> None:
    required = {"query", "maximum_results", "include_body"}
    reject_unknown_arguments(arguments, required)
    if set(arguments) != required:
        raise SkillValidationError("query, maximum_results, and include_body are required")
    query = arguments["query"]
    maximum_results = arguments["maximum_results"]
    include_body = arguments["include_body"]
    if not isinstance(query, str) or len(query) > 200:
        raise SkillValidationError("query must be a string up to 200 characters")
    if (
        not isinstance(maximum_results, int)
        or isinstance(maximum_results, bool)
        or not 1 <= maximum_results <= 10
    ):
        raise SkillValidationError("maximum_results must be an integer from 1 to 10")
    if not isinstance(include_body, bool):
        raise SkillValidationError("include_body must be true or false")


def _validate_calendar(arguments: dict[str, Any]) -> None:
    required = {"start", "end", "maximum_results"}
    reject_unknown_arguments(arguments, required)
    if set(arguments) != required:
        raise SkillValidationError("start, end, and maximum_results are required")
    start = _parse_datetime(arguments["start"], "start")
    end = _parse_datetime(arguments["end"], "end")
    if end <= start:
        raise SkillValidationError("end must be after start")
    maximum_results = arguments["maximum_results"]
    if (
        not isinstance(maximum_results, int)
        or isinstance(maximum_results, bool)
        or not 1 <= maximum_results <= 20
    ):
        raise SkillValidationError("maximum_results must be an integer from 1 to 20")


def _parse_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise SkillValidationError(f"{name} must be an ISO 8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SkillValidationError(f"{name} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SkillValidationError(f"{name} must include a UTC offset")
    return parsed
