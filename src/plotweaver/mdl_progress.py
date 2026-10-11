"""Run VOXPrint MDL and render its JSON events.

Plotweaver does not download model bytes. ``voxprint-mdl download`` does.
0.2.1 has no progress window, so a caller draws these events itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Callable, Sequence
from importlib.metadata import version
from pathlib import Path

from voxprint_common.paths import logs_dir

APP_ID = "plotweaver"
EventFn = Callable[[dict[str, object]], None]


def mdl_gui_supported() -> bool:
    """True when this voxprint-common build ships the MDL window.

    The window arrives in 0.2.2. 0.2.1 accepts ``--gui`` and then fails
    closed or opens an unfinished window, so Manage models does not use it.
    """
    text = version("voxprint-common")
    parts: list[int] = []
    for piece in text.split("."):
        digits = ""
        for char in piece:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3]) >= (0, 2, 2)


def download_command(models: Sequence[str] = ()) -> list[str]:
    """``voxprint-mdl download --app plotweaver --json``, plus optional model ids."""
    command = [
        sys.executable,
        "-m",
        "voxprint_common.mdl",
        "download",
        "--app",
        APP_ID,
        "--json",
    ]
    for model_id in models:
        command.extend(["--model", model_id])
    return command


def install_log_path() -> Path:
    """Installer log. The directory is created when the download starts."""
    return logs_dir() / "plotweaver-mdl-install.log"


def run_download(
    command: Sequence[str] | None = None,
    *,
    log: Path | None = None,
    on_event: EventFn | None = None,
    process: list[subprocess.Popen[str]] | None = None,
) -> int:
    """Run the MDL download and return its exit code.

    Each JSON object on stdout is passed to ``on_event``. ``log`` receives
    stdout and stderr. A non-JSON line is logged and ignored.
    """
    argv = list(command) if command is not None else download_command()
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None
    if process is not None:
        process.append(proc)
    errand = threading.Thread(target=_drain, args=(proc.stderr, log), daemon=True)
    errand.start()
    try:
        for line in proc.stdout:
            _log_line(log, line)
            event = _event(line)
            if event is not None and on_event is not None:
                on_event(event)
    finally:
        proc.wait()
        errand.join()
    return int(proc.returncode or 0)


def _event(line: str) -> dict[str, object] | None:
    text = line.strip()
    if not text:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or payload.get("type") not in {"progress", "result"}:
        return None
    return payload


def _drain(stream: object, log: Path | None) -> None:
    read = getattr(stream, "read", None)
    if not callable(read):
        return
    text = read()
    if isinstance(text, str) and text and log is not None:
        with log.open("a", encoding="utf-8") as handle:
            handle.write(text)


def _log_line(log: Path | None, line: str) -> None:
    if log is None:
        return
    with log.open("a", encoding="utf-8") as handle:
        handle.write(line)
