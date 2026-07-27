from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, TypedDict


class ToolSchema(TypedDict):
    type: str
    name: str
    description: str
    strict: bool
    parameters: dict[str, Any]


class ToolOutputText(TypedDict):
    type: Literal["input_text"]
    text: str


class ToolOutputImage(TypedDict):
    type: Literal["input_image"]
    image_url: str
    detail: Literal["low", "high", "auto"]


ToolOutput = str | list[ToolOutputText | ToolOutputImage]


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
