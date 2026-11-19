"""Pull a JSON object out of a model reply that may contain a think channel or fences."""

from __future__ import annotations

import json
import re
from typing import Any

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Return the JSON object in a model reply, or None when it is not there."""
    value, _how = load_json_object(text)
    return value


def load_json_object(text: str) -> tuple[dict[str, Any] | None, str]:
    """Return the object and ``plain``, ``repaired``, or ``none``.

    ``plain`` is a reply that is one JSON object. The repair pass strips a think
    channel, fences, and prose, then drops trailing commas.
    """
    cleaned = _THINK.sub("", text).strip()
    direct = _loads_whole(cleaned)
    if direct is not None:
        return direct, "plain"
    repaired = _loads_whole(_repair_text(cleaned))
    if repaired is not None:
        return repaired, "repaired"
    return None, "none"


def _repair_text(text: str) -> str:
    cleaned = re.sub(r"```(?:json)?", "", text)
    cleaned = cleaned.replace("```", "").strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return cleaned
    return _strip_trailing_commas(cleaned[start : end + 1])


def _loads_whole(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(value, dict):
        return value
    return None


def _strip_trailing_commas(text: str) -> str:
    out: list[str] = []
    in_string = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        if in_string:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            out.append(char)
            index += 1
            continue
        if char == ",":
            look = index + 1
            while look < len(text) and text[look] in " \t\r\n":
                look += 1
            if look < len(text) and text[look] in "}]":
                index += 1
                continue
        out.append(char)
        index += 1
    return "".join(out)
