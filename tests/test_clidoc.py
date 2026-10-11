"""The command reference is taken from the argument parser, not a hand copy."""

from __future__ import annotations

from plotweaver.cli import build_parser
from plotweaver.clidoc import render_cli_reference


def test_cli_reference_lists_the_live_commands() -> None:
    text = render_cli_reference(build_parser())
    assert text.startswith("# Command reference\n")
    for heading in (
        "## plotweaver",
        "## plotweaver run",
        "## plotweaver export",
        "## plotweaver scenario-mars",
        "## plotweaver vxbook validate",
        "## plotweaver models list",
        "## plotweaver mdl-progress",
        "## plotweaver sound add",
        "## plotweaver brief draft",
    ):
        assert heading in text
    assert "--json" in text
    assert "--dry-run" in text
    assert "--brief" in text
