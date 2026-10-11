"""Version stamp. BUILD.json at the install root is the only source."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_NAME = "VOXPrint AI Plotweaver"
GITHUB_REPO = "Mitroshenkov87/voxprint-plotweaver"
LOCK_OWNER = "plotweaver"
DEV_BUILD = "dev"
_REQUIRED = ("version", "codename", "offset")


def build_json_path() -> Path:
    """BUILD.json for this install. PLOTWEAVER_BUILD_JSON overrides the search.

    The search stays in this module so setuptools can import it while reading the
    package version, before the rest of the package is on the path.
    """
    override = os.environ.get("PLOTWEAVER_BUILD_JSON")
    if override:
        return Path(override)
    here = Path(__file__).resolve()
    for candidate in (here.parent, *here.parents):
        found = candidate / "BUILD.json"
        marked = (candidate / "pyproject.toml").is_file() or candidate == here.parent
        if found.is_file() and marked:
            return found
    raise FileNotFoundError("BUILD.json was not found")


def _read_text(path: Path) -> str:
    """Read BUILD.json, including a BOM, without importing the rest of the package."""
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    return data.decode("utf-8")


def load_build() -> dict[str, Any]:
    """Read BUILD.json. Callers that display a label should use version_label()."""
    path = build_json_path()
    try:
        data = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"BUILD.json is missing or invalid: {path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"BUILD.json must be an object: {path}")
    missing = [key for key in _REQUIRED if key not in data]
    if missing:
        raise RuntimeError(f"BUILD.json needs {', '.join(missing)}")
    return data


def package_version(info: dict[str, Any] | None = None) -> str:
    """PEP 440 version. A prerelease of rc7 on 0.2.0 is 0.2.0rc7."""
    payload = load_build() if info is None else info
    version = str(payload["version"])
    pre = payload.get("prerelease")
    if pre in (None, False, ""):
        return version
    return f"{version}{pre}"


def is_prerelease(info: dict[str, Any] | None = None) -> bool:
    payload = load_build() if info is None else info
    return payload.get("prerelease") not in (None, False, "")


def _channel(info: dict[str, Any]) -> str:
    if is_prerelease(info):
        return " RC"
    return ""


def _build_marker(info: dict[str, Any]) -> str:
    build = info.get("build")
    if build is None:
        return DEV_BUILD
    return str(int(build))


def version_label(info: dict[str, Any] | None = None) -> str:
    """Display form: `X.Y.Z RC · build N "Codename"`. Final releases drop RC."""
    payload = load_build() if info is None else info
    version = str(payload["version"])
    codename = str(payload["codename"])
    return f'{version}{_channel(payload)} · build {_build_marker(payload)} "{codename}"'


def release_title(run_number: int) -> str:
    """Title for a GitHub release built by this Actions run."""
    info = dict(load_build())
    info["build"] = int(run_number) + int(info["offset"])
    return version_label(info)


def stamp_build(path: Path, run_number: int) -> int:
    """Write build = run number + offset. Local checkouts stay null and show dev."""
    data = json.loads(_read_text(path))
    if not isinstance(data, dict) or "offset" not in data:
        raise RuntimeError(f"BUILD.json must be an object with offset: {path}")
    build = int(run_number) + int(data["offset"])
    data["build"] = build
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return build


APP_VERSION = package_version()
