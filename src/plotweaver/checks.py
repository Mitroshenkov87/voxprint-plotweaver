"""Lightweight checks. A hit is a note for at most one rewrite, not a retry loop."""

from __future__ import annotations

import re

_REFUSAL = re.compile(
    r"("
    r"\bi cannot\b|"
    r"\bi can't\b|"
    r"\bi must refuse\b|"
    r"\bas an ai\b|"
    r"\bi won't (write|generate|continue)\b|"
    r"\bcontent policy\b|"
    r"я не могу|"
    r"не могу это написать|"
    r"как языковая модель|"
    r"я должен отказаться"
    r")",
    re.IGNORECASE,
)

_SANITISING = (
    "fade to black",
    "some things are better left unsaid",
    "я предпочту не описывать",
    "дальше всё было прилично",
)

_SLOP = (
    "little did they know",
    "a testament to",
    "сердце бешено колотилось",
    "не мог не заметить",
    "время словно остановилось",
)


def is_refusal(text: str) -> bool:
    """True when the prose contains a model refusal."""
    return _REFUSAL.search(text) is not None


def is_sanitised(text: str) -> bool:
    """True when the prose contains a softening phrase."""
    lowered = text.lower()
    return any(phrase in lowered for phrase in _SANITISING)


def chapter_problems(text: str) -> list[str]:
    """Deterministic problems. Empty means the chapter is left as written."""
    problems: list[str] = []
    if is_refusal(text):
        problems.append("a refusal or disclaimer is still in the prose")
    lowered = text.lower()
    for phrase in _SLOP:
        if phrase in lowered:
            problems.append(f"anti-slop phrase: {phrase}")
            break
    words = re.findall(r"\w+", lowered, flags=re.UNICODE)
    counts: dict[tuple[str, ...], int] = {}
    for index in range(0, max(0, len(words) - 5)):
        gram = tuple(words[index : index + 6])
        counts[gram] = counts.get(gram, 0) + 1
        if counts[gram] >= 3:
            problems.append("a 6-word sequence repeats three times")
            break
    return problems
