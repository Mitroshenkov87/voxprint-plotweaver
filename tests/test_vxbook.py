"""Voxprint Book writer, the spec example, and the validation checklist."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from PIL import features
from plotweaver_dev.mock import MockBackend

from plotweaver.appinfo import APP_VERSION
from plotweaver.cli import main
from plotweaver.sound import add_sound
from plotweaver.vxbook import (
    BlockKind,
    VxBlock,
    VxChapter,
    VxPart,
    VxSpeaker,
    emitted_chapter_id,
    legacy_pair,
    pack_vxbook,
    validate_vxbook,
    write_vxbook,
)

_EMITTED = re.compile(r"^[a-z][a-z0-9_]{0,63}$")

_MARKS = [
    "1. NARRATOR",
    "2. FEMALE: Анна",
    "3. MALE: Пётр",
    "4. FEMALE: Анна",
    "5. NARRATOR",
    "6. NARRATOR",
]


def _fixture() -> Path:
    return Path(__file__).parent / "fixtures" / "vxbook"


def _errors(path: Path) -> list[str]:
    return [issue.message for issue in validate_vxbook(path) if issue.severity == "error"]


def _members(root: Path) -> list[tuple[str, bytes]]:
    names = ["book.md", "speakers.json", "cast.json", "notes/author.md"]
    return [(name, (root / name).read_bytes()) for name in names]


def test_digit_chapter_ids_are_emitted_as_ch01(tmp_path: Path) -> None:
    assert emitted_chapter_id("1", 1, 2) == "ch01"
    assert emitted_chapter_id("2", 2, 2) == "ch02"
    assert emitted_chapter_id("100", 100, 100) == "ch100"
    chapters = [
        VxChapter("1", "One", [VxBlock(BlockKind.PARAGRAPH, text="The first room stayed quiet.")]),
        VxChapter("2", "Two", [VxBlock(BlockKind.PARAGRAPH, text="The second room stayed quiet.")]),
    ]
    path = tmp_path / "book.vxbook"
    write_vxbook(
        path,
        title="Rooms",
        author="A",
        language="en",
        chapters=chapters,
        speakers=[VxSpeaker("narrator", "narrator")],
        created="2026-10-11T00:00:00Z",
    )
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        book = archive.read("book.md").decode("utf-8")
    ids = [row["id"] for row in manifest["chapters"]]
    anchors = [row["anchor"] for row in manifest["chapters"]]
    assert ids == ["ch01", "ch02"]
    assert anchors == ids
    assert all(_EMITTED.fullmatch(item) for item in [*ids, *anchors])
    assert 'id="ch01"' in book and 'id="ch02"' in book
    sounded = tmp_path / "book.sound.vxbook"
    add_sound(path, sounded, MockBackend())
    with zipfile.ZipFile(sounded) as archive:
        document = json.loads(archive.read("sound.json"))
    for scene in document["scenes"]:
        assert scene["chapter"] in {"ch01", "ch02"}
        assert _EMITTED.fullmatch(scene["chapter"])
        assert _EMITTED.fullmatch(scene["id"])


def test_spec_example_round_trip(tmp_path: Path) -> None:
    root = _fixture()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    first = tmp_path / "example.vxbook"
    second = tmp_path / "again.vxbook"
    pack_vxbook(first, manifest, _members(root))
    pack_vxbook(second, manifest, _members(root))
    assert first.read_bytes() == second.read_bytes()
    raw = first.read_bytes()
    assert raw[30:38] == b"mimetype"
    assert raw[38:71] == b"application/vnd.voxprint.book+zip"
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == [
            "mimetype",
            "manifest.json",
            "book.md",
            "speakers.json",
            "cast.json",
            "notes/author.md",
        ]
        assert archive.read("manifest.json") == (root / "manifest.json").read_bytes()
        assert archive.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        assert archive.getinfo("mimetype").extra == b""
    issues = validate_vxbook(first)
    assert _errors(first) == []
    assert not [issue for issue in issues if issue.severity == "warning"]
    plain, marks = legacy_pair(first)
    assert marks.splitlines() == _MARKS
    assert "<!--" not in plain
    assert "<span" not in plain
    assert "Я не боюсь" in plain
    assert "\u0301" in plain
    assert plain.startswith("# Глава 1")
    assert "* * *" in plain
    assert main(["vxbook", "validate", str(first)]) == 0


def test_writer_is_reproducible_and_marks_inferred_speech(tmp_path: Path) -> None:
    chapters = [
        VxChapter(
            "ch01",
            "Пыль",
            [
                VxBlock(BlockKind.PARAGRAPH, text="Еще не все сказано, и Илья\u0301 молчит."),
                VxBlock(
                    BlockKind.PARAGRAPH,
                    text="1. Мы остаёмся.",
                    speaker_id="ilya-voronov",
                    src="auto",
                ),
                VxBlock(
                    BlockKind.PARAGRAPH,
                    parts=(
                        VxPart("— Я не боюсь,", "anna", "auto"),
                        VxPart(" — сказала она.", None),
                    ),
                ),
            ],
        )
    ]
    speakers = [
        VxSpeaker("narrator", "narrator"),
        VxSpeaker("ilya-voronov", "character", name="Илья Воронов", gender="male"),
        VxSpeaker("anna", "character", name="Анна", gender="female", age_group="adult"),
    ]
    created = "2026-10-10T08:00:00Z"
    first = tmp_path / "a.vxbook"
    second = tmp_path / "b.vxbook"
    kwargs = {
        "title": "Пыль",
        "author": "Илья Воронов",
        "language": "ru",
        "chapters": chapters,
        "speakers": speakers,
        "created": created,
        "synopsis": "Короткий синопсис.",
    }
    write_vxbook(first, **kwargs)
    write_vxbook(second, **kwargs)
    assert first.read_bytes() == second.read_bytes()
    assert _errors(first) == []
    with zipfile.ZipFile(first) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        book = archive.read("book.md").decode("utf-8")
        names = archive.namelist()
    assert manifest["generator"] == {"app": "plotweaver", "version": APP_VERSION}
    assert manifest["created_by"]["app"] == "plotweaver"
    assert manifest["source"] == {"format": "plotweaver"}
    assert manifest["created"] == created
    assert 'src="auto"' in book
    assert "ещё" in book.casefold() or "ё" in book
    assert "\u0301" in book
    assert r"1\. " in book
    assert '<span data-vx-speaker="anna" data-vx-src="auto">' in book
    assert "notes/synopsis.md" in names
    if features.check("avif"):
        assert "cover.avif" in names
    plain, marks = legacy_pair(first)
    assert "1. NARRATOR" in marks
    assert "MALE: Илья Воронов" in marks
    assert "FEMALE: Анна" in marks
    assert "\u0301" in plain


def test_validator_rejects_a_bad_archive(tmp_path: Path) -> None:
    broken = tmp_path / "broken.vxbook"
    with zipfile.ZipFile(broken, "w") as archive:
        archive.writestr("mimetype", b"not-a-vxbook")
        archive.writestr("manifest.json", b"{}")
    assert any("mimetype" in message for message in _errors(broken))
    assert main(["vxbook", "validate", str(broken)]) == 1

    root = _fixture()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    speakers = json.loads((root / "speakers.json").read_text(encoding="utf-8"))
    speakers["speakers"][1]["gender"] = "other"
    bad_gender = tmp_path / "gender.vxbook"
    members = _members(root)
    members[1] = (
        "speakers.json",
        (json.dumps(speakers, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    pack_vxbook(bad_gender, manifest, members)
    assert any("gender" in message for message in _errors(bad_gender))

    speakers = json.loads((root / "speakers.json").read_text(encoding="utf-8"))
    speakers["speakers"] = [row for row in speakers["speakers"] if row["id"] != "narrator"]
    missing = tmp_path / "narrator.vxbook"
    members = _members(root)
    members[1] = (
        "speakers.json",
        (json.dumps(speakers, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    pack_vxbook(missing, manifest, members)
    assert any("narrator" in message for message in _errors(missing))

    newer = dict(manifest)
    newer["format_version"] = "2.0"
    future = tmp_path / "future.vxbook"
    pack_vxbook(future, newer, _members(root))
    assert any("newer Plotweaver" in message for message in _errors(future))

    shifted = dict(manifest)
    chapters = json.loads(json.dumps(manifest["chapters"]))
    chapters[1]["offset"] = 1
    shifted["chapters"] = chapters
    warned = tmp_path / "offset.vxbook"
    pack_vxbook(warned, shifted, _members(root))
    issues = validate_vxbook(warned)
    assert not [issue for issue in issues if issue.severity == "error"]
    assert any(issue.severity == "warning" and "offset" in issue.message for issue in issues)
    assert main(["vxbook", "validate", str(warned)]) == 0
