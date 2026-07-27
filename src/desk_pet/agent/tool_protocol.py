from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


class ToolSchema(TypedDict):
    type: str
    name: str
    description: str
    strict: bool
    parameters: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ModelTurn:
    output_items: list[dict[str, Any]]
    output_text: str
    tool_calls: list[ToolCall]
