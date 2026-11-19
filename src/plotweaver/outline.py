"""Hierarchical outline: parts, then chapter batches, then repair.

A single 2,048-token call cannot hold a long chapter list. Parts come first.
Chapters are then requested in batches that fit that budget. A missing index
gets one repair call. Anything still missing is filled locally so the book
never starts a draft with a hole in the chapter list.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from plotweaver.domain import BookRequest
from plotweaver.length import (
    PLAN_MAX_TOKENS,
    chapter_word_budgets,
    chapters_per_outline_call,
)
from plotweaver.llm import ChatMessage, LLMBackend, complete_json
from plotweaver.prompts import (
    outline_chapters_prompt,
    outline_parts_prompt,
    outline_repair_prompt,
    system_message,
)
from plotweaver.vxbook import emitted_chapter_id


def generate_outline(
    backend: LLMBackend,
    request: BookRequest,
    bible: dict[str, Any],
    *,
    log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Build ``parts`` and a complete ``chapters`` list for ``request.shape()``."""
    chapter_count, _scenes, _per_scene = request.shape()
    budgets = chapter_word_budgets(request.target_words, chapter_count)
    spans = _batch_spans(1, chapter_count, chapters_per_outline_call())

    def _log(message: str) -> None:
        if log is not None:
            log(message)

    _log("outline parts")
    parts = _resolve_parts(backend, request, bible, spans, chapter_count, _log)
    rows: list[dict[str, Any]] = []
    for part in parts:
        start = int(part["chapter_start"])
        end = int(part["chapter_end"])
        for batch_start, batch_end in _batch_spans(start, end, chapters_per_outline_call()):
            _log(f"outline chapters {batch_start}-{batch_end}")
            found = _collect_batch(
                backend,
                request,
                bible,
                part,
                batch_start,
                batch_end,
                budgets,
                _log,
            )
            for index in range(batch_start, batch_end + 1):
                rows.append(found[index])
    total = len(rows)
    for position, row in enumerate(rows, start=1):
        row["id"] = emitted_chapter_id("", position, total)
        row["word_budget"] = budgets[position - 1]
    return {"parts": parts, "chapters": rows}


def _resolve_parts(
    backend: LLMBackend,
    request: BookRequest,
    bible: dict[str, Any],
    spans: list[tuple[int, int]],
    chapter_count: int,
    log: Callable[[str], None],
) -> list[dict[str, Any]]:
    payload = _complete(backend, outline_parts_prompt(request, bible, spans))
    parts = _parts_from_payload(payload, chapter_count)
    missing = _missing_numbers(_covered(parts), chapter_count)
    if missing:
        log("outline repair parts")
        gap_spans = _batch_spans_for(missing, chapters_per_outline_call())
        repaired = _complete(
            backend,
            outline_repair_prompt(
                request,
                bible,
                kind="parts",
                start=missing[0],
                end=missing[-1],
                missing=missing,
                spans=gap_spans,
                part=None,
                budgets={},
            ),
        )
        parts = _merge_parts(parts, _parts_from_payload(repaired, chapter_count), chapter_count)
        missing = _missing_numbers(_covered(parts), chapter_count)
    if missing:
        parts = _merge_parts(parts, _synthetic_parts(missing), chapter_count)
    return _reindex(parts)


def _collect_batch(
    backend: LLMBackend,
    request: BookRequest,
    bible: dict[str, Any],
    part: dict[str, Any],
    start: int,
    end: int,
    budgets: list[int],
    log: Callable[[str], None],
) -> dict[int, dict[str, Any]]:
    budget_map = {index: budgets[index - 1] for index in range(start, end + 1)}
    payload = _complete(
        backend,
        outline_chapters_prompt(request, bible, part, start, end, budget_map),
    )
    found = _chapters_from_payload(payload, start, end, request)
    for row in found.values():
        row["part_index"] = int(part.get("index") or 0)
    missing = [index for index in range(start, end + 1) if index not in found]
    if missing:
        log(f"outline repair chapters {missing[0]}-{missing[-1]}")
        repaired = _complete(
            backend,
            outline_repair_prompt(
                request,
                bible,
                kind="chapters",
                start=start,
                end=end,
                missing=missing,
                spans=[(start, end)],
                part=part,
                budgets=budget_map,
            ),
        )
        extra = _chapters_from_payload(repaired, start, end, request)
        for row in extra.values():
            row["part_index"] = int(part.get("index") or 0)
        for index in missing:
            if index in extra:
                found[index] = extra[index]
        missing = [index for index in range(start, end + 1) if index not in found]
    for index in missing:
        found[index] = _synthetic_chapter(index, request, part)
    return found


def _complete(backend: LLMBackend, prompt: str) -> dict[str, Any]:
    payload = complete_json(
        backend,
        [ChatMessage("system", system_message()), ChatMessage("user", prompt)],
        temperature=0.4,
        max_tokens=PLAN_MAX_TOKENS,
    )
    return payload


def _batch_spans(start: int, end: int, size: int) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    cursor = start
    step = max(1, size)
    while cursor <= end:
        batch_end = min(end, cursor + step - 1)
        spans.append((cursor, batch_end))
        cursor = batch_end + 1
    return spans


def _batch_spans_for(numbers: list[int], size: int) -> list[tuple[int, int]]:
    if not numbers:
        return []
    ordered = sorted(set(numbers))
    runs: list[tuple[int, int]] = []
    run_start = ordered[0]
    previous = ordered[0]
    for number in ordered[1:]:
        if number == previous + 1:
            previous = number
            continue
        runs.append((run_start, previous))
        run_start = number
        previous = number
    runs.append((run_start, previous))
    spans: list[tuple[int, int]] = []
    for run_start, run_end in runs:
        spans.extend(_batch_spans(run_start, run_end, size))
    return spans


def _parts_from_payload(payload: dict[str, Any], chapter_count: int) -> list[dict[str, Any]]:
    raw = payload.get("parts")
    if not isinstance(raw, list):
        return []
    parts: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        start = _as_int(item.get("chapter_start"))
        end = _as_int(item.get("chapter_end"))
        if start is None or end is None:
            continue
        start = max(1, min(chapter_count, start))
        end = max(1, min(chapter_count, end))
        if end < start:
            continue
        index = _as_int(item.get("index")) or (len(parts) + 1)
        title = str(item.get("title") or f"Part {index}").strip() or f"Part {index}"
        purpose = str(item.get("purpose") or "Advance the story.").strip() or "Advance the story."
        parts.append(
            {
                "index": index,
                "title": title,
                "purpose": purpose,
                "chapter_start": start,
                "chapter_end": end,
            }
        )
    return _without_overlaps(parts, chapter_count)


def _without_overlaps(parts: list[dict[str, Any]], chapter_count: int) -> list[dict[str, Any]]:
    owner: dict[int, int] = {}
    for position, part in enumerate(parts):
        start = int(part["chapter_start"])
        end = int(part["chapter_end"])
        for number in range(start, end + 1):
            if 1 <= number <= chapter_count and number not in owner:
                owner[number] = position
    resolved: list[dict[str, Any]] = []
    for position, part in enumerate(parts):
        numbers = sorted(number for number, who in owner.items() if who == position)
        if not numbers:
            continue
        for run_start, run_end in _runs(numbers):
            resolved.append(
                {
                    "index": part["index"],
                    "title": part["title"],
                    "purpose": part["purpose"],
                    "chapter_start": run_start,
                    "chapter_end": run_end,
                }
            )
    resolved.sort(key=lambda item: int(item["chapter_start"]))
    return resolved


def _merge_parts(
    current: list[dict[str, Any]],
    extra: list[dict[str, Any]],
    chapter_count: int,
) -> list[dict[str, Any]]:
    return _without_overlaps([*current, *extra], chapter_count)


def _synthetic_parts(missing: list[int]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for start, end in _batch_spans_for(missing, chapters_per_outline_call()):
        parts.append(
            {
                "index": len(parts) + 1,
                "title": f"Part {start}",
                "purpose": f"Cover chapters {start} through {end}.",
                "chapter_start": start,
                "chapter_end": end,
            }
        )
    return parts


def _reindex(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(parts, key=lambda item: int(item["chapter_start"]))
    for position, part in enumerate(ordered, start=1):
        part["index"] = position
    return ordered


def _covered(parts: list[dict[str, Any]]) -> set[int]:
    found: set[int] = set()
    for part in parts:
        start = int(part["chapter_start"])
        end = int(part["chapter_end"])
        found.update(range(start, end + 1))
    return found


def _missing_numbers(covered: set[int], chapter_count: int) -> list[int]:
    return [number for number in range(1, chapter_count + 1) if number not in covered]


def _chapters_from_payload(
    payload: dict[str, Any],
    start: int,
    end: int,
    request: BookRequest,
) -> dict[int, dict[str, Any]]:
    raw = payload.get("chapters")
    if not isinstance(raw, list):
        return {}
    found: dict[int, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        index = _chapter_index(item)
        if index is None or index < start or index > end or index in found:
            continue
        found[index] = _clean_chapter(item, index, request)
    return found


def _clean_chapter(item: dict[str, Any], index: int, request: BookRequest) -> dict[str, Any]:
    title = str(item.get("title") or f"Chapter {index}").strip() or f"Chapter {index}"
    purpose = str(item.get("purpose") or "Carry the story forward.").strip()
    pov = str(item.get("pov") or request.pov).strip() or request.pov
    return {
        "index": index,
        "title": title,
        "purpose": purpose or "Carry the story forward.",
        "pov": pov,
        "word_budget": 0,
        "dark_hint": bool(item.get("dark_hint")),
        "part_index": 0,
    }


def _synthetic_chapter(
    index: int,
    request: BookRequest,
    part: dict[str, Any],
) -> dict[str, Any]:
    return {
        "index": index,
        "title": f"Chapter {index}",
        "purpose": "Carry the story forward without a jump.",
        "pov": request.pov,
        "word_budget": 0,
        "dark_hint": False,
        "part_index": int(part.get("index") or 0),
    }


def _chapter_index(item: dict[str, Any]) -> int | None:
    direct = _as_int(item.get("index"))
    if direct is not None:
        return direct
    raw = str(item.get("id") or "").strip().lower()
    if raw.startswith("ch") and raw[2:].isdigit():
        return int(raw[2:])
    return _as_int(raw)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.lstrip("-").isdigit():
            return int(text)
    return None


def _runs(numbers: list[int]) -> list[tuple[int, int]]:
    if not numbers:
        return []
    ordered = sorted(numbers)
    runs: list[tuple[int, int]] = []
    start = previous = ordered[0]
    for number in ordered[1:]:
        if number == previous + 1:
            previous = number
            continue
        runs.append((start, previous))
        start = previous = number
    runs.append((start, previous))
    return runs
