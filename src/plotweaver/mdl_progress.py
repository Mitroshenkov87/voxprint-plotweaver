"""Run VOXPrint MDL.

Plotweaver does not download or repair model bytes. Manage models opens
``voxprint-mdl --gui --app plotweaver``. An interactive installer opens
``voxprint-mdl download --gui``. ``/VERYSILENT`` stays on the JSON log.
Launch repair is ``voxprint-mdl verify --repair --app plotweaver``.
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


def manage_command() -> list[str]:
    """``voxprint-mdl --gui --app plotweaver``. No download subcommand."""
    return [sys.executable, "-m", "voxprint_common.mdl", "--gui", "--app", APP_ID]


def installer_gui_command() -> list[str]:
    """Interactive installer progress: the MDL download window."""
    return [
        sys.executable,
        "-m",
        "voxprint_common.mdl",
        "download",
        "--gui",
        "--app",
        APP_ID,
    ]


def verify_repair_command() -> list[str]:
    """Launch repair. MDL neutralises a dangerous manifest path and re-checks files."""
    return [
        sys.executable,
        "-m",
        "voxprint_common.mdl",
        "verify",
        "--repair",
        "--app",
        APP_ID,
    ]


def run_mdl(command: Sequence[str]) -> int | None:
    """Run one MDL command. ``None`` means the process could not be started."""
    try:
        completed = subprocess.run(command, check=False)
    except OSError:
        return None
    return int(completed.returncode)


def launch_repair() -> int:
    """Run ``voxprint-mdl verify --repair --app plotweaver`` and return its code."""
    code = run_mdl(verify_repair_command())
    if code is None:
        raise OSError("voxprint-mdl verify --repair could not be started")
    return code


def mdl_gui_supported() -> bool:
    """True when this voxprint-common build ships the MDL window.

    The localized window is in 0.2.4. Older builds are not used.
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
