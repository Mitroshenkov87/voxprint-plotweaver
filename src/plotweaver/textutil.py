"""Russian yo restoration and stress marks taken from the story bible.

Audiobook Builder owns the full yo/stress normaliser. Plotweaver writes yo where a
short unambiguous dictionary is sure, and places the combining acute (U+0301) on
invented names the bible already marked.
"""

from __future__ import annotations

import re

# Unambiguous dictionary forms. "все" (everyone) is intentionally absent: "всё" is a different word.
_YO_WORDS: dict[str, str] = {
    "еще": "ещё",
    "ее": "её",
    "мое": "моё",
    "твое": "твоё",
    "свое": "своё",
    "моею": "моёю",
    "черный": "чёрный",
    "черная": "чёрная",
    "черное": "чёрное",
    "желтый": "жёлтый",
    "зеленый": "зелёный",
    "идет": "идёт",
    "берет": "берёт",
    "течет": "течёт",
    "учет": "учёт",
    "прием": "приём",
    "очем": "очём",
    "причем": "причём",
    "жесткий": "жёсткий",
    "черствый": "чёрствый",
    "пчелы": "пчёлы",
    "счет": "счёт",
    "расчет": "расчёт",
    "легкий": "лёгкий",
    "легкая": "лёгкая",
    "теплый": "тёплый",
    "теплая": "тёплая",
    "мертвый": "мёртвый",
    "звезды": "звёзды",
    "звезда": "звезда",
    "актер": "актёр",
    "режиссер": "режиссёр",
    "шофер": "шофёр",
    "трех": "трёх",
    "четырех": "четырёх",
    "самолет": "самолёт",
    "полет": "полёт",
    "взлет": "взлёт",
    "надежный": "надёжный",
    "сестры": "сёстры",
    "слезы": "слёзы",
    "береза": "берёза",
    "бересте": "берёсте",
}


def _match_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def restore_yo(text: str) -> str:
    """Replace dictionary words that must be written with yo (U+0451 / U+0401)."""

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        mapped = _YO_WORDS.get(word.lower())
        if mapped is None:
            return word
        return _match_case(word, mapped)

    return re.sub(r"[0-9A-Za-zА-Яа-яЁё]+", replace, text)


def apply_pronunciations(text: str, pronunciations: list[tuple[str, str]]) -> str:
    """Swap a bible surface form for the stressed form when the acute is not already there.

    ``pronunciations`` is a list of (surface, stressed). The stressed string uses U+0301
    immediately after the stressed vowel. A word that already contains the acute is left alone.
    """
    result = text
    for surface, stressed in pronunciations:
        surface = surface.strip()
        stressed = stressed.strip()
        if not surface or not stressed or surface == stressed:
            continue
        if "\u0301" in surface:
            continue

        pattern = re.compile(rf"(?<![\w\u0301]){re.escape(surface)}(?![\w])", re.IGNORECASE)
        # Combining marks are not \\w. Look ahead in the original for an acute glued to the word.
        pieces: list[str] = []
        cursor = 0
        for match in pattern.finditer(result):
            after = result[match.end() : match.end() + 4]
            if "\u0301" in after and not after[:1].isalnum():
                continue
            # Also skip when the acute is inside a decomposed vowel we already wrote.
            if "\u0301" in result[match.start() : match.end() + 2]:
                continue
            pieces.append(result[cursor : match.start()])
            found = match.group(0)
            pieces.append(_match_case(found, stressed))
            cursor = match.end()
        pieces.append(result[cursor:])
        result = "".join(pieces)
    return result


def prepare_prose(text: str, pronunciations: list[tuple[str, str]]) -> str:
    """Yo dictionary, then bible stress marks. Paragraph-internal newlines become spaces."""
    collapsed = re.sub(r"\s*\n\s*", " ", text).strip()
    return apply_pronunciations(restore_yo(collapsed), pronunciations)
