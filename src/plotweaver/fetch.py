"""HTTP download that reports size and a plain-language time estimate."""

from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

import httpx

from plotweaver.errors import PlotweaverError
from plotweaver.ui.i18n import tr

_MIB = 1024 * 1024
_GIB = 1024 * 1024 * 1024


def format_size(nbytes: int) -> str:
    """Render a byte count as GB or MB."""
    if nbytes >= _GIB:
        return f"{nbytes / _GIB:.1f} GB"
    if nbytes >= _MIB:
        return f"{nbytes / _MIB:.0f} MB"
    return f"{nbytes} B"


def format_eta(seconds: float) -> str:
    """Render a remaining time as minutes or seconds."""
    if seconds >= 90:
        return tr("eta_min").format(count=max(1, round(seconds / 60)))
    return tr("eta_sec").format(count=max(1, round(seconds)))


def estimate_minutes(nbytes: int) -> int:
    """Rough minutes at 20 MB/s, at least one."""
    seconds = nbytes / (20 * _MIB)
    return max(1, round(seconds / 60))


def stream_download(
    url: str,
    dest: Path,
    *,
    total: int | None,
    on_progress: Callable[[str], None] | None,
    label: str,
) -> None:
    """Download ``url`` to ``dest``. Resume a non-empty ``.partial`` and drop an empty one."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if total is not None and total > 0:
        require_disk_space(dest, total)
    partial = dest.with_suffix(dest.suffix + ".partial")
    resume = _resume_from(partial, total)
    if resume and total is not None and resume >= total:
        partial.replace(dest)
        return
    headers = {"User-Agent": "plotweaver"}
    if resume:
        headers["Range"] = f"bytes={resume}-"
    started = time.monotonic()
    got = resume
    last_note = 0.0
    try:
        with httpx.stream(
            "GET",
            url,
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(3600.0, connect=30.0),
        ) as response:
            if resume and response.status_code != 206:
                resume = 0
                got = 0
                partial.unlink(missing_ok=True)
            response.raise_for_status()
            announced = total if total is not None else _content_length(response)
            if announced and resume == 0:
                require_disk_space(dest, announced)
            with partial.open("ab" if resume else "wb") as handle:
                for chunk in response.iter_bytes(1024 * 1024):
                    handle.write(chunk)
                    got += len(chunk)
                    last_note = _note(
                        on_progress,
                        label,
                        announced,
                        got,
                        started,
                        last_note,
                    )
    except httpx.HTTPError:
        _drop_empty_partial(partial)
        raise PlotweaverError(
            f"Could not download {label}. Check the network connection and try again."
        ) from None
    except OSError as exc:
        _drop_empty_partial(partial)
        raise PlotweaverError(f"Could not save {label}. {exc.strerror or exc}.") from None
    if partial.is_file() and partial.stat().st_size == 0:
        partial.unlink()
        raise PlotweaverError(f"Could not download {label}. The file was empty.")
    partial.replace(dest)


def require_disk_space(dest: Path, nbytes: int) -> None:
    """Refuse a download when the drive cannot hold the file plus a 10% margin."""
    need = int(nbytes * 1.10)
    if need < nbytes:
        need = nbytes
    probe = dest.parent
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    usage = shutil.disk_usage(probe)
    if usage.free >= need:
        return
    drive = dest.anchor or str(probe)
    needed = need / _GIB
    free = usage.free / _GIB
    raise PlotweaverError(
        f"Not enough disk space on {drive}. Need {needed:.1f} GB, {free:.1f} GB free."
    )


def _resume_from(partial: Path, total: int | None) -> int:
    if not partial.is_file():
        return 0
    size = partial.stat().st_size
    if size <= 0:
        partial.unlink()
        return 0
    if total is not None and size > total:
        partial.unlink()
        return 0
    return size


def _drop_empty_partial(partial: Path) -> None:
    try:
        if partial.is_file() and partial.stat().st_size == 0:
            partial.unlink()
    except OSError:
        return


def _content_length(response: httpx.Response) -> int | None:
    raw = response.headers.get("content-length")
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _note(
    on_progress: Callable[[str], None] | None,
    label: str,
    announced: int | None,
    got: int,
    started: float,
    last_note: float,
) -> float:
    if on_progress is None or not announced:
        return last_note
    now = time.monotonic()
    if now - last_note < 0.5 and got < announced:
        return last_note
    rate = got / max(now - started, 0.001)
    remaining = max(0.0, announced - got) / max(rate, 1.0)
    on_progress(
        tr("optional_eta").format(
            name=label,
            size=format_size(announced),
            eta=format_eta(remaining),
        )
    )
    return now
