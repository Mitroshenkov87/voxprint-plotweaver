"""Mars scenario and a one-synopsis bake-off, both on the mock backend."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from plotweaver.paths import repo_root
from plotweaver.scenarios import MARS_CHAPTERS, MARS_TITLE, mars_request
from plotweaver.vxbook import legacy_pair, validate_vxbook

_FORBIDDEN = (
    "Musk",
    "Маск",
    "Илон",
    "Shotwell",
    "Bezos",
    "Gwynne",
)


def test_mars_request_is_the_short_story() -> None:
    request = mars_request()
    assert request.title == MARS_TITLE
    assert request.chapter_count == MARS_CHAPTERS
    assert request.dark_themes is False
    assert "SpaceX" in request.synopsis
    outline = (repo_root() / "scenarios" / "mars-e2e" / "outline.md").read_text(encoding="utf-8")
    for name in _FORBIDDEN:
        assert name not in request.synopsis
        assert name not in outline


def test_mars_mock_cli_exports_audiobook(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PLOTWEAVER_NO_UPDATE_CHECK"] = "1"
    env["VOXPRINT_GPU_LOCK"] = str(tmp_path / "lock.json")
    env["QT_QPA_PLATFORM"] = "offscreen"
    export = tmp_path / "mars"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "plotweaver",
            "scenario-mars",
            "--mock",
            "--yes",
            "--project",
            str(export / "project"),
            "--export-dir",
            str(export),
        ],
        cwd=repo_root(),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "book.vxbook" in proc.stdout
    vxbook = export / "book.vxbook"
    assert not [issue for issue in validate_vxbook(vxbook) if issue.severity == "error"]
    book, marks_text = legacy_pair(vxbook)
    marks = marks_text.splitlines()
    paragraphs = [
        block for block in book.split("\n\n") if block.strip() and not block.startswith("# ")
    ]
    assert book.count("\n# ") + (1 if book.startswith("# ") else 0) == MARS_CHAPTERS
    assert len(marks) == len(paragraphs)
    assert "ё" in book or "Ё" in book
    assert "\u0301" in book
    assert not (export / "audiobook" / "speaker-marks.txt").is_file()
    stored = (export / "project" / "project.json").read_text(encoding="utf-8")
    assert "SpaceX" in stored
    for name in _FORBIDDEN:
        assert name not in stored
        assert name not in book


def test_mars_script_writes_sound_markup(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PLOTWEAVER_NO_UPDATE_CHECK"] = "1"
    env["PLOTWEAVER_MOCK"] = "1"
    env["PLOTWEAVER_MARS_OUT"] = str(tmp_path / "mars")
    env["VOXPRINT_GPU_LOCK"] = str(tmp_path / "lock.json")
    proc = subprocess.run(
        ["bash", "scripts/e2e_mars.sh", "--mock"],
        cwd=repo_root(),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    sound = tmp_path / "mars" / "book.sound.vxbook"
    assert sound.is_file()
    assert (tmp_path / "mars" / "book.vxbook").is_file()
    assert not [issue for issue in validate_vxbook(sound) if issue.severity == "error"]


def test_bakeoff_mock_limit_one(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["PLOTWEAVER_NO_UPDATE_CHECK"] = "1"
    env["VOXPRINT_GPU_LOCK"] = str(tmp_path / "lock.json")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "plotweaver",
            "bakeoff",
            "--mock",
            "--limit",
            "1",
            "--results",
            str(tmp_path / "bakeoff"),
        ],
        cwd=repo_root(),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    results = tmp_path / "bakeoff"
    assert (results / "bakeoff-results.tar.gz").is_file()
    assert (results / "judge" / "scores.json").is_file()
    assert (results / "blind-packet" / "reader" / "README.md").is_file()
    assert (results / "assignment-key.json").is_file()
    solos = list((results / "solo").glob("*/*/metrics.json"))
    assert len(solos) == 2
    two_pass = list((results / "two-pass").glob("*/*/metrics.json"))
    assert len(two_pass) == 1
