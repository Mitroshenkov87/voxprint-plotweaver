"""Machine-readable CLI: version label, --json, and --dry-run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plotweaver.appinfo import stamp_build, version_label
from plotweaver.cli import main
from plotweaver.domain import BookRequest, Language
from plotweaver.export import export_output_names
from plotweaver.paths import repo_root
from plotweaver.store import Project
from plotweaver.vxbook import BlockKind, VxBlock, VxChapter, VxSpeaker, write_vxbook


def test_version_flag_is_the_display_label(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--version"])
    assert caught.value.code == 0
    assert capsys.readouterr().out.strip() == version_label()
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == '0.2.0 RC · build dev "Sefer"'


def test_stamp_replaces_the_dev_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = repo_root() / "BUILD.json"
    stamped = tmp_path / "BUILD.json"
    stamped.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    assert stamp_build(stamped, 52) == 52
    monkeypatch.setenv("PLOTWEAVER_BUILD_JSON", str(stamped))
    assert version_label() == '0.2.0 RC · build 52 "Sefer"'
    final = json.loads(stamped.read_text(encoding="utf-8"))
    final["prerelease"] = None
    final["build"] = 9
    stamped.write_text(json.dumps(final), encoding="utf-8")
    assert version_label() == '0.2.0 · build 9 "Sefer"'


def test_run_dry_run_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    synopsis = tmp_path / "synopsis.md"
    synopsis.write_text("A short synopsis about a river.", encoding="utf-8")
    project = tmp_path / "book"
    assert (
        main(
            [
                "run",
                "--project",
                str(project),
                "--synopsis",
                str(synopsis),
                "--mock",
                "--dry-run",
                "--json",
                "--fb2",
                "--sound",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["command"] == "run"
    assert payload["dry_run"] is True
    assert payload["code"] == 0
    assert "book.vxbook" in payload["outputs"][0]
    assert any(item.endswith("book.fb2") for item in payload["outputs"])
    assert any(item.endswith("book.sound.vxbook") for item in payload["outputs"])
    assert not project.exists()


def test_run_dry_run_requires_a_synopsis(tmp_path: Path) -> None:
    assert main(["run", "--project", str(tmp_path / "missing"), "--dry-run", "--json"]) == 1


def test_export_dry_run_needs_an_outline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "book"
    Project.open_or_create(
        root, BookRequest(title="River", language=Language.EN, synopsis="A river.")
    )
    assert main(["export", "--project", str(root), "--dry-run", "--json"]) == 1
    capsys.readouterr()
    (root / "artefacts").mkdir()
    (root / "artefacts" / "outline.json").write_text(
        json.dumps({"chapters": [{"id": "ch01", "title": "One"}]}),
        encoding="utf-8",
    )
    before = (root / "project.json").read_bytes()
    assert main(["export", "--project", str(root), "--dry-run", "--json", "--docx"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "export"
    assert payload["title"] == "River"
    assert any(item.endswith("book.vxbook") for item in payload["outputs"])
    assert any(item.endswith("book.docx") for item in payload["outputs"])
    assert (root / "project.json").read_bytes() == before
    assert not (root / "export").exists()


def test_models_list_json() -> None:
    assert main(["models", "list", "--dry-run", "--json"]) == 0


def test_models_list_json_shape(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["models", "list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "models.list"
    assert payload["code"] == 0
    ids = {row["id"] for row in payload["models"]}
    assert "t-pro-it-2.1-q4" in ids
    row = next(item for item in payload["models"] if item["id"] == "t-pro-it-2.1-q4")
    assert set(row) == {
        "id",
        "enabled",
        "tier",
        "role",
        "filename",
        "repo",
        "revision",
        "sha256",
        "size",
        "license",
        "min_vram_gb",
        "uncensored",
        "optional",
        "default",
        "languages",
    }


def test_import_dry_run_does_not_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    registry = tmp_path / "models.toml"
    registry.write_text(
        (repo_root() / "bakeoff" / "models.toml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    before = registry.read_bytes()
    manifest = tmp_path / "forge.json"
    manifest.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "id": "t-lite-it-2.1-forge-abliterated-q4",
                        "revision": "rev-1",
                        "sha256": "ab" * 32,
                        "size": 120,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "models",
                "import-forge-manifest",
                str(manifest),
                "--registry",
                str(registry),
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["writes"] is False
    assert payload["models"] == ["t-lite-it-2.1-forge-abliterated-q4"]
    assert registry.read_bytes() == before


def test_vxbook_validate_json_and_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    book = tmp_path / "book.vxbook"
    write_vxbook(
        book,
        title="Пыль",
        author="Илья Воронов",
        language="ru",
        created="2026-10-10T08:00:00Z",
        synopsis="Короткий синопсис.",
        chapters=[
            VxChapter(
                "ch01",
                "Глава",
                [VxBlock(BlockKind.PARAGRAPH, text="Еще не все сказано.")],
            )
        ],
        speakers=[VxSpeaker("narrator", "narrator")],
    )
    empty = tmp_path / "empty.vxbook"
    empty.write_bytes(b"")
    assert main(["vxbook", "validate", str(empty), "--dry-run", "--json"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["dry_run"] is True
    assert plan["actions"]
    assert main(["vxbook", "validate", str(book), "--json"]) == 0
    checked = json.loads(capsys.readouterr().out)
    assert checked["ok"] is True
    assert checked["issues"] == []


def test_sound_dry_run_does_not_write(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    book = tmp_path / "book.vxbook"
    write_vxbook(
        book,
        title="Пыль",
        author="Илья Воронов",
        language="ru",
        created="2026-10-10T08:00:00Z",
        synopsis="Короткий синопсис.",
        chapters=[
            VxChapter(
                "ch01",
                "Глава",
                [VxBlock(BlockKind.PARAGRAPH, text="Еще не все сказано.")],
            )
        ],
        speakers=[VxSpeaker("narrator", "narrator")],
    )
    output = tmp_path / "book.sound.vxbook"
    assert main(["sound", "add", str(book), "-o", str(output), "--dry-run", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "sound.add"
    assert payload["outputs"] == [str(output.resolve())]
    assert not output.exists()


def test_export_names_include_vxbook() -> None:
    names = export_output_names(["epub", "markdown"], sound=True)
    assert names[0] == "book.vxbook"
    assert "book.epub" in names
    assert "book.md" in names
    assert "book.sound.vxbook" in names
