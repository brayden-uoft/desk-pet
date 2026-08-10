from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, NotRequired, TypedDict


class ToolSchema(TypedDict):
    type: str
    name: str
    description: str
    strict: bool
    parameters: dict[str, Any]


class WebSearchTool(TypedDict):
    type: Literal["web_search"]
    search_context_size: Literal["low", "medium", "high"]


class MCPConnectorTool(TypedDict):
    type: Literal["mcp"]
    server_label: str
    server_description: str
    connector_id: str
    authorization: str
    require_approval: Literal["never"]
    allowed_tools: list[str]


class RemoteMCPTool(TypedDict):
    type: Literal["mcp"]
    server_label: str
    server_description: str
    server_url: str
    authorization: str
    require_approval: Literal["never"]
    allowed_tools: NotRequired[list[str]]


MCPTool = MCPConnectorTool | RemoteMCPTool
ModelTool = ToolSchema | WebSearchTool | MCPTool


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
