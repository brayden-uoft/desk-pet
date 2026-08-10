from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

_EXTERNAL_SIGNAL = re.compile(
    r"\b(?:"
    r"calendar|schedule|meeting|appointment|event|email|gmail|outlook|inbox|message|"
    r"weather|forecast|temperature|news|headline|latest|current events?|today|tomorrow|"
    r"internet|online|web|search|look up|github|repository|pull request|issue|notion|"
    r"drive|dropbox|sharepoint|document|spreadsheet|slides?|file|slack|teams|toronto"
    r")\b",
    re.IGNORECASE,
)
_DEFINITELY_LOCAL = re.compile(
    r"^(?:"
    r"(?:please\s+)?(?:say|repeat|reply with|respond with)\b|"
    r"h+i+\b|hello\b|hey(?:\s+deskbob)?\b|"
    r"thanks?\b|thank you\b|good(?:bye|night)\b|"
    r"again\b|one more(?: time)?\b"
    r")",
    re.IGNORECASE,
)


def should_offer_external_tools(input_items: Sequence[dict[str, Any]]) -> bool:
    """Skip expensive external tools only for high-confidence local conversation."""

    user_texts = [
        str(item.get("content", "")).strip()
        for item in input_items
        if item.get("role") == "user" and isinstance(item.get("content"), str)
    ]
    if not user_texts:
        return True
    latest = user_texts[-1]
    if _EXTERNAL_SIGNAL.search(latest):
        return True
    return _DEFINITELY_LOCAL.search(latest) is None
