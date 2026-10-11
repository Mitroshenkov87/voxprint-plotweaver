"""ensure_ready opens the window only when MDL reports ready."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from voxprint_common.mdl.status import JobState, Status, save_status

from plotweaver.ready import Failed, Ready, ensure_ready


def test_mdl_ensure_ready_downloads_so_the_gate_does_not_call_it() -> None:
    from voxprint_common.mdl.queue import ensure_ready as mdl_ensure_ready

    params = list(inspect.signature(mdl_ensure_ready).parameters)
    assert params == ["app", "progress_cb"]


def test_missing_status_is_not_ready(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    notes: list[str] = []
    result = ensure_ready(notes.append)
    assert isinstance(result, Failed)
    assert result.message == "models not ready"
    assert notes == ["Checking models."]


def test_ready_status_opens_the_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("VOXPRINT_HOME", str(tmp_path))
    save_status(Status(JobState.READY))
    notes: list[str] = []
    assert isinstance(ensure_ready(notes.append), Ready)
    assert notes == ["Checking models."]
