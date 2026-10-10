"""Sound extension v1: the spec sample, mock markup, and the validator."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from plotweaver.appinfo import APP_VERSION
from plotweaver.cli import main
from plotweaver.domain import BookMode, BookRequest, Language
from plotweaver.llm import MockBackend
from plotweaver.runner import run_book
from plotweaver.sound import add_sound
from plotweaver.store import Project
from plotweaver.vxbook import (
    BlockKind,
    VxBlock,
    VxChapter,
    pack_vxbook,
    validate_vxbook,
    write_vxbook,
)

_SAMPLE_SHA = "2365261917099d28252a7775609617472d6ad1b4eb50c189e98d1f230b1ff1f6"
_FINGERPRINTS = (
    "791635f0f627",
    "82b5671d2862",
    "bcd4b2c89e66",
    "746e4aee43ff",
    "062d3efcc474",
    "e31b535c10d9",
)


def _sample() -> Path:
    return Path(__file__).parent / "fixtures" / "sound-sample.vxbook"


def _errors(path: Path) -> list[str]:
    return [issue.message for issue in validate_vxbook(path) if issue.severity == "error"]


def test_sound_sample_is_the_spec_archive() -> None:
    data = _sample().read_bytes()
    assert hashlib.sha256(data).hexdigest() == _SAMPLE_SHA
    assert data[:4] == b"PK\x03\x04"
    issues = validate_vxbook(_sample())
    assert _errors(_sample()) == []
    assert not [issue for issue in issues if issue.severity == "warning"]
    with zipfile.ZipFile(_sample()) as archive:
        assert archive.namelist() == [
            "mimetype",
            "manifest.json",
            "book.md",
            "speakers.json",
            "cast.json",
            "sound.json",
            "sound-cast.json",
            "notes/author.md",
        ]
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format_version"] == "1.1"
        assert manifest["extensions"] == ["sound/1"]
        sound = json.loads(archive.read("sound.json"))
        assert sound["extension"] == "sound/1"
        fingerprints = [cue["para_fp"] for cue in sound["cues"]]
        assert fingerprints[0] == _FINGERPRINTS[0]
        assert main(["vxbook", "validate", str(_sample())]) == 0


def test_mock_sound_add_is_reproducible(tmp_path: Path) -> None:
    source = tmp_path / "book.vxbook"
    write_vxbook(
        source,
        title="Пыль",
        author="Илья Воронов",
        language="ru",
        created="2026-10-10T08:00:00Z",
        synopsis="Короткий синопсис.",
        chapters=[
            VxChapter(
                "ch01",
                "Глава",
                [
                    VxBlock(BlockKind.PARAGRAPH, "Ещё туман стоял над шлюзом."),
                    VxBlock(BlockKind.PARAGRAPH, "Илья\u0301 молчал."),
                    VxBlock(BlockKind.SCENE),
                    VxBlock(BlockKind.PARAGRAPH, "Утром пыль легла обратно."),
                ],
            )
        ],
        speakers=[],
    )
    original = source.read_bytes()
    first = tmp_path / "a.vxbook"
    second = tmp_path / "b.vxbook"
    assert add_sound(source, first, MockBackend()) == []
    assert add_sound(source, second, MockBackend()) == []
    assert first.read_bytes() == second.read_bytes()
    assert source.read_bytes() == original
    with zipfile.ZipFile(first) as archive, zipfile.ZipFile(source) as untouched:
        assert archive.read("book.md") == untouched.read("book.md")
        manifest = json.loads(archive.read("manifest.json"))
        sound = json.loads(archive.read("sound.json"))
    assert manifest["format_version"] == "1.1"
    assert manifest["extensions"] == ["sound/1"]
    assert manifest["generator"] == {"app": "plotweaver", "version": APP_VERSION}
    assert manifest["source"]["format"] == "vxbook"
    assert manifest["source"]["filename"] == "book.vxbook"
    assert manifest["source"]["sha256"] == hashlib.sha256(original).hexdigest()
    assert sound["extension"] == "sound/1"
    assert all(cue.get("src") == "auto" and "conf" in cue for cue in sound["cues"])
    assert all("asset" not in cue for cue in sound["cues"])
    assert any(cue["kind"] == "bed" and "no vocals" in cue["prompt"] for cue in sound["cues"])
    assert not any(cue["kind"] == "sfx" for cue in sound["cues"])
    assert _errors(first) == []
    assert main(["sound", "add", str(source), "-o", str(tmp_path / "cli.vxbook"), "--mock"]) == 0


def test_rerun_keeps_user_markup_and_cast(tmp_path: Path) -> None:
    source = tmp_path / "book.vxbook"
    write_vxbook(
        source,
        title="Пыль",
        author="Автор",
        language="ru",
        created="2026-10-10T08:00:00Z",
        chapters=[
            VxChapter(
                "ch01",
                "Глава",
                [
                    VxBlock(BlockKind.PARAGRAPH, "Тишина."),
                    VxBlock(BlockKind.PARAGRAPH, "Потом шаг."),
                ],
            )
        ],
        speakers=[],
    )
    marked = tmp_path / "marked.vxbook"
    add_sound(source, marked, MockBackend())
    with zipfile.ZipFile(marked) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        sound = json.loads(archive.read("sound.json"))
        members = [
            (name, archive.read(name))
            for name in archive.namelist()
            if name not in {"mimetype", "manifest.json"}
        ]
    sound["scenes"][0]["src"] = "user"
    sound["scenes"][0]["hint"] = "USER SCENE"
    sound["cues"][0]["src"] = "user"
    sound["cues"][0]["prompt"] = "USER CUE KEEP, no vocals"
    kept_id = sound["cues"][0]["id"]
    cast = {
        "version": "1.0",
        "enabled": True,
        "master_gain_db": 0,
        "cues": {kept_id: {"gain_db": -12}, "missing": {"gain_db": -10}},
    }
    payload = (json.dumps(sound, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    cast_bytes = (json.dumps(cast, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    replaced = [(name, payload if name == "sound.json" else data) for name, data in members]
    replaced.append(("sound-cast.json", cast_bytes))
    packed = tmp_path / "with-user.vxbook"
    pack_vxbook(packed, manifest, replaced)
    before = packed.read_bytes()
    dest = tmp_path / "again.vxbook"
    warnings = add_sound(packed, dest, MockBackend())
    assert packed.read_bytes() == before
    assert any("missing" in message for message in warnings)
    with zipfile.ZipFile(dest) as archive:
        sound_again = json.loads(archive.read("sound.json"))
        cast_again = json.loads(archive.read("sound-cast.json"))
    assert sound_again["scenes"][0]["hint"] == "USER SCENE"
    kept = next(cue for cue in sound_again["cues"] if cue["id"] == kept_id)
    assert kept["prompt"] == "USER CUE KEEP, no vocals"
    assert kept["src"] == "user"
    assert kept_id in cast_again["cues"]
    assert "missing" not in cast_again["cues"]
    assert _errors(dest) == []


def test_validator_rejects_a_broken_soundscape(tmp_path: Path) -> None:
    source = tmp_path / "book.vxbook"
    write_vxbook(
        source,
        title="Пыль",
        author="Автор",
        language="ru",
        created="2026-10-10T08:00:00Z",
        chapters=[VxChapter("ch01", "Глава", [VxBlock(BlockKind.PARAGRAPH, "Одно предложение.")])],
        speakers=[],
    )
    with zipfile.ZipFile(source) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        members = [
            (name, archive.read(name))
            for name in archive.namelist()
            if name not in {"mimetype", "manifest.json"}
        ]
    manifest["format_version"] = "1.1"
    manifest["extensions"] = ["sound/1"]
    speakers = json.loads(next(data for name, data in members if name == "speakers.json"))
    speakers["format_version"] = "1.1"
    sound = {
        "extension": "sound/1",
        "version": "1.0",
        "scenes": [
            {
                "id": "s1",
                "chapter": "ch01",
                "start_paragraph": 1,
                "end_paragraph": 1,
                "mood": "calm",
                "intensity": 0.2,
                "src": "auto",
                "conf": 0.5,
            }
        ],
        "cues": [
            {
                "id": "a",
                "kind": "bed",
                "layer": "music",
                "prompt": "bed one, no vocals",
                "start_paragraph": 1,
                "end_paragraph": 1,
                "src": "auto",
                "conf": 0.4,
            },
            {
                "id": "b",
                "kind": "bed",
                "layer": "music",
                "prompt": "bed two, no vocals",
                "start_paragraph": 1,
                "end_paragraph": 1,
                "src": "auto",
                "conf": 0.4,
            },
        ],
    }
    replaced = []
    for name, data in members:
        if name == "speakers.json":
            data = (json.dumps(speakers, ensure_ascii=False, indent=2) + "\n").encode()
        replaced.append((name, data))
    replaced.append(("sound.json", (json.dumps(sound) + "\n").encode()))
    broken = tmp_path / "broken.vxbook"
    pack_vxbook(broken, manifest, replaced)
    assert any("more than one bed" in message for message in _errors(broken))
    assert main(["vxbook", "validate", str(broken)]) == 1


def test_pipeline_flag_writes_sound_beside_the_book(tmp_path: Path) -> None:
    request = BookRequest(
        title="Проверка",
        language=Language.RU,
        synopsis="Короткий синопсис про пыль и шов.",
        target_words=800,
        chapter_count=1,
        sound_markup=True,
    )
    project = Project.open_or_create(tmp_path / "book", request)
    result = run_book(project, MockBackend(), yes=True, export_to=tmp_path / "export")
    assert result.export_dir is not None
    assert (result.export_dir / "book.vxbook").is_file()
    assert (result.export_dir / "book.sound.vxbook").is_file()
    assert BookMode.AUTOPILOT == request.mode
    assert _errors(result.export_dir / "book.sound.vxbook") == []
