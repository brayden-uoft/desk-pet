from __future__ import annotations

import re

_PARENTHESIZED_MARKDOWN_LINK = re.compile(r"\(\s*\[([^\]\n]+)\]\(\s*<?https?://[^\s>\n]+>?\)\s*\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]\n]+)\]\(\s*<?https?://[^\s>\n]+>?\)")
_AUTOLINK = re.compile(r"<?(?:https?://|www\.)[^\s<]+>?", re.IGNORECASE)
_EMPTY_PARENS = re.compile(r"\(\s*\)")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.;:!?])")
_EXCESS_SPACES = re.compile(r"[ \t]{2,}")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def text_for_speech(text: str) -> str:
    """Keep useful prose while removing URLs that TTS would laboriously spell."""
    spoken = _PARENTHESIZED_MARKDOWN_LINK.sub(r"\1", text)
    spoken = _MARKDOWN_LINK.sub(r"\1", spoken)
    spoken = _AUTOLINK.sub(_remove_bare_url, spoken)
    spoken = _EMPTY_PARENS.sub("", spoken)
    spoken = spoken.replace("**", "").replace("__", "").replace("`", "")
    spoken = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", spoken)
    spoken = _EXCESS_SPACES.sub(" ", spoken)
    spoken = _EXCESS_BLANK_LINES.sub("\n\n", spoken)
    return spoken.strip()


def _remove_bare_url(match: re.Match[str]) -> str:
    matched = match.group(0)
    if matched[-1:] in ".,;:!?":
        return matched[-1]
    return ""
