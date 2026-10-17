"""Stage a relocatable Plotweaver tree: Python, dependencies, and llama.cpp.

The Windows installer and the Linux package both ship this directory.
Shared runtimes and the stock model are installed by ``plotweaver provision``
when the user runs the installer, not while this package is built.
"""

from __future__ import annotations

import argparse
import hashlib
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
# Wheel built from voxprint-common v0.2.5 Yitro, 8a94b531cb4f3526425a80a86a1e64624b5de606.
# The normative pin is the git URL in pyproject.toml. --require-hashes cannot use it.
_COMMON_SHA256 = "334fdac85082b64fe6bb2f4c7ef17ed71419550f6050e043f29519a4139fea87"
_FETCH = """
from pathlib import Path
import sys
from plotweaver.llama_release import LLAMA_BUILD, find_server, install_pinned_runtime

folder = Path(sys.argv[1])
binary = install_pinned_runtime(folder)
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
_CLI_SH = """#!/bin/sh
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
exec "$ROOT/python/bin/python3" -m plotweaver "$@"
"""
_ALIAS_SH = """#!/bin/sh
echo "plotweaver is deprecated; use voxprint-plotweaver-cli" >&2
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
exec "$ROOT/python/bin/python3" -m plotweaver "$@"
"""
_GUI_CMD = """@echo off\r
"%~dp0voxprint-plotweaver.exe" %*\r
"""
_PROVISION_SH = """#!/bin/sh
ROOT=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
"$ROOT/python/bin/python3" -m plotweaver mdl-progress --quiet --installer
exit 0
"""
_PROVISION_CMD = """@echo off\r
"%~dp0python\\python.exe" -m plotweaver mdl-progress --quiet --installer\r
exit /b 0\r
"""
_LAUNCHER_CS = r"""
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
class Program {
  static int Main(string[] args) {
    __DEPRECATE__
    string root = AppDomain.CurrentDomain.BaseDirectory;
    string py = Path.Combine(root, "python", "__PYTHON__");
    var psi = new ProcessStartInfo();
    psi.FileName = py;
    psi.UseShellExecute = false;
    psi.WorkingDirectory = root;
    var all = new List<string>();
    __PREFIX__
    foreach (string arg in args) all.Add(Quote(arg));
    psi.Arguments = string.Join(" ", all.ToArray());
    var proc = Process.Start(psi);
    if (proc == null) return 1;
    proc.WaitForExit();
    return proc.ExitCode;
  }
  static string Quote(string value) {
    if (value.IndexOfAny(new char[] { ' ', '\t', '"' }) < 0) return value;
    return "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";
  }
}
"""


def _refuse_suite_root(path: Path) -> None:
    """Refuse a suite home, a shared root, or an ancestor of one.

    Same refuse-list as ``plotweaver.manifest.refuse_shared_delete``. This
    script runs before the staged tree exists, so it does not import it.
    """
    resolved = path.resolve()
    homes: list[Path] = []
    configured = os.environ.get("VOXPRINT_HOME", "").strip()
    if configured:
        homes.append(Path(configured))
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        homes.append(Path(local) / "Voxprint")
    homes.append(Path.home() / ".local" / "share" / "voxprint")
    protected: list[Path] = []
    for item in homes:
        root = item.resolve()
        protected.append(root)
        for name in ("shared", "models", "runtime", "voices", "cache"):
            protected.append(root / name)
            if name != "shared":
                protected.append(root / "shared" / name)
    for root in protected:
        if resolved == root or resolved in root.parents:
            raise SystemExit(f"refusing to delete {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage a full Plotweaver runtime.")
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args(argv)
    dest = args.dest.resolve()
    if dest == _ROOT or dest in _ROOT.parents:
        raise SystemExit(f"refusing to stage into {dest}")
    _refuse_suite_root(dest)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    prefix = _install_python(dest / "python")
    py = _base_python(prefix)
    for marker in prefix.rglob("EXTERNALLY-MANAGED"):
        marker.unlink()
    wheel = _common_wheel()
    wheels = wheel.parent
    # jeepney is not vendored. The project install below resolves other deps.
    _uv(
        "pip",
        "install",
        "--python",
        str(py),
        "--link-mode",
        "copy",
        "--no-index",
        "--no-deps",
        str(wheel),
    )
    _uv(
        "pip",
        "install",
        "--python",
        str(py),
        "--link-mode",
        "copy",
        "--find-links",
        str(wheels),
        str(_ROOT),
    )
    _bundle_common(wheels, wheel, dest)
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
    _stamp_packaged_build(py, dest, env)
    print(dest)
    return 0


def _common_wheel() -> Path:
    """Vendored voxprint-common 0.2.5 wheel. Installers must not fetch it."""
    wheel = _ROOT / "packaging" / "wheels" / "voxprint_common-0.2.5-py3-none-any.whl"
    if not wheel.is_file():
        raise SystemExit("packaging/wheels is missing voxprint-common 0.2.5")
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if digest != _COMMON_SHA256:
        raise SystemExit(f"voxprint-common wheel sha256 is {digest}")
    return wheel


def _bundle_common(wheels: Path, wheel: Path, dest: Path) -> None:
    """Copy the wheel, the sdist, and their sha256 sidecars into the stage."""
    bundled = dest / "wheels"
    bundled.mkdir()
    shutil.copy2(wheel, bundled / wheel.name)
    version = wheel.name.split("-", 2)[1]
    names = [
        f"{wheel.name}.sha256",
        f"voxprint_common-{version}.tar.gz",
        f"voxprint_common-{version}.tar.gz.sha256",
    ]
    for name in names:
        extra = wheels / name
        if not extra.is_file():
            raise SystemExit(f"packaging/wheels is missing {name}")
        shutil.copy2(extra, bundled / name)


def _install_python(dest: Path) -> Path:
    parent = dest.parent / "_python_install"
    _refuse_suite_root(parent)
    if parent.exists():
        shutil.rmtree(parent)
    parent.mkdir(parents=True)
    _uv("python", "install", "3.14", "--install-dir", str(parent), "--no-bin")
    matches = [item for item in parent.iterdir() if item.name.startswith("cpython-")]
    if not matches:
        raise SystemExit(f"no CPython install in {parent}")
    shutil.copytree(choose_cpython(matches), dest, symlinks=True)
    _refuse_suite_root(parent)
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


def _stamp_packaged_build(py: Path, dest: Path, env: dict[str, str]) -> None:
    """CI build number is GITHUB_RUN_NUMBER + BUILD.json offset. Local stays dev."""
    run = os.environ.get("GITHUB_RUN_NUMBER", "")
    if not run.isdigit():
        return
    script = (
        "import os, sys\n"
        "from pathlib import Path\n"
        "from plotweaver.appinfo import stamp_build\n"
        "print(stamp_build(Path(sys.argv[1]), int(os.environ['GITHUB_RUN_NUMBER'])))\n"
    )
    subprocess.run([str(py), "-c", script, str(dest / "BUILD.json")], check=True, env=env)


def _copy_payload(dest: Path) -> None:
    def ignore(directory: str, names: list[str]) -> set[str]:
        del directory
        return {name for name in names if name == "__pycache__" or name.endswith(".pyc")}

    for name in _COPY_DIRS:
        shutil.copytree(_ROOT / name, dest / name, symlinks=True, ignore=ignore)
    for name in _COPY_FILES:
        shutil.copy2(_ROOT / name, dest / name)
    data = _ROOT / "src" / "plotweaver" / "data"
    for name in ("mdl.json", "voxprint-app-models.json"):
        shutil.copy2(data / name, dest / name)
    _write_script(dest / "voxprint-plotweaver", _GUI_SH)
    _write_script(dest / "voxprint-plotweaver-cli", _CLI_SH)
    _write_script(dest / "plotweaver", _ALIAS_SH)
    _write_script(dest / "plotweaver-gui.sh", _GUI_SH)
    (dest / "plotweaver-gui.cmd").write_text(_GUI_CMD, encoding="utf-8", newline="\n")
    _write_script(dest / "plotweaver-provision.sh", _PROVISION_SH)
    (dest / "plotweaver-provision.cmd").write_text(_PROVISION_CMD, encoding="utf-8", newline="\n")
    if sys.platform == "win32":
        _compile_windows_launcher(
            dest,
            "voxprint-plotweaver.exe",
            python_name="pythonw.exe",
            prefix='all.Add("-m"); all.Add("plotweaver"); all.Add("gui");',
            winexe=True,
            deprecate=False,
        )
        _compile_windows_launcher(
            dest,
            "voxprint-plotweaver-cli.exe",
            python_name="python.exe",
            prefix='all.Add("-m"); all.Add("plotweaver");',
            winexe=False,
            deprecate=False,
        )
        _compile_windows_launcher(
            dest,
            "plotweaver.exe",
            python_name="python.exe",
            prefix='all.Add("-m"); all.Add("plotweaver");',
            winexe=False,
            deprecate=True,
        )
    for script in (dest / "scripts").glob("*.sh"):
        script.chmod(script.stat().st_mode | 0o755)


def _write_script(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | 0o755)


def _compile_windows_launcher(
    dest: Path,
    name: str,
    *,
    python_name: str,
    prefix: str,
    winexe: bool,
    deprecate: bool,
) -> None:
    """Compile one small exe that starts the staged interpreter."""
    deprecate_line = ""
    if deprecate:
        deprecate_line = (
            'Console.Error.WriteLine("plotweaver is deprecated; use voxprint-plotweaver-cli");'
        )
    source_text = (
        _LAUNCHER_CS.replace("__DEPRECATE__", deprecate_line)
        .replace("__PYTHON__", python_name)
        .replace("__PREFIX__", prefix)
    )
    source = dest / f"{name}.cs"
    source.write_text(source_text, encoding="utf-8", newline="\n")
    target = "/target:winexe" if winexe else "/target:exe"
    subprocess.run(
        [_csc(), "/nologo", target, f"/out:{dest / name}", str(source)],
        check=True,
    )
    source.unlink()


def _csc() -> str:
    roots = (
        Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe"),
    )
    for candidate in roots:
        if candidate.is_file():
            return str(candidate)
    raise SystemExit("csc.exe was not found")


if __name__ == "__main__":
    raise SystemExit(main())
