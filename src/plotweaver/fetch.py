"""HTTP download that reports size and a plain-language time estimate."""

from __future__ import annotations

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
    """Download ``url`` to ``dest``. The destination appears only after the stream finishes."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    started = time.monotonic()
    got = 0
    last_note = 0.0
    try:
        with httpx.stream(
            "GET",
            url,
            headers={"User-Agent": "plotweaver"},
            follow_redirects=True,
            timeout=httpx.Timeout(3600.0, connect=30.0),
        ) as response:
            response.raise_for_status()
            announced = total if total is not None else _content_length(response)
            with partial.open("wb") as handle:
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
        partial.unlink(missing_ok=True)
        raise PlotweaverError(
            f"Could not download {label}. Check the network connection and try again."
        ) from None
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise PlotweaverError(f"Could not save {label}. {exc.strerror or exc}.") from None
    partial.replace(dest)


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
