"""Command reference rendered from the live argument parser."""

from __future__ import annotations

import argparse

from plotweaver.cli import build_parser


def render_cli_reference(parser: argparse.ArgumentParser | None = None) -> str:
    """Render the command reference from the program's argument parser."""
    root = parser if parser is not None else build_parser()
    parts = [
        "# Command reference",
        "",
        "This page is generated from the argument parser when the documentation site is built.",
        "The notes for other apps are in [the command-line guide](CLI.md).",
        "",
    ]
    for item in _parsers(root):
        parts.append(f"## {item.prog}")
        parts.append("")
        parts.append("```text")
        parts.append(item.format_help().rstrip())
        parts.append("```")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _parsers(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    found = [parser]
    for action in parser._actions:
        if getattr(action, "nargs", None) != argparse.PARSER:
            continue
        choices = getattr(action, "choices", None)
        if not isinstance(choices, dict):
            continue
        for sub in choices.values():
            if isinstance(sub, argparse.ArgumentParser):
                found.extend(_parsers(sub))
    return found
