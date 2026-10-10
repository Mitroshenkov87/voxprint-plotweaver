"""Suite GPU lock: stale pid, stale eta, and re-entry."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from plotweaver.gpu_lock import gpu_job, is_stale, lock_path, read_lock


def test_reentrant_lock_is_held_until_the_outer_block() -> None:
    with gpu_job("outer", eta_s=120):
        outer = read_lock()
        assert outer is not None
        assert outer["owner"] == "plotweaver"
        assert outer["job"] == "outer"
        with gpu_job("inner", eta_s=120):
            assert read_lock()["job"] == "outer"
        assert read_lock() is not None
    assert read_lock() is None


def test_dead_pid_and_old_eta_are_stale(tmp_path) -> None:
    path = lock_path()
    past = datetime.now(UTC) - timedelta(hours=5)
    path.write_text(
        json.dumps(
            {
                "owner": "plotweaver",
                "pid": 2**30,
                "job": "gone",
                "started": past.isoformat(timespec="seconds"),
                "eta": (past + timedelta(hours=1)).isoformat(timespec="seconds"),
            }
        ),
        encoding="utf-8",
    )
    assert is_stale(read_lock() or {})
    with gpu_job("fresh", eta_s=120):
        assert read_lock()["pid"] == os.getpid()
    alive = datetime.now(UTC)
    path.write_text(
        json.dumps(
            {
                "owner": "other",
                "pid": os.getpid(),
                "job": "held",
                "started": (alive - timedelta(hours=4)).isoformat(timespec="seconds"),
                "eta": (alive - timedelta(hours=3)).isoformat(timespec="seconds"),
            }
        ),
        encoding="utf-8",
    )
    assert is_stale(read_lock() or {})
    del tmp_path
