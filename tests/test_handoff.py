"""Audiobook Builder CLI lookup: registry, suite paths, PATH, then the legacy path."""

from __future__ import annotations

from pathlib import Path

import pytest
from voxprint_common.runtime_manifest import Component, Manifest

from plotweaver import handoff


def _manifest(component_id: str, path: Path) -> Manifest:
    component = Component(
        kind="tool",
        version="0",
        path=str(path),
        sha256="ab" * 32,
        installed_at="2026-01-01T00:00:00Z",
        refs=["plotweaver"],
    )
    return Manifest(components={component_id: component})


def _hide_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handoff, "_WIN_DEFAULT", tmp_path / "missing-win")
    monkeypatch.setattr(handoff, "_LINUX_DEFAULT", tmp_path / "missing-linux")
    monkeypatch.setattr(handoff, "_WIN_LEGACY", tmp_path / "missing-legacy")
    monkeypatch.setattr(handoff.shutil, "which", lambda _name: None)


def test_empty_component_id_skips_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail() -> Manifest:
        raise AssertionError("manifest was loaded")

    monkeypatch.setattr(handoff, "ABB_COMPONENT_ID", "")
    monkeypatch.setattr(handoff, "load", fail)
    _hide_defaults(tmp_path, monkeypatch)
    assert handoff.find_audiobook_cli() is None


def test_lookup_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = tmp_path / "registry-cli"
    windows = tmp_path / "win.exe"
    linux = tmp_path / "linux-cli"
    on_path = tmp_path / "on-path"
    legacy = tmp_path / "legacy.exe"
    for path in (registry, windows, linux, on_path, legacy):
        path.write_bytes(b"")
    monkeypatch.setattr(handoff, "_WIN_DEFAULT", windows)
    monkeypatch.setattr(handoff, "_LINUX_DEFAULT", linux)
    monkeypatch.setattr(handoff, "_WIN_LEGACY", legacy)
    monkeypatch.setattr(handoff.shutil, "which", lambda _name: str(on_path))
    monkeypatch.setattr(handoff, "ABB_COMPONENT_ID", "audiobook-builder")
    monkeypatch.setattr(handoff, "load", lambda: _manifest("audiobook-builder", registry))
    assert handoff.find_audiobook_cli() == registry

    monkeypatch.setattr(handoff, "ABB_COMPONENT_ID", "")
    assert handoff.find_audiobook_cli() == windows
    windows.unlink()
    assert handoff.find_audiobook_cli() == linux
    linux.unlink()
    assert handoff.find_audiobook_cli() == on_path
    monkeypatch.setattr(handoff.shutil, "which", lambda _name: None)
    assert handoff.find_audiobook_cli() == legacy


def test_registry_directory_uses_the_cli_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "Audiobook Builder"
    folder.mkdir()
    cli = folder / "voxprint-audiobook-cli.exe"
    cli.write_bytes(b"")
    _hide_defaults(tmp_path, monkeypatch)
    monkeypatch.setattr(handoff, "ABB_COMPONENT_ID", "audiobook-builder")
    monkeypatch.setattr(handoff, "load", lambda: _manifest("audiobook-builder", folder))
    assert handoff.find_audiobook_cli() == cli


def test_case_insensitive_walk_finds_the_cli(tmp_path: Path) -> None:
    folder = tmp_path / "VOXPrint AI Suite" / "Audiobook Builder"
    folder.mkdir(parents=True)
    cli = folder / "voxprint-audiobook-cli.exe"
    cli.write_bytes(b"")
    requested = tmp_path / "voxprint ai suite" / "audiobook builder" / "VOXPRINT-AUDIOBOOK-CLI.EXE"
    assert handoff._case_insensitive(requested) == cli


def test_windows_lookup_uses_the_case_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    found = tmp_path / "folded.exe"
    monkeypatch.setattr(handoff.os, "name", "nt")
    monkeypatch.setattr(handoff, "_case_insensitive", lambda _path: found)
    monkeypatch.setattr(handoff, "ABB_COMPONENT_ID", "")
    monkeypatch.setattr(handoff, "_WIN_DEFAULT", tmp_path / "missing-win.exe")
    monkeypatch.setattr(handoff, "_LINUX_DEFAULT", tmp_path / "missing-linux")
    monkeypatch.setattr(handoff, "_WIN_LEGACY", tmp_path / "missing-legacy.exe")
    monkeypatch.setattr(handoff.shutil, "which", lambda _name: None)
    assert handoff.find_audiobook_cli() == found
