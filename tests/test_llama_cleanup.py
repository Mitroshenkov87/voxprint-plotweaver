"""A stale Plotweaver llama-server recorded in the state pidfile is stopped."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from plotweaver.llama_server import LlamaServer


def test_stale_pidfile_stops_only_llama_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    (tmp_path / "llama-server.pid").write_text("4242\n", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr("plotweaver.llama_server._is_llama_server", lambda pid: pid == 4242)
    monkeypatch.setattr("plotweaver.llama_server._kill_pid_tree", killed.append)
    LlamaServer(tmp_path / "llama-server")
    assert killed == [4242]
    assert not (tmp_path / "llama-server.pid").exists()


def test_pidfile_for_another_program_is_not_killed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PLOTWEAVER_STATE", str(tmp_path))
    (tmp_path / "llama-server.pid").write_text(f"{os.getpid()}\n", encoding="utf-8")
    killed: list[int] = []
    monkeypatch.setattr("plotweaver.llama_server._kill_pid_tree", killed.append)
    LlamaServer(tmp_path / "llama-server")
    assert killed == []
    assert not (tmp_path / "llama-server.pid").exists()
