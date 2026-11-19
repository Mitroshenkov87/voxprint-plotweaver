"""Write the generated command reference before MkDocs collects pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from plotweaver.clidoc import render_cli_reference

_DOCS = Path(__file__).resolve().parent


def write_cli_reference() -> Path:
    """Refresh docs/cli-reference.md from the current argument parser."""
    path = _DOCS / "cli-reference.md"
    path.write_text(render_cli_reference(), encoding="utf-8")
    return path


def on_pre_build(config: dict[str, Any]) -> None:
    """Regenerate the command reference and include the brief guide when it exists."""
    write_cli_reference()
    brief = Path(str(config["docs_dir"])) / "WRITING-A-BRIEF.md"
    if not brief.is_file():
        return
    nav = config.get("nav")
    if not isinstance(nav, list):
        return
    entry = {"Writing a brief": "WRITING-A-BRIEF.md"}
    if entry in nav:
        return
    nav.insert(1, entry)


write_cli_reference()
