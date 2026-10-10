"""Version stamp and the bundled llama.cpp tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from plotweaver.appinfo import APP_VERSION
from plotweaver.llama_release import LLAMA_BUILD, bundled_runtime_dir, ensure_llama_server
from plotweaver.paths import _marked_root, repo_root


def test_version_is_shared() -> None:
    root = repo_root()
    project = (root / "pyproject.toml").read_text(encoding="utf-8")
    installer = (root / "packaging" / "windows" / "plotweaver.iss").read_text(encoding="utf-8")
    assert f'version = "{APP_VERSION}"' in project
    assert f'#define MyAppVersion "{APP_VERSION}"' in installer


def test_marked_root_needs_both_markers(tmp_path: Path) -> None:
    assert _marked_root(tmp_path) is None
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    assert _marked_root(tmp_path) is None
    (tmp_path / "bakeoff").mkdir()
    assert _marked_root(tmp_path) == tmp_path


def test_bundled_runtime_is_used_before_a_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "app"
    binary = bundled_runtime_dir(root) / "llama-server"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"")
    (binary.parent / ".complete").write_text(LLAMA_BUILD, encoding="utf-8")
    monkeypatch.delenv("PLOTWEAVER_LLAMA_SERVER", raising=False)
    monkeypatch.setattr("plotweaver.llama_release.repo_root", lambda: root)
    monkeypatch.setattr(
        "plotweaver.llama_release.llama_runtime_dir", lambda: tmp_path / "shared-missing"
    )

    def fail_download(folder: Path) -> Path:
        raise AssertionError(f"download attempted: {folder}")

    monkeypatch.setattr("plotweaver.llama_release._ensure_in", fail_download)
    assert ensure_llama_server() == binary
