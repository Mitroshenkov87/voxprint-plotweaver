"""ensure_ready is the only provisioning result the window needs."""

from __future__ import annotations

import pytest

from plotweaver.errors import PlotweaverError
from plotweaver.ready import Failed, Ready, ensure_ready


def test_ensure_ready_reports_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    def repair(progress: object) -> list[str]:
        assert callable(progress)
        progress("Downloading t-pro (4.0 GB at 10 MB/s). About 1 minute left.")
        return ["t-pro"]

    monkeypatch.setattr("plotweaver.suite.repair_shared", repair)
    notes: list[str] = []
    assert isinstance(ensure_ready(notes.append), Ready)
    assert notes == ["Downloading t-pro (4.0 GB at 10 MB/s). About 1 minute left."]


def test_ensure_ready_returns_a_sentence(monkeypatch: pytest.MonkeyPatch) -> None:
    def repair(_progress: object) -> list[str]:
        raise PlotweaverError("Not enough disk space on C:. Need 8.0 GB, 1.0 GB free.")

    monkeypatch.setattr("plotweaver.suite.repair_shared", repair)
    result = ensure_ready(lambda _message: None)
    assert isinstance(result, Failed)
    assert result.message.startswith("Not enough disk space")
