"""Suite GPU lock from voxprint-common.

The file is ``%TEMP%/voxprint-gpu.lock`` (or ``VOXPRINT_GPU_LOCK``). New records
use ``app`` and ``stage``. Readers still see ``owner`` and ``job``, which is
what older Plotweaver locks wrote. The same process may re-enter; only the
outer block releases the file.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from voxprint_common.gpu_lock import gpu_job as common_gpu_job
from voxprint_common.gpu_lock import is_stale as is_stale
from voxprint_common.gpu_lock import lock_path as lock_path

from plotweaver.appinfo import LOCK_OWNER
from plotweaver.textio import read_text

__all__ = ["LOCK_OWNER", "gpu_job", "is_stale", "lock_path", "read_lock"]


def read_lock(path: Path | None = None) -> dict[str, Any] | None:
    """Lock contents, an empty dict when the file is garbage, or None when there is no file.

    ``app`` and ``stage`` are also returned as ``owner`` and ``job``.
    """
    target = path or lock_path()
    try:
        text = read_text(target)
    except FileNotFoundError:
        return None
    except OSError:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    copied = dict(data)
    if "owner" not in copied and "app" in copied:
        copied["owner"] = copied.get("app")
    if "job" not in copied and "stage" in copied:
        copied["job"] = copied.get("stage")
    if "app" not in copied and "owner" in copied:
        copied["app"] = copied.get("owner")
    if "stage" not in copied and "job" in copied:
        copied["stage"] = copied.get("job")
    return copied


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

    def adapt(holder: Any, waited: float) -> None:
        on_wait(
            {
                "app": holder.app,
                "stage": holder.stage,
                "owner": holder.app,
                "job": holder.stage,
                "pid": holder.pid,
                "started": holder.started,
                "eta": holder.eta,
            },
            waited,
        )

    with common_gpu_job(
        LOCK_OWNER,
        job,
        eta=eta_s,
        timeout=timeout,
        poll=poll,
        path=path,
        on_wait=adapt,
    ):
        yield
