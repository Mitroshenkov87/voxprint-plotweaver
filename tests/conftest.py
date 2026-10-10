"""Isolate the suite lock and skip the network update check."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_runtime(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOXPRINT_GPU_LOCK", str(tmp_path / "voxprint-gpu.lock"))
    monkeypatch.setenv("PLOTWEAVER_NO_UPDATE_CHECK", "1")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PLOTWEAVER_FAKE_GPU", "none")
