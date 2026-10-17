"""Long-book outlines, scene budgets, and prompt windows. Mock backend only."""

from __future__ import annotations

from pathlib import Path

import pytest
from plotweaver_dev.mock import MockBackend

from plotweaver.domain import BookMode, BookRequest, Language
from plotweaver.length import (
    CONTEXT_FLOOR,
    DRAFT_PROMPT_FLOOR,
    PLAN_MAX_TOKENS,
    PROOF_INSTRUCTION_TOKENS,
    SCENE_MAX_TOKENS,
    STRUCTURAL_MAX_PAGES,
    SYSTEM_TOKEN_RESERVE,
    call_fits,
    chapter_count_for,
    chapters_per_outline_call,
    estimate_tokens,
    plan_shape,
    proofread_calls,
    scene_max_tokens,
    scene_word_cap,
)
from plotweaver.outline import generate_outline
from plotweaver.prompts import bible_digest, draft_prompt, system_message
from plotweaver.runner import run_book
from plotweaver.store import Project
from plotweaver.vxbook import emitted_chapter_id

_PAGES = (
    (25, 8, 2, 390),
    (250, 20, 3, 1041),
    (550, 43, 3, 1065),
    (2000, 156, 7, 457),
)


def _request(pages: int, *, language: Language = Language.RU) -> BookRequest:
    return BookRequest(
        title="Длинная книга",
        language=language,
        synopsis="Экипаж ведёт корабль через пыль и не торопит шов.",
        target_words=pages * 250,
        chapter_count=None,
        scenes_per_chapter=2,
        mode=BookMode.AUTOPILOT,
        main_model_id="mock-main",
        least_censored_model_id="mock-low",
    )


def _flag(user: str, name: str) -> str:
    prefix = f"{name}:"
    for line in user.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def _phase(call: dict[str, object]) -> str:
    return str(call.get("phase") or "")


@pytest.mark.parametrize(("pages", "chapters", "scenes_each", "words_each"), _PAGES)
def test_page_targets_finish_a_complete_outline(
    tmp_path: Path, pages: int, chapters: int, scenes_each: int, words_each: int
) -> None:
    if pages == STRUCTURAL_MAX_PAGES:
        assert chapters == chapter_count_for(pages * 250)
    request = _request(pages)
    assert request.shape() == (chapters, scenes_each, words_each)
    _chapters, scenes, per_scene = request.shape()
    assert scene_max_tokens(per_scene, "ru") <= SCENE_MAX_TOKENS
    if pages <= 600:
        assert scenes in (2, 3)
        assert per_scene <= 1500
        if pages >= 250:
            assert 1000 <= per_scene <= 1500
            full_draft = CONTEXT_FLOOR - SYSTEM_TOKEN_RESERVE - DRAFT_PROMPT_FLOOR
            assert scene_max_tokens(per_scene, "ru") == full_draft
    else:
        assert per_scene <= scene_word_cap("ru")
        assert scenes > 3
    words = pages * 250
    if words >= 8 * 2500:
        assert 2500 <= words // chapters <= 4000
    else:
        assert chapters == 8

    backend = MockBackend()
    project = Project.open_or_create(tmp_path / f"p{pages}", request)
    bible_gate = run_book(project, backend, yes=False)
    assert bible_gate.gate == "bible"
    outline_gate = run_book(project, backend, yes=False, approve=True)
    assert outline_gate.gate == "outline"

    outline = project.read_artefact("outline.json")
    rows = outline["chapters"]
    assert isinstance(rows, list)
    assert len(rows) == chapters
    ids = [str(item["id"]) for item in rows if isinstance(item, dict)]
    assert ids == [emitted_chapter_id("", index, chapters) for index in range(1, chapters + 1)]
    assert len(set(ids)) == chapters
    budgets = [int(item["word_budget"]) for item in rows if isinstance(item, dict)]
    assert sum(budgets) == words

    parts = outline["parts"]
    assert isinstance(parts, list) and parts
    covered: list[int] = []
    for part in parts:
        assert isinstance(part, dict)
        covered.extend(range(int(part["chapter_start"]), int(part["chapter_end"]) + 1))
    assert covered == list(range(1, chapters + 1))

    secret = "He fears an early ascent."
    batch_numbers: list[int] = []
    saw_parts = False
    for call in backend.calls:
        user = str(call["user"])
        max_tokens = int(str(call["max_tokens"]))
        task = str(call["task"])
        assert max_tokens <= SCENE_MAX_TOKENS
        if task in {"bible", "outline", "beats"}:
            assert max_tokens <= PLAN_MAX_TOKENS
        prompt_tokens = estimate_tokens(system_message(), russian=False) + estimate_tokens(
            user, russian=True
        )
        assert prompt_tokens + max_tokens <= CONTEXT_FLOOR
        if task != "outline":
            continue
        assert secret not in user
        phase = _phase(call)
        if phase == "parts":
            saw_parts = True
        if phase == "chapters":
            start = int(_flag(user, "chapter_start"))
            end = int(_flag(user, "chapter_end"))
            assert 1 <= end - start + 1 <= chapters_per_outline_call()
            batch_numbers.extend(range(start, end + 1))
        assert phase != "repair-chapters"
    assert saw_parts
    assert batch_numbers == list(range(1, chapters + 1))
    assert "draft" not in backend.tasks


def test_explicit_chapter_count_is_kept_and_scenes_scale() -> None:
    request = BookRequest(
        title="Epic",
        language=Language.RU,
        synopsis="A long road.",
        target_words=500_000,
        chapter_count=10,
        scenes_per_chapter=2,
    )
    chapters, scenes, per_scene = request.shape()
    assert chapters == 10
    assert scenes > 2
    assert per_scene <= scene_word_cap("ru")


def test_english_short_book_keeps_two_scenes() -> None:
    request = _request(25, language=Language.EN)
    chapters, scenes, per_scene = request.shape()
    assert chapters == 8
    assert scenes == 2
    assert per_scene <= scene_word_cap("en")


def test_scene_words_are_clamped_without_adding_scenes() -> None:
    request = BookRequest(
        title="Clamped",
        language=Language.RU,
        synopsis="A short order.",
        target_words=20_000,
        chapter_count=8,
        scenes_per_chapter=2,
        scene_words=5_000,
    )
    chapters, scenes, per_scene = request.shape()
    assert (chapters, scenes, per_scene) == (8, 2, scene_word_cap("ru"))


def test_scene_round_trip_fits_the_context_floor() -> None:
    words = scene_word_cap("ru")
    completion = scene_max_tokens(words, "ru")
    full_draft = CONTEXT_FLOOR - SYSTEM_TOKEN_RESERVE - DRAFT_PROMPT_FLOOR
    assert completion <= SCENE_MAX_TOKENS
    assert full_draft - 64 <= completion <= full_draft
    assert plan_shape(500_000, "ru", None, 2)[0] == chapter_count_for(500_000)


def test_proofread_of_a_normal_scene_is_chunked() -> None:
    prose = " ".join(["шов"] * 1041)
    calls = proofread_calls([prose], russian=True)
    assert len(calls) > 1
    covered: list[str] = []
    for max_tokens, pieces in calls:
        assert pieces
        text = "\n\n".join(piece for _index, piece in pieces)
        assert call_fits(
            text,
            russian=True,
            max_tokens=max_tokens,
            instruction_tokens=PROOF_INSTRUCTION_TOKENS,
        )
        assert max_tokens <= SCENE_MAX_TOKENS
        covered.extend(piece for _index, piece in pieces)
    assert " ".join(covered) == prose


def test_repair_puts_a_dropped_chapter_back() -> None:
    class _DropSecond(MockBackend):
        def __init__(self) -> None:
            super().__init__()
            self.dropped = False

        def _outline(self, user: str) -> dict[str, object]:
            payload = super()._outline(user)
            phase = _flag(user, "outline_phase")
            rows = payload.get("chapters")
            if (
                phase == "chapters"
                and not self.dropped
                and isinstance(rows, list)
                and len(rows) > 2
            ):
                self.dropped = True
                payload = dict(payload)
                payload["chapters"] = [rows[0], *rows[2:]]
            return payload

    backend = _DropSecond()
    request = _request(25)
    outline = generate_outline(backend, request, _secret_bible())
    rows = outline["chapters"]
    assert isinstance(rows, list)
    assert [int(item["index"]) for item in rows if isinstance(item, dict)] == list(
        range(1, request.shape()[0] + 1)
    )
    restored = next(item for item in rows if isinstance(item, dict) and item["index"] == 2)
    assert "Move the story through chapter 2" in str(restored["purpose"])
    assert any(_phase(call) == "repair-chapters" for call in backend.calls)


def test_missing_chapters_are_filled_after_repair_fails() -> None:
    class _Empty(MockBackend):
        def _outline(self, user: str) -> dict[str, object]:
            phase = _flag(user, "outline_phase")
            if phase in {"chapters", "repair-chapters"}:
                return {"chapters": []}
            return super()._outline(user)

    backend = _Empty()
    request = _request(25)
    outline = generate_outline(backend, request, _secret_bible())
    rows = outline["chapters"]
    assert isinstance(rows, list)
    assert len(rows) == request.shape()[0]
    assert all(isinstance(item, dict) and "without a jump" in str(item["purpose"]) for item in rows)
    assert any(_phase(call) == "repair-chapters" for call in backend.calls)


def test_oversize_beats_are_split(tmp_path: Path) -> None:
    class _OneScene(MockBackend):
        def _beats(self, user: str) -> dict[str, object]:
            payload = super()._beats(user)
            rows = payload.get("scenes")
            if isinstance(rows, list) and rows:
                payload = dict(payload)
                payload["scenes"] = rows[:1]
            return payload

    request = BookRequest(
        title="Одна сцена",
        language=Language.RU,
        synopsis="Короткий синопсис про шов и пыль.",
        target_words=2_000,
        chapter_count=1,
        scenes_per_chapter=2,
        mode=BookMode.AUTOPILOT,
        main_model_id="mock-main",
    )
    _chapters, scenes, per_scene = request.shape()
    assert scenes > 1
    backend = _OneScene()
    project = Project.open_or_create(tmp_path / "split", request)
    result = run_book(project, backend, yes=True)
    assert result.status == "completed"
    beats = project.read_artefact("beats/ch01.json")
    rows = beats["scenes"]
    assert isinstance(rows, list)
    assert len(rows) == scenes
    assert "part 1 of" in str(rows[0]["goal"])
    assert [str(item["id"]) for item in rows if isinstance(item, dict)] == [
        f"ch01-sc{index:02d}" for index in range(1, scenes + 1)
    ]
    for call in backend.calls:
        task = str(call["task"])
        max_tokens = int(str(call["max_tokens"]))
        if task in {"draft", "fill", "rewrite"}:
            assert max_tokens == scene_max_tokens(per_scene, "ru")
        if task == "proofread":
            user = str(call["user"])
            assert max_tokens <= SCENE_MAX_TOKENS
            assert (
                estimate_tokens(system_message(), russian=False)
                + estimate_tokens(user, russian=True)
                + max_tokens
                <= CONTEXT_FLOOR
            )


def test_scene_prompt_keeps_a_digest_inside_the_window() -> None:
    request = _request(STRUCTURAL_MAX_PAGES)
    bible = _secret_bible()
    bible["logline"] = "пыль " * 400
    continuity = {
        "story_so_far": "сводка " * 400,
        "chapters": [{"id": f"ch{index:03d}", "summary": "глава " * 80} for index in range(1, 181)],
    }
    prompt = draft_prompt(
        request,
        bible,
        {"id": "ch010", "title": "Пыль", "purpose": "Держать шов."},
        {"id": "ch010-sc01", "goal": "Проверить шов."},
        "хвост " * 800,
        "короткие фразы " * 40,
        continuity,
    )
    _chapters, _scenes, per_scene = request.shape()
    completion = scene_max_tokens(per_scene, "ru")
    total = (
        estimate_tokens(system_message(), russian=False)
        + estimate_tokens(prompt, russian=True)
        + completion
    )
    assert total <= CONTEXT_FLOOR
    assert "TASK: draft" in prompt
    assert "BIBLE DIGEST:" in prompt
    assert "STORY SO FAR:" in prompt
    assert "He fears an early ascent." not in prompt
    assert "He fears an early ascent." not in bible_digest(bible)


def test_later_scenes_see_the_rolling_summary(tmp_path: Path) -> None:
    request = BookRequest(
        title="Две главы",
        language=Language.RU,
        synopsis="Экипаж спорит до утра и держит шов.",
        target_words=3_000,
        chapter_count=2,
        scenes_per_chapter=2,
        mode=BookMode.AUTOPILOT,
        main_model_id="mock-main",
    )
    backend = MockBackend()
    project = Project.open_or_create(tmp_path / "roll", request)
    result = run_book(project, backend, yes=True)
    assert result.status == "completed"
    continuity = project.read_artefact("continuity.json")
    assert len(str(continuity["story_so_far"])) <= 700
    stored = continuity["chapters"]
    assert isinstance(stored, list) and len(stored) == 2
    drafts = [
        call
        for call in backend.calls
        if str(call["task"]) == "draft" and "scene_id: ch02" in str(call["user"])
    ]
    assert drafts
    user = str(drafts[0]["user"])
    assert "BIBLE DIGEST:" in user
    assert "STORY SO FAR:" in user
    assert "ch01 keeps the mission moving." in user
    assert "He fears an early ascent." not in user
    assert int(str(drafts[0]["max_tokens"])) <= SCENE_MAX_TOKENS


def _secret_bible() -> dict[str, object]:
    return {
        "logline": "Экипаж держит корабль.",
        "theme": "A schedule is not a promise.",
        "characters": [
            {
                "name": "Илья Воронов",
                "gender": "male",
                "role": "commander",
                "secrets": "He fears an early ascent.",
                "voice": "Short orders.",
                "pronunciation": "Илья\u0301 Воронов",
            }
        ],
    }
