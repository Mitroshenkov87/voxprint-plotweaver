"""Stage a relocatable Plotweaver tree: Python, dependencies, and llama.cpp.

The Windows installer and the Linux package both ship this directory.
Model weights are not included. They download on first run.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_COPY_DIRS = ("bakeoff", "branding", "scenarios", "docs", "scripts")
_COPY_FILES = (
    "pyproject.toml",
    "requirements.txt",
    "README.md",
    "LICENSE",
    "NOTICE",
    "BUILD.json",
)
_FETCH = """
from pathlib import Path
import sys
from plotweaver.llama_release import LLAMA_BUILD, ensure_llama_server, find_server

folder = Path(sys.argv[1])
binary = ensure_llama_server(folder)
if find_server(folder) != binary:
    raise SystemExit("llama-server was not unpacked")
marker = (folder / ".complete").read_text(encoding="utf-8").strip()
if marker != LLAMA_BUILD:
    raise SystemExit(f"llama.cpp marker is {marker!r}")
print(binary)
"""
_GUI_SH = """#!/bin/sh
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
exec "$ROOT/python/bin/python3" -m plotweaver gui "$@"
"""
_GUI_CMD = """@echo off\r
"%~dp0python\\pythonw.exe" -m plotweaver gui %*\r
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage a full Plotweaver runtime.")
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args(argv)
    dest = args.dest.resolve()
    if dest == _ROOT or dest in _ROOT.parents:
        raise SystemExit(f"refusing to stage into {dest}")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    prefix = _install_python(dest / "python")
    py = _base_python(prefix)
    for marker in prefix.rglob("EXTERNALLY-MANAGED"):
        marker.unlink()
    _uv("pip", "install", "--python", str(py), "--link-mode", "copy", str(_ROOT))
    _copy_payload(dest)
    runtime = dest / "runtime" / "llama.cpp-b11476"
    runtime.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("PLOTWEAVER_LLAMA_SERVER", None)
    env["PYTHONUTF8"] = "1"
    subprocess.run([str(py), "-c", _FETCH, str(runtime)], check=True, env=env)
    subprocess.run(
        [
            str(py),
            "-c",
            "import plotweaver; from plotweaver.paths import repo_root; "
            "root = repo_root(); assert (root / 'bakeoff' / 'models.toml').is_file(); "
            "print(plotweaver.__version__, root)",
        ],
        check=True,
        env=env,
    )
    print(dest)
    return 0


def _install_python(dest: Path) -> Path:
    parent = dest.parent / "_python_install"
    if parent.exists():
        shutil.rmtree(parent)
    parent.mkdir(parents=True)
    _uv("python", "install", "3.14", "--install-dir", str(parent), "--no-bin")
    matches = [item for item in parent.iterdir() if item.name.startswith("cpython-")]
    if not matches:
        raise SystemExit(f"no CPython install in {parent}")
    shutil.copytree(choose_cpython(matches), dest, symlinks=True)
    shutil.rmtree(parent)
    return dest


def choose_cpython(candidates: list[Path]) -> Path:
    """Pick the concrete install when uv also writes a shorter version alias."""

    def rank(item: Path) -> tuple[tuple[int, ...], int]:
        version = item.name.split("-", 2)[1]
        parts = tuple(int(piece) for piece in version.split(".") if piece.isdigit())
        concrete = 0 if item.is_symlink() else 1
        return (parts, concrete)

    return max(candidates, key=rank)


def _base_python(prefix: Path) -> Path:
    names = ("python.exe", "python3.14", "python3", "python")
    for folder in (prefix, prefix / "bin"):
        for name in names:
            candidate = folder / name
            if candidate.is_file():
                return candidate
    raise SystemExit(f"no Python executable in {prefix}")


def _uv(*args: str) -> None:
    probe = subprocess.run(
        [sys.executable, "-m", "uv", "--version"],
        capture_output=True,
        check=False,
    )
    if probe.returncode == 0:
        subprocess.run([sys.executable, "-m", "uv", *args], check=True)
        return
    if shutil.which("uv"):
        subprocess.run(["uv", *args], check=True)
        return
    raise SystemExit("uv is not installed")


def _copy_payload(dest: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        del directory
        return {name for name in names if name == "__pycache__" or name.endswith(".pyc")}

    for name in _COPY_DIRS:
        shutil.copytree(_ROOT / name, dest / name, symlinks=True, ignore=ignore)
    for name in _COPY_FILES:
        shutil.copy2(_ROOT / name, dest / name)
    gui = dest / "plotweaver-gui.sh"
    gui.write_text(_GUI_SH, encoding="utf-8", newline="\n")
    gui.chmod(0o755)
    (dest / "plotweaver-gui.cmd").write_text(_GUI_CMD, encoding="utf-8", newline="\n")
    for script in (dest / "scripts").glob("*.sh"):
        script.chmod(script.stat().st_mode | 0o755)


if __name__ == "__main__":
    raise SystemExit(main())
