"""Startup cost: hash stamps, and the offscreen time to the first window."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from plotweaver.manifest import file_sha256
from plotweaver.paths import repo_root
from plotweaver.suite import _cached_sha256, _trusted

FIRST_WINDOW_BUDGET_S = 2.5
_ABCDEF = "bef57ec7f53a6d40beb640a780a639c83bc29ac8a9816f1fc6c5c6dcd93c4721"


def _seconds(text: str, label: str) -> float:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0] == label:
            return float(parts[1])
    raise AssertionError(f"{label} missing from:\n{text}")


def test_cached_sha256_hashes_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    monkeypatch.delenv("PLOTWEAVER_MODELS", raising=False)
    target = tmp_path / "marker"
    target.write_bytes(b"abcdef")
    calls = {"n": 0}

    def counting(path: Path) -> str:
        calls["n"] += 1
        return file_sha256(path)

    monkeypatch.setattr("plotweaver.suite.file_sha256", counting)
    assert _cached_sha256(target) == _ABCDEF
    assert _cached_sha256(target) == _ABCDEF
    assert calls["n"] == 1
    target.write_bytes(b"abcdef!")
    assert _cached_sha256(target) != _ABCDEF
    assert calls["n"] == 2


def test_trusted_skips_the_hash_when_the_stamp_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    monkeypatch.delenv("PLOTWEAVER_MODELS", raising=False)
    target = tmp_path / "models" / "llm" / "model.gguf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"abcdef")
    assert _trusted(target, size=6, sha256=_ABCDEF) is True

    def fail(path: Path, *, size: int, sha256: str) -> None:
        del path, size, sha256
        raise AssertionError("hashed again")

    monkeypatch.setattr("plotweaver.suite.verify_file", fail)
    assert _trusted(target, size=6, sha256=_ABCDEF) is True


def test_offscreen_first_window_meets_budget(tmp_path: Path) -> None:
    """Fail when the splash is later than 2.5 s on this runner."""
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONUTF8"] = "1"
    env["PLOTWEAVER_NO_UPDATE_CHECK"] = "1"
    env["PLOTWEAVER_SKIP_WEIGHTS"] = "1"
    env["PLOTWEAVER_FAKE_GPU"] = "none"
    env["PLOTWEAVER_FAKE_DRIVER"] = "none"
    env["PLOTWEAVER_STARTUP_PROBE"] = "1"
    env["VOXPRINT_HOME"] = str(tmp_path / "home")
    env["PLOTWEAVER_STATE"] = str(tmp_path / "state")
    proc = subprocess.run(
        [sys.executable, "-m", "plotweaver", "gui", "--mock"],
        cwd=repo_root(),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    first = _seconds(proc.stdout, "first_window")
    main = _seconds(proc.stdout, "main_window")
    print(f"first_window {first:.3f}")
    print(f"main_window {main:.3f}")
    assert first <= FIRST_WINDOW_BUDGET_S
