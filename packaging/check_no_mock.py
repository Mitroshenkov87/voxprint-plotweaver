"""Fail when a built wheel or staged installer still contains the dev mock."""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Check a wheel, a directory of wheels, or a staged install tree."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, action="append", default=[])
    parser.add_argument("--wheel-dir", type=Path)
    parser.add_argument("--tree", type=Path)
    args = parser.parse_args(argv)
    wheels = list(args.wheel)
    if args.wheel_dir is not None:
        wheels.extend(sorted(args.wheel_dir.glob("*.whl")))
    if not wheels and args.tree is None:
        print("pass --wheel, --wheel-dir, or --tree", file=sys.stderr)
        return 2
    failed = False
    for wheel in wheels:
        failed = _check_wheel(wheel) or failed
    if args.tree is not None:
        failed = _check_tree(args.tree) or failed
    return 1 if failed else 0


def _check_wheel(path: Path) -> bool:
    if not path.is_file():
        print(f"missing wheel {path}", file=sys.stderr)
        return True
    bad: list[str] = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if _banned(name) or "/test_" in name or name.startswith("tests/"):
                bad.append(name)
        source = _wheel_text(archive, "plotweaver/llm.py")
        if "class MockBackend" in source or "mock_sound_document" in source:
            bad.append("plotweaver/llm.py contains mock code")
        sound = _wheel_text(archive, "plotweaver/sound.py")
        if "def mock_sound_document" in sound:
            bad.append("plotweaver/sound.py contains mock_sound_document")
    if bad:
        print(f"{path.name} contains mock or test modules:", file=sys.stderr)
        for item in bad:
            print(f"  {item}", file=sys.stderr)
        return True
    print(f"{path.name} has no mock or test modules")
    return False


def _check_tree(root: Path) -> bool:
    if not root.is_dir():
        print(f"missing install tree {root}", file=sys.stderr)
        return True
    failed = False
    common = list(root.rglob("voxprint_common/__init__.py"))
    if not common:
        print(f"{root} does not include voxprint_common", file=sys.stderr)
        failed = True
    dev = list(root.rglob("plotweaver_dev/__init__.py"))
    if dev:
        print(f"{root} includes plotweaver_dev: {dev[0]}", file=sys.stderr)
        failed = True
    wheels = list((root / "wheels").glob("voxprint_common-0.1.*.whl"))
    if not wheels:
        print(f"{root}/wheels is missing the voxprint-common 0.1 wheel", file=sys.stderr)
        failed = True
    for llm in root.rglob("plotweaver/llm.py"):
        text = llm.read_text(encoding="utf-8")
        if "class MockBackend" in text:
            print(f"{llm} still defines MockBackend", file=sys.stderr)
            failed = True
    if not failed:
        print(f"{root} bundles voxprint-common and has no dev mock")
    return failed


def _banned(name: str) -> bool:
    lowered = name.replace("\\", "/")
    return "plotweaver_dev" in lowered or "mock_backend" in lowered


def _wheel_text(archive: zipfile.ZipFile, suffix: str) -> str:
    for name in archive.namelist():
        if name.endswith(suffix):
            return archive.read(name).decode("utf-8")
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
