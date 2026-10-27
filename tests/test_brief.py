"""Book brief schema, import, compilation, and the draft command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plotweaver.brief import (
    BriefError,
    attach_context,
    chat_prompt,
    compile_brief,
    parse_brief,
    render_markdown,
    writing_guide_path,
)
from plotweaver.cli import main
from plotweaver.domain import BookRequest, Language
from plotweaver.paths import repo_root
from plotweaver.prompts import bible_prompt
from plotweaver.store import Project


def _sample() -> str:
    return """# Book brief

version: 1

## Title

Station

## Language

en

## Length

pages: 4
words_per_page: 200
chapters: 1
scenes_per_chapter: 2

## Genre

science fiction

## Subgenre

expedition

## Tone

dry

## Point of view

third-person limited

## Tense

past

## Audience

adult

## Setting

a research station

## Characters

- name: Ilya
  role: commander
  description: Short orders.
  gender: male

## Plot points

- The seal fails.

## Ending

bittersweet

## Style references

- a field log

## Dark themes

no

## Synopsis

The seal fails. The crew stays.

## Guessed

- tone
"""


def test_markdown_and_json_round_trip() -> None:
    brief = parse_brief(_sample())
    assert brief.title == "Station"
    assert brief.target_words == 800
    assert brief.chapter_count == 1
    assert brief.characters[0].gender == "male"
    assert brief.guessed == ["tone"]
    again = parse_brief(render_markdown(brief))
    assert again.to_dict() == brief.to_dict()
    parsed = parse_brief(json.dumps(brief.to_dict()))
    assert parsed.pov == "third-person limited"
    assert parsed.tense == "past"


def test_import_names_the_bad_field() -> None:
    with pytest.raises(BriefError) as missing:
        parse_brief(json.dumps({"version": 1, "language": "en"}))
    assert any(item.field == "title" and item.code == "required" for item in missing.value.errors)
    with pytest.raises(BriefError) as gender:
        payload = parse_brief(_sample()).to_dict()
        characters = payload["characters"]
        assert isinstance(characters, list)
        characters[0]["gender"] = "other"
        parse_brief(json.dumps(payload))
    assert gender.value.errors[0].code == "gender"
    with pytest.raises(BriefError) as target:
        payload = parse_brief(_sample()).to_dict()
        payload["target_words"] = 10
        parse_brief(json.dumps(payload))
    assert target.value.errors[0].code == "target"
    with pytest.raises(BriefError) as broken:
        parse_brief("{")
    assert broken.value.errors[0].code == "json"


def test_compiled_brief_is_binding_until_the_preview_is_edited() -> None:
    brief = parse_brief(_sample())
    text = compile_brief(brief)
    assert "pov: third-person limited" in text
    assert "tense: past" in text
    assert "Do not infer a different point of view" in text
    request = BookRequest(
        title="Station",
        language=Language.EN,
        synopsis=brief.synopsis,
        brief=brief.to_dict(),
    )
    attach_context(request)
    assert "BOOK BRIEF (binding)" in request.generation_context
    prompt = bible_prompt(request)
    assert "BOOK BRIEF (binding)" in prompt
    assert "The BOOK BRIEF block is binding" in prompt
    request.prompt_override = "Use the edited preview."
    attach_context(request)
    assert request.generation_context == "Use the edited preview."
    assert "Use the edited preview." in bible_prompt(request)


def test_chat_prompt_and_guide_are_shipped() -> None:
    prompt = chat_prompt("ru")
    assert "## Point of view" in prompt
    assert "## Tense" in prompt
    assert "ru" in prompt
    guide = writing_guide_path()
    assert guide.is_file()
    packaged = Path(__file__).parents[1] / "src" / "plotweaver" / "data" / "writing-a-brief.md"
    docs = repo_root() / "docs" / "WRITING-A-BRIEF.md"
    assert packaged.read_text(encoding="utf-8") == docs.read_text(encoding="utf-8")
    readme = (repo_root() / "docs" / "README-full.md").read_text(encoding="utf-8")
    assert "docs/WRITING-A-BRIEF.md" in readme
    nav = (repo_root() / "mkdocs.yml").read_text(encoding="utf-8")
    assert "WRITING-A-BRIEF.md" in nav


def test_brief_draft_json_and_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "brief",
                "draft",
                "--idea",
                "The seal fails.\nThe crew stays.",
                "--mock",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "brief.draft"
    assert payload["brief"]["pov"] == "third-person limited"
    assert "tone" in payload["brief"]["guessed"]
    assert payload["brief"]["target_words"] == 40 * 250
    assert main(["brief", "draft", "--idea", "notes", "--dry-run", "--json", "--mock"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert plan["command"] == "brief.draft"


def test_run_brief_rejects_bad_json_and_writes_a_short_book(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "bad.json"
    broken.write_text("{", encoding="utf-8")
    project = tmp_path / "book"
    assert (
        main(
            [
                "run",
                "--project",
                str(project),
                "--brief",
                str(broken),
                "--json",
                "--mock",
                "--dry-run",
            ]
        )
        == 1
    )
    failure = json.loads(capsys.readouterr().out)
    assert failure["errors"][0]["field"] == "brief"
    assert failure["errors"][0]["code"] == "json"
    assert not project.exists()
    path = tmp_path / "brief.md"
    path.write_text(_sample(), encoding="utf-8")
    assert (
        main(
            [
                "run",
                "--project",
                str(project),
                "--brief",
                str(path),
                "--mock",
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    done = json.loads(capsys.readouterr().out)
    assert done["status"] == "completed"
    stored = Project(project).request()
    assert stored.title == "Station"
    assert stored.target_words == 800
    assert stored.chapter_count == 1
    assert stored.pov == "third-person limited"
    assert stored.tense == "past"
    assert stored.brief is not None
    assert stored.brief["genre"] == "science fiction"
