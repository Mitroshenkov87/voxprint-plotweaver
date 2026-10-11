"""Mock pipeline: export shape, dark-theme swap, refusal, and resume."""

from __future__ import annotations

import zipfile
from pathlib import Path

from plotweaver_dev.mock import MockBackend

from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.llm import Task
from plotweaver.runner import run_book
from plotweaver.store import Project
from plotweaver.vxbook import legacy_pair, validate_vxbook


def _request(tmp: Path, *, dark: bool, chapters: int = 2) -> BookRequest:
    return BookRequest(
        title="Проверка",
        language=Language.RU,
        synopsis="Короткий синопсис. Ещё корабль стоит в пыли, и экипаж спорит до утра.",
        target_words=1600,
        chapter_count=chapters,
        scenes_per_chapter=2,
        dark_themes=dark,
        tier=ModelTier.STANDARD,
        mode=BookMode.AUTOPILOT,
        main_model_id="mock-main",
        least_censored_model_id="mock-low",
    )


def test_mock_export_aligns_marks_and_keeps_yo(tmp_path: Path) -> None:
    project = Project.open_or_create(tmp_path / "book", _request(tmp_path, dark=False, chapters=1))
    result = run_book(project, MockBackend(), yes=True, export_to=tmp_path / "export")
    assert result.status == "completed"
    assert result.swaps == 0
    assert result.export_dir is not None
    vxbook = result.export_dir / "book.vxbook"
    assert not [issue for issue in validate_vxbook(vxbook) if issue.severity == "error"]
    book, marks_text = legacy_pair(vxbook)
    marks = marks_text.splitlines()
    paragraphs = [
        block for block in book.split("\n\n") if block.strip() and not block.startswith("# ")
    ]
    assert len(marks) == len(paragraphs)
    assert any(line.endswith("NARRATOR") for line in marks)
    assert any("MALE:" in line for line in marks)
    assert any("FEMALE:" in line for line in marks)
    assert "ё" in book or "Ё" in book
    assert "\u0301" in book
    with zipfile.ZipFile(vxbook) as archive:
        assert 'src="auto"' in archive.read("book.md").decode("utf-8")
    assert (result.export_dir / "book.epub").is_file()
    assert not (result.export_dir / "book.docx").is_file()
    assert not (result.export_dir / "book.fb2").is_file()
    assert not (result.export_dir / "book.md").is_file()
    assert not (result.export_dir / "audiobook" / "speaker-marks.txt").is_file()


def test_dark_toggle_swaps_once_and_fills(tmp_path: Path) -> None:
    backend = MockBackend()
    project = Project.open_or_create(tmp_path / "dark", _request(tmp_path, dark=True))
    result = run_book(project, backend, yes=True)
    assert result.swaps == 1
    assert result.placeholders >= 1
    assert Task.FILL.value in backend.tasks
    off = MockBackend()
    project_off = Project.open_or_create(tmp_path / "plain", _request(tmp_path, dark=False))
    plain = run_book(project_off, off, yes=True)
    assert plain.swaps == 0
    assert Task.FILL.value not in off.tasks


def test_refusal_becomes_a_placeholder_only_when_dark_is_on(tmp_path: Path) -> None:
    dark = MockBackend(refuse_drafts=1)
    project = Project.open_or_create(
        tmp_path / "refuse-dark", _request(tmp_path, dark=True, chapters=1)
    )
    result = run_book(project, dark, yes=True)
    assert result.swaps == 1
    assert result.refusals >= 1
    assert Task.FILL.value in dark.tasks
    plain_backend = MockBackend(refuse_drafts=1)
    plain = Project.open_or_create(
        tmp_path / "refuse-plain", _request(tmp_path, dark=False, chapters=1)
    )
    kept = run_book(plain, plain_backend, yes=True)
    assert kept.swaps == 0
    assert Task.FILL.value not in plain_backend.tasks
    book = kept.export_dir or Path()
    text = ""
    if kept.export_dir is not None:
        text, _marks = legacy_pair(kept.export_dir / "book.vxbook")
    assert "cannot write" in text.lower() or "I cannot" in text
    del book


def test_resume_skips_a_finished_bible(tmp_path: Path) -> None:
    backend = MockBackend()
    project = Project.open_or_create(
        tmp_path / "resume", _request(tmp_path, dark=False, chapters=1)
    )
    waiting = run_book(project, backend, yes=False)
    assert waiting.status == "waiting"
    assert waiting.gate == "bible"
    done = run_book(project, backend, yes=True)
    assert done.status == "completed"
    assert backend.tasks.count(Task.BIBLE.value) == 1
