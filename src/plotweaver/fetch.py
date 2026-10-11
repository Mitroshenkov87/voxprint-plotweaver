"""HTTP download that reports size and a plain-language time estimate.

A dropped connection resumes the ``.partial`` file with an HTTP Range request.
Ten attempts back off, then the bytes are hashed and renamed into place.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from voxprint_common.hashing import sha256_file

from plotweaver.errors import PlotweaverError
from plotweaver.ui.i18n import tr

_MIB = 1024 * 1024
_GIB = 1024 * 1024 * 1024
_ATTEMPTS = 10
_RESERVE = 2 * _GIB
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def require_sha256(sha256: str, label: str) -> str:
    """Refuse a model whose registry entry has no 64-hex SHA-256."""
    digest = (sha256 or "").strip().lower()
    if _SHA256.fullmatch(digest) is None:
        raise PlotweaverError(
            f"Refusing to download or load {label}. The registry entry has no SHA-256."
        )
    return digest


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
    sha256: str,
) -> None:
    """Download ``url`` to ``dest``. Resume, retry, check the hash, then rename."""
    digest = require_sha256(sha256, label)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if total is not None and total > 0:
        require_disk_space(dest, total)
    partial = dest.with_suffix(dest.suffix + ".partial")
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            _pull(url, partial, total, on_progress, label)
            break
        except httpx.HTTPError:
            _drop_empty_partial(partial)
            if attempt >= _ATTEMPTS:
                raise PlotweaverError(
                    f"Could not download {label}. Check the network connection and try again."
                ) from None
            time.sleep(min(30.0, float(2 ** (attempt - 1))))
        except OSError as exc:
            _drop_empty_partial(partial)
            raise PlotweaverError(f"Could not save {label}. {exc.strerror or exc}.") from None
    _finalize(partial, dest, total, digest, label)


def require_disk_space(dest: Path, nbytes: int) -> None:
    """Refuse a download when the drive cannot hold the file, 10%, and 2 GB."""
    margin = int(nbytes * 1.10)
    if margin < nbytes:
        margin = nbytes
    need = margin + _RESERVE
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


def _pull(
    url: str,
    partial: Path,
    total: int | None,
    on_progress: Callable[[str], None] | None,
    label: str,
) -> None:
    resume = _resume_from(partial, total)
    if resume and total is not None and resume >= total:
        return
    headers = {"User-Agent": "plotweaver"}
    if resume:
        headers["Range"] = f"bytes={resume}-"
    started = time.monotonic()
    got = resume
    last_note = 0.0
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
            require_disk_space(partial, announced)
        with partial.open("ab" if resume else "wb") as handle:
            for chunk in response.iter_bytes(1024 * 1024):
                handle.write(chunk)
                got += len(chunk)
                last_note = _note(on_progress, label, announced, got, started, last_note)


def _finalize(
    partial: Path,
    dest: Path,
    total: int | None,
    sha256: str,
    label: str,
) -> None:
    if not partial.is_file() or partial.stat().st_size == 0:
        if partial.is_file():
            partial.unlink()
        raise PlotweaverError(f"Could not download {label}. The file was empty.")
    size = partial.stat().st_size
    if total is not None and size != total:
        raise PlotweaverError(
            f"Could not download {label}. The download stopped at {size} of {total} bytes."
        )
    found = sha256_file(partial)
    if found != sha256:
        partial.unlink()
        raise PlotweaverError(f"{label} SHA-256 {found} does not match {sha256}")
    os.replace(partial, dest)


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
            speed=f"{format_size(int(rate))}/s",
            eta=format_eta(remaining),
        )
    )
    return now
