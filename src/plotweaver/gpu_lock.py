"""Suite GPU lock: %TEMP%/voxprint-gpu.lock.

The file is JSON ``{owner, pid, job, started, eta}`` with ISO-8601 UTC timestamps.
A lock is stale when its pid is gone or its eta is more than two hours in the past.
The same process may re-enter; the inner block does not release the outer lock.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from plotweaver.appinfo import LOCK_OWNER

LOCK_NAME = "voxprint-gpu.lock"
STALE_AFTER = timedelta(hours=2)


class GpuLockTimeout(TimeoutError):
    """Another Voxprint app still holds the GPU."""


def lock_path() -> Path:
    override = os.environ.get("VOXPRINT_GPU_LOCK")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / LOCK_NAME


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _parse(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _pid_alive(pid: object) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int | str):
        return False
    try:
        number = int(pid)
    except ValueError:
        return False
    if number <= 0:
        return False
    try:
        os.kill(number, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def read_lock(path: Path | None = None) -> dict[str, Any] | None:
    """Lock contents, an empty dict when the file is garbage, or None when there is no file."""
    target = path or lock_path()
    try:
        text = target.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    except OSError:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if isinstance(data, dict):
        return data
    return {}


def is_stale(data: dict[str, Any], now: datetime | None = None) -> bool:
    """Stale when the recorded pid is gone, or eta is more than two hours ago."""
    moment = now or _now()
    pid = data.get("pid")
    if pid is not None and not _pid_alive(pid):
        return True
    eta = _parse(data.get("eta")) or _parse(data.get("started"))
    if eta is None:
        return True
    return moment - eta > STALE_AFTER


def try_acquire(
    job: str,
    eta_s: float,
    path: Path | None = None,
    owner: str = LOCK_OWNER,
) -> dict[str, Any] | None:
    """Create the lock. None means we hold it; otherwise the holder's record is returned."""
    target = path or lock_path()
    current = read_lock(target)
    if current is not None:
        mine = current.get("owner") == owner and current.get("pid") == os.getpid()
        if not mine and not is_stale(current):
            return current
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        except PermissionError:
            return current
    moment = _now()
    payload = {
        "owner": owner,
        "pid": os.getpid(),
        "job": job,
        "started": _iso(moment),
        "eta": _iso(moment + timedelta(seconds=max(60.0, eta_s))),
    }
    tmp = target.with_name(f"{target.name}.{uuid.uuid4().hex[:8]}.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.link(tmp, target)
        tmp.unlink()
    except FileExistsError, PermissionError, OSError:
        tmp.unlink(missing_ok=True)
        return read_lock(target) or {"owner": "?"}
    return None


def release(path: Path | None = None, owner: str = LOCK_OWNER) -> None:
    target = path or lock_path()
    current = read_lock(target)
    if current is None:
        return
    if current.get("owner") == owner and current.get("pid") in (None, os.getpid()):
        try:
            target.unlink()
        except OSError:
            pass


@contextmanager
def gpu_job(
    job: str,
    eta_s: float = 10 * 3600,
    on_wait: Callable[[dict[str, Any], float], None] = lambda _holder, _waited: None,
    timeout: float | None = None,
    poll: float = 5.0,
    path: Path | None = None,
) -> Iterator[None]:
    """Hold the suite GPU lock for one book job. Re-entrant for this process."""
    target = path or lock_path()
    current = read_lock(target)
    if current and current.get("owner") == LOCK_OWNER and current.get("pid") == os.getpid():
        yield
        return
    started = time.monotonic()
    while True:
        holder = try_acquire(job, eta_s, target)
        if holder is None:
            break
        waited = time.monotonic() - started
        if timeout is not None and waited > timeout:
            raise GpuLockTimeout(
                f"the GPU is busy: {holder.get('owner', '?')} / {holder.get('job', '?')}"
            )
        on_wait(holder, waited)
        time.sleep(poll)
    try:
        yield
    finally:
        release(target)
