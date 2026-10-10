"""Command line: run a book, open the window, bake off models, or run the Mars scenario."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from plotweaver.appinfo import APP_NAME, version_label
from plotweaver.bakeoff import run_bakeoff
from plotweaver.brief import BookBrief, BriefError, apply_brief, parse_brief, render_markdown
from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.errors import GpuUnsupported, PlotweaverError
from plotweaver.export import export_output_names
from plotweaver.hardware import require_supported_gpu, vram_budget_gb, vram_headroom_gb
from plotweaver.install import prepare_real_models
from plotweaver.llama_release import ensure_llama_server
from plotweaver.llama_server import LlamaServer, apply_vram_budget_cap
from plotweaver.llm import LLMBackend, MockBackend
from plotweaver.registry import (
    detected_tier,
    import_forge_manifest,
    load_registry,
    model_public_row,
    registry_path,
    resolve_tier,
    tier_headroom_gb,
    usable_vram_gb,
)
from plotweaver.runner import draft_book_brief, export_book, run_book
from plotweaver.scenarios import mars_request
from plotweaver.sound import add_sound, resolve_vxbook
from plotweaver.store import Project
from plotweaver.ui.splash import Splash
from plotweaver.ui.window import MainWindow
from plotweaver.vxbook import validate_vxbook


def build_parser() -> argparse.ArgumentParser:
    """Build the plotweaver command parser, including every subcommand."""
    parser = argparse.ArgumentParser(prog="plotweaver", description=APP_NAME)
    parser.add_argument("--version", action="version", version=version_label())
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="Print the version and codename.")
    version.set_defaults(func=_version)

    doctor = sub.add_parser("doctor", help="Show the GPU check.")
    doctor.add_argument("--mock", action="store_true")
    doctor.set_defaults(func=_doctor)

    run = sub.add_parser("run", help="Write or resume one book.")
    _add_book_args(run)
    _add_machine_args(run)
    run.set_defaults(func=_run)

    export = sub.add_parser("export", help="Export an existing project, including book.vxbook.")
    export.add_argument("--project", type=Path, required=True)
    export.add_argument("--export-dir", type=Path)
    export.add_argument("--mock", action="store_true")
    _add_export_args(export)
    _add_machine_args(export)
    export.set_defaults(func=_export)

    scenario = sub.add_parser(
        "scenario-mars",
        help="Write the short Russian Mars story and the Audiobook Builder export.",
    )
    scenario.add_argument("--project", type=Path, default=Path("out/mars-e2e/project"))
    scenario.add_argument("--export-dir", type=Path, default=Path("out/mars-e2e"))
    scenario.add_argument("--mock", action="store_true")
    scenario.add_argument("--yes", action="store_true", help="Skip bible and outline approval.")
    scenario.add_argument("--main-gguf", default="")
    scenario.add_argument("--least-censored-gguf", default="")
    scenario.add_argument("--main-model-id", default="")
    scenario.add_argument("--least-censored-model-id", default="")
    _add_export_args(scenario)
    _add_machine_args(scenario)
    scenario.set_defaults(func=_scenario_mars)

    bake = sub.add_parser("bakeoff", help="Run the Russian 10x3 bake-off, or a mock slice of it.")
    bake.add_argument("--results", type=Path, default=Path("out/bakeoff"))
    bake.add_argument("--mock", action="store_true")
    bake.add_argument(
        "--limit", type=int, default=0, help="Only the first N synopses. 0 means all."
    )
    bake.add_argument("--allow-other-license", action="store_true")
    bake.set_defaults(func=_bakeoff)

    gui = sub.add_parser("gui", help="Open the desktop window.")
    gui.add_argument("--mock", action="store_true")
    gui.add_argument(
        "--selftest", action="store_true", help="Write a one-chapter mock book and exit."
    )
    gui.set_defaults(func=_gui)

    vxbook = sub.add_parser("vxbook", help="Check or inspect a Voxprint Book.")
    vx = vxbook.add_subparsers(dest="vx_command", required=True)
    validate = vx.add_parser("validate", help="Run the Voxprint Book validation checklist.")
    validate.add_argument("file", type=Path)
    _add_machine_args(validate)
    validate.set_defaults(func=_vxbook_validate)

    models = sub.add_parser("models", help="Registry tools for Model Forge publications.")
    model_commands = models.add_subparsers(dest="models_command", required=True)
    listing = model_commands.add_parser("list", help="List registry models.")
    listing.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Registry file to read. Defaults to bakeoff/models.toml.",
    )
    _add_machine_args(listing)
    listing.set_defaults(func=_models_list)
    forge = model_commands.add_parser(
        "import-forge-manifest",
        help="Enable placeholder rows from a Model Forge JSON manifest.",
    )
    forge.add_argument("file", type=Path)
    forge.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="Registry file to update. Defaults to bakeoff/models.toml.",
    )
    _add_machine_args(forge)
    forge.set_defaults(func=_import_forge_manifest)

    sound = sub.add_parser("sound", help="Add VXBOOK v1.1 + sound extension v1 markup.")
    sound_commands = sound.add_subparsers(dest="sound_command", required=True)
    sound_add = sound_commands.add_parser("add", help="Write a new .vxbook with sound markup.")
    sound_add.add_argument("src", type=Path, help="A .vxbook file or a Plotweaver project folder.")
    sound_add.add_argument("-o", "--output", type=Path, required=True)
    sound_add.add_argument("--mock", action="store_true")
    sound_add.add_argument(
        "--mirror",
        action="store_true",
        help="Also write optional vx:sound lines. Off by default.",
    )
    _add_machine_args(sound_add)
    sound_add.set_defaults(func=_sound_add)

    brief = sub.add_parser("brief", help="Draft a book brief from loose notes.")
    brief_commands = brief.add_subparsers(dest="brief_command", required=True)
    draft = brief_commands.add_parser("draft", help="Expand notes into a book brief.")
    draft.add_argument("--idea", required=True, help="Loose notes to expand.")
    draft.add_argument("--language", choices=["ru", "en"], default="en")
    draft.add_argument("--mock", action="store_true")
    _add_machine_args(draft)
    draft.set_defaults(func=_brief_draft)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one plotweaver command and return its exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GpuUnsupported as exc:
        return _fail(args, str(exc), 2)
    except PlotweaverError as exc:
        return _fail(args, str(exc), 1)


def _add_book_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--synopsis", type=Path)
    parser.add_argument(
        "--brief",
        type=Path,
        default=None,
        help="Book brief in JSON or the Markdown template. Supplies the book fields.",
    )
    parser.add_argument("--title", default="Untitled")
    parser.add_argument("--language", choices=["ru", "en"], default="ru")
    parser.add_argument("--genre", default="")
    parser.add_argument("--target-words", type=int, default=80_000)
    parser.add_argument("--chapters", type=int, default=0)
    parser.add_argument("--scenes-per-chapter", type=int, default=2)
    parser.add_argument("--dark-themes", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--tier",
        choices=[ModelTier.STANDARD.value, ModelTier.LEAST_CENSORED.value],
        default=ModelTier.STANDARD.value,
        help="standard, or least-censored (an installed Model Forge model).",
    )
    parser.add_argument("--mode", choices=["autopilot", "copilot", "manual"], default="autopilot")
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Do not stop for approval.")
    parser.add_argument(
        "--approve", action="store_true", help="Clear the gate the book is waiting on."
    )
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--main-gguf", default="")
    parser.add_argument("--least-censored-gguf", default="")
    parser.add_argument("--main-model-id", default="")
    parser.add_argument("--least-censored-model-id", default="")
    _add_export_args(parser)


def _add_export_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--author",
        default="",
        help="Author stored in EPUB and FictionBook title-info.",
    )
    parser.add_argument("--fb2", action="store_true", help="Also write FictionBook 2.1.")
    parser.add_argument("--docx", action="store_true", help="Also write DOCX.")
    parser.add_argument("--markdown", action="store_true", help="Also write Markdown.")
    parser.add_argument(
        "--speaker-marks",
        action="store_true",
        help="Also write the legacy numbered speaker-marks pair.",
    )
    parser.add_argument(
        "--sound",
        action="store_true",
        help="Also write book.sound.vxbook (VXBOOK v1.1 + sound extension v1).",
    )


def _add_machine_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON object on stdout. The schema is in docs/CLI.md.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs and print the planned actions. Write nothing and do not run a model.",
    )


def _export_formats(args: argparse.Namespace) -> list[str]:
    chosen = ["epub"]
    if args.fb2:
        chosen.append("fb2")
    if args.docx:
        chosen.append("docx")
    if args.markdown:
        chosen.append("markdown")
    if args.speaker_marks:
        chosen.append("speaker-marks")
    return chosen


def _fail(args: argparse.Namespace, message: str, code: int) -> int:
    if getattr(args, "json", False):
        _print_json({"ok": False, "error": message, "code": code})
    else:
        print(message, file=sys.stderr)
    return code


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _emit(args: argparse.Namespace, payload: dict[str, Any], text: str) -> int:
    if args.json:
        _print_json(payload)
    elif text:
        print(text)
    return int(payload.get("code", 0))


def _output_paths(directory: Path, formats: list[str], *, sound: bool) -> list[str]:
    return [str((directory / name).resolve()) for name in export_output_names(formats, sound=sound)]


def _vxbook_validate(args: argparse.Namespace) -> int:
    if args.dry_run:
        if not args.file.is_file():
            raise PlotweaverError(f"not a file: {args.file}")
        payload: dict[str, Any] = {
            "ok": True,
            "command": "vxbook.validate",
            "dry_run": True,
            "code": 0,
            "file": str(args.file.resolve()),
            "actions": ["run the Voxprint Book validation checklist"],
            "outputs": [],
        }
        text = f"dry-run\naction: validate {args.file.resolve()}"
        return _emit(args, payload, text)
    issues = validate_vxbook(args.file)
    failed = any(issue.severity == "error" for issue in issues)
    rows = [{"severity": issue.severity, "message": issue.message} for issue in issues]
    if args.json:
        _print_json(
            {
                "ok": not failed,
                "command": "vxbook.validate",
                "dry_run": False,
                "code": 1 if failed else 0,
                "file": str(args.file.resolve()),
                "issues": rows,
            }
        )
    else:
        for issue in issues:
            print(f"{issue.severity}: {issue.message}")
        if not issues:
            print("ok")
    return 1 if failed else 0


def _sound_add(args: argparse.Namespace) -> int:
    source = resolve_vxbook(args.src)
    if source.resolve() == args.output.resolve():
        raise PlotweaverError("sound markup writes a new file and leaves the original in place")
    if args.dry_run:
        problems = [issue.message for issue in validate_vxbook(source) if issue.severity == "error"]
        if problems:
            raise PlotweaverError(problems[0])
        payload: dict[str, Any] = {
            "ok": True,
            "command": "sound.add",
            "dry_run": True,
            "code": 0,
            "source": str(source.resolve()),
            "output": str(args.output.resolve()),
            "mirror": bool(args.mirror),
            "actions": ["read the source .vxbook", "write sound markup to the output .vxbook"],
            "outputs": [str(args.output.resolve())],
        }
        text = f"dry-run\nsource: {source.resolve()}\noutput: {args.output.resolve()}"
        return _emit(args, payload, text)
    warnings = add_sound(source, args.output, _backend(bool(args.mock)), mirror=bool(args.mirror))
    payload = {
        "ok": True,
        "command": "sound.add",
        "dry_run": False,
        "code": 0,
        "source": str(source.resolve()),
        "output": str(args.output.resolve()),
        "mirror": bool(args.mirror),
        "warnings": list(warnings),
    }
    lines = [f"warning: {message}" for message in warnings]
    lines.append(str(args.output))
    return _emit(args, payload, "\n".join(lines))


def _models_list(args: argparse.Namespace) -> int:
    path = args.registry or registry_path()
    if not path.is_file():
        raise PlotweaverError(f"registry not found: {path}")
    rows = [model_public_row(entry) for entry in load_registry(path)]
    payload: dict[str, Any] = {
        "ok": True,
        "command": "models.list",
        "dry_run": bool(args.dry_run),
        "code": 0,
        "registry": str(path.resolve()),
        "actions": ["read the model registry"],
        "models": rows,
    }
    lines = ["dry-run"] if args.dry_run else []
    for row in rows:
        state = "enabled" if row["enabled"] else "disabled"
        lines.append(f"{row['id']}\t{state}\t{row['tier']}\t{row['role']}\t{row['filename']}")
    return _emit(args, payload, "\n".join(lines))


def _import_forge_manifest(args: argparse.Namespace) -> int:
    if not args.file.is_file():
        raise PlotweaverError(f"manifest not found: {args.file}")
    path = args.registry or registry_path()
    enabled = import_forge_manifest(args.file, path, dry_run=bool(args.dry_run))
    payload: dict[str, Any] = {
        "ok": True,
        "command": "models.import-forge-manifest",
        "dry_run": bool(args.dry_run),
        "code": 0,
        "registry": str(path.resolve()),
        "manifest": str(args.file.resolve()),
        "models": enabled,
        "writes": not bool(args.dry_run),
        "actions": [
            "validate the Model Forge manifest",
            "enable the listed placeholder rows"
            if not args.dry_run
            else "leave the registry unchanged",
        ],
    }
    prefix = "dry-run\n" if args.dry_run else ""
    return _emit(args, payload, prefix + "\n".join(enabled))


def _version(_args: argparse.Namespace) -> int:
    print(version_label())
    return 0


def _doctor(args: argparse.Namespace) -> int:
    print(f"{APP_NAME} {version_label()}")
    if args.mock:
        print("Mock mode: the GPU check is skipped.")
        return 0
    info = require_supported_gpu()
    budget = vram_budget_gb(info.free_gb, info.total_gb)
    capped = apply_vram_budget_cap(budget)
    chosen = resolve_tier(info.total_gb)
    cap_note = ""
    if capped < budget:
        cap_note = f" Server budget capped at {capped:.1f} GB."
    print(
        f"{info.name}: compute {info.compute_cap}, "
        f"VRAM {info.free_gb:.1f} of {info.total_gb:.1f} GB free, "
        f"budget {budget:.1f} GB (headroom {vram_headroom_gb(info.total_gb):.1f} GB). "
        f"Model tier {chosen} (detected {detected_tier(info.total_gb)}), "
        f"usable {usable_vram_gb(info.total_gb, info.free_gb):.1f} GB "
        f"with {tier_headroom_gb(info.total_gb):.0f} GB held back."
        f"{cap_note}"
    )
    return 0


def _backend(mock: bool) -> LLMBackend:
    if mock:
        return MockBackend()
    require_supported_gpu()
    return LlamaServer(ensure_llama_server())


def _apply_models(request: BookRequest, args: argparse.Namespace) -> None:
    if args.main_gguf:
        request.main_gguf = args.main_gguf
        request.main_model_id = args.main_model_id or Path(args.main_gguf).stem
    elif args.main_model_id:
        request.main_model_id = args.main_model_id
    if args.least_censored_gguf:
        request.least_censored_gguf = args.least_censored_gguf
        request.least_censored_model_id = (
            args.least_censored_model_id or Path(args.least_censored_gguf).stem
        )
    elif args.least_censored_model_id:
        request.least_censored_model_id = args.least_censored_model_id


def _progress(args: argparse.Namespace) -> Callable[[str], None]:
    if args.json:
        return lambda message: print(message, file=sys.stderr)
    return print


def _check_export_dir(path: Path | None) -> None:
    if path is not None and path.exists() and not path.is_dir():
        raise PlotweaverError(f"--export-dir is not a directory: {path}")


def _check_references(paths: list[str]) -> None:
    for raw in paths:
        if not Path(raw).is_file():
            raise PlotweaverError(f"reference not found: {raw}")


def _run_request(args: argparse.Namespace, synopsis: str) -> BookRequest:
    if args.target_words < 1:
        raise PlotweaverError("--target-words must be positive")
    if args.scenes_per_chapter < 1:
        raise PlotweaverError("--scenes-per-chapter must be positive")
    return BookRequest(
        title=args.title,
        language=Language(args.language),
        synopsis=synopsis,
        genre=args.genre,
        target_words=args.target_words,
        chapter_count=None if args.chapters == 0 else args.chapters,
        scenes_per_chapter=args.scenes_per_chapter,
        dark_themes=bool(args.dark_themes),
        tier=ModelTier(args.tier),
        mode=BookMode(args.mode),
        reference_paths=list(args.reference or []),
        author=args.author,
        export_formats=_export_formats(args),
        sound_markup=bool(args.sound),
    )


def _brief_fail(args: argparse.Namespace, exc: BriefError) -> int:
    if args.json:
        _print_json(
            {
                "ok": False,
                "command": str(getattr(args, "command", "brief")),
                "error": str(exc),
                "code": 1,
                "errors": [
                    {"field": item.field, "code": item.code, "message": item.message()}
                    for item in exc.errors
                ],
            }
        )
        return 1
    print(str(exc), file=sys.stderr)
    return 1


def _read_brief_file(args: argparse.Namespace) -> BookBrief | None:
    if getattr(args, "brief", None) is None:
        return None
    if not args.brief.is_file():
        raise PlotweaverError(f"brief not found: {args.brief}")
    return parse_brief(args.brief.read_text(encoding="utf-8"))


def _brief_draft(args: argparse.Namespace) -> int:
    if not str(args.idea).strip():
        raise PlotweaverError("--idea is empty")
    if args.dry_run:
        actions = [
            "expand the notes into a book brief with the mock backend"
            if args.mock
            else "expand the notes into a book brief with the local model",
        ]
        payload: dict[str, Any] = {
            "ok": True,
            "command": "brief.draft",
            "dry_run": True,
            "code": 0,
            "language": args.language,
            "mock": bool(args.mock),
            "actions": actions,
        }
        lines = ["dry-run", *[f"action: {item}" for item in actions]]
        return _emit(args, payload, "\n".join(lines))
    brief = draft_book_brief(str(args.idea), str(args.language), _backend(bool(args.mock)))
    payload = {
        "ok": True,
        "command": "brief.draft",
        "dry_run": False,
        "code": 0,
        "brief": brief.to_dict(),
    }
    return _emit(args, payload, render_markdown(brief))


def _run(args: argparse.Namespace) -> int:
    exists = (args.project / "project.json").is_file()
    try:
        loaded = _read_brief_file(args)
    except BriefError as exc:
        return _brief_fail(args, exc)
    if args.synopsis is None and loaded is None and not exists:
        raise PlotweaverError(
            "--synopsis or --brief is required when the project does not exist yet"
        )
    _check_export_dir(args.export_dir)
    _check_references(list(args.reference or []))
    synopsis = ""
    if loaded is not None:
        synopsis = loaded.synopsis
    if args.synopsis is not None:
        if not args.synopsis.is_file():
            raise PlotweaverError(f"synopsis not found: {args.synopsis}")
        synopsis = args.synopsis.read_text(encoding="utf-8")
        if not synopsis.strip():
            raise PlotweaverError("synopsis is empty")
    if exists and args.synopsis is None:
        Project(args.project).request()
    formats = _export_formats(args)
    export_root = args.export_dir or (args.project / "export")
    _run_request(args, synopsis or "resume")
    if args.dry_run:
        actions = [
            "resume the project" if exists else "create the project",
            "generate the book with the mock backend"
            if args.mock
            else "generate the book with the local model",
            "write the export files, including book.vxbook",
        ]
        payload: dict[str, Any] = {
            "ok": True,
            "command": "run",
            "dry_run": True,
            "code": 0,
            "project": str(args.project.resolve()),
            "resume": exists,
            "mock": bool(args.mock),
            "actions": actions,
            "outputs": _output_paths(export_root, formats, sound=bool(args.sound)),
        }
        lines = ["dry-run", *[f"action: {item}" for item in actions]]
        lines.extend(f"output: {item}" for item in payload["outputs"])
        return _emit(args, payload, "\n".join(lines))
    request = _run_request(args, synopsis)
    if loaded is not None:
        apply_brief(request, loaded)
        if args.chapters:
            request.chapter_count = args.chapters
            loaded.chapter_count = args.chapters
            request.brief = loaded.to_dict()
    _apply_models(request, args)
    project = Project.open_or_create(args.project, request)
    if loaded is None and project.request_path.is_file() and args.synopsis is None:
        request = project.request()
        _apply_models(request, args)
    elif args.synopsis is not None:
        stored = project.request()
        request.synopsis = synopsis
        # Keep model paths already stored when the caller only resumes.
        if not request.main_gguf:
            request.main_gguf = stored.main_gguf
            request.main_model_id = stored.main_model_id
        if not request.least_censored_gguf:
            request.least_censored_gguf = stored.least_censored_gguf
            request.least_censored_model_id = stored.least_censored_model_id
    progress = _progress(args)
    if not args.mock:
        prepare_real_models(request, on_progress=progress)
    project.save_request(request)
    result = run_book(
        project,
        _backend(args.mock),
        yes=bool(args.yes),
        approve=bool(args.approve),
        on_progress=progress,
        export_to=args.export_dir,
    )
    outputs: list[str] = []
    if result.export_dir is not None:
        outputs = _output_paths(result.export_dir, formats, sound=bool(args.sound))
    payload = {
        "ok": True,
        "command": "run",
        "dry_run": False,
        "code": 0,
        "status": result.status,
        "gate": result.gate,
        "swaps": result.swaps,
        "refusals": result.refusals,
        "placeholders": result.placeholders,
        "rewrites": result.rewrites,
        "project": str(project.root.resolve()),
        "export_dir": str(result.export_dir.resolve()) if result.export_dir else None,
        "outputs": outputs,
    }
    text = f"status={result.status} gate={result.gate or '-'} swaps={result.swaps}"
    if result.export_dir is not None:
        text = f"{text}\n{result.export_dir}"
    return _emit(args, payload, text)


def _export(args: argparse.Namespace) -> int:
    if not (args.project / "project.json").is_file():
        raise PlotweaverError(f"project not found: {args.project}")
    _check_export_dir(args.export_dir)
    project = Project(args.project)
    request = project.request()
    outline = project.artefacts / "outline.json"
    if not outline.is_file():
        raise PlotweaverError("the project has no outline to export")
    formats = _export_formats(args)
    export_root = args.export_dir or project.export_dir
    if args.dry_run:
        actions = [
            "read the generated project",
            "write the export files, including book.vxbook",
        ]
        if args.sound:
            actions.append(
                "add sound markup with the mock backend"
                if args.mock
                else "add sound markup with the local model"
            )
        payload: dict[str, Any] = {
            "ok": True,
            "command": "export",
            "dry_run": True,
            "code": 0,
            "project": str(project.root.resolve()),
            "title": request.title,
            "actions": actions,
            "outputs": _output_paths(export_root, formats, sound=bool(args.sound)),
        }
        lines = ["dry-run", *[f"action: {item}" for item in actions]]
        lines.extend(f"output: {item}" for item in payload["outputs"])
        return _emit(args, payload, "\n".join(lines))
    directory = export_book(
        project,
        _backend(bool(args.mock)) if args.sound else None,
        formats=formats,
        sound=bool(args.sound),
        export_to=args.export_dir,
    )
    outputs = _output_paths(directory, formats, sound=bool(args.sound))
    payload = {
        "ok": True,
        "command": "export",
        "dry_run": False,
        "code": 0,
        "project": str(project.root.resolve()),
        "export_dir": str(directory.resolve()),
        "outputs": outputs,
    }
    return _emit(args, payload, "\n".join(outputs))


def _scenario_mars(args: argparse.Namespace) -> int:
    _check_export_dir(args.export_dir)
    if not args.mock and not args.main_gguf:
        raise PlotweaverError(
            "scenario-mars on a GPU needs --main-gguf. "
            "Use --mock to exercise the same path without a model."
        )
    formats = _export_formats(args)
    export_root = args.export_dir or (args.project / "export")
    if args.dry_run:
        mars_request()
        actions = [
            "create the Mars scenario project",
            "generate the short Russian story",
            "write the export files, including book.vxbook",
        ]
        payload: dict[str, Any] = {
            "ok": True,
            "command": "scenario-mars",
            "dry_run": True,
            "code": 0,
            "project": str(args.project.resolve()),
            "mock": bool(args.mock),
            "actions": actions,
            "outputs": _output_paths(export_root, formats, sound=bool(args.sound)),
        }
        lines = ["dry-run", *[f"action: {item}" for item in actions]]
        lines.extend(f"output: {item}" for item in payload["outputs"])
        return _emit(args, payload, "\n".join(lines))
    request = mars_request()
    request.main_gguf = args.main_gguf
    request.least_censored_gguf = args.least_censored_gguf
    if args.main_gguf:
        request.main_model_id = args.main_model_id or Path(args.main_gguf).stem
    elif args.main_model_id:
        request.main_model_id = args.main_model_id
    if args.least_censored_gguf:
        request.least_censored_model_id = (
            args.least_censored_model_id or Path(args.least_censored_gguf).stem
        )
    elif args.least_censored_model_id:
        request.least_censored_model_id = args.least_censored_model_id
    request.author = args.author
    request.export_formats = _export_formats(args)
    request.sound_markup = bool(args.sound)
    project = Project.open_or_create(args.project, request)
    project.save_request(request)
    progress = _progress(args)
    result = run_book(
        project,
        _backend(bool(args.mock)),
        yes=bool(args.yes),
        on_progress=progress,
        export_to=args.export_dir,
    )
    code = 0 if result.status == "completed" else 3
    published = result.export_dir or project.export_dir
    outputs = (
        _output_paths(published, formats, sound=bool(args.sound))
        if result.export_dir is not None
        else []
    )
    body: dict[str, Any] = {
        "ok": code == 0,
        "command": "scenario-mars",
        "dry_run": False,
        "code": code,
        "status": result.status,
        "swaps": result.swaps,
        "project": str(project.root.resolve()),
        "export_dir": str(result.export_dir.resolve()) if result.export_dir else None,
        "outputs": outputs,
    }
    text = f"status={result.status} swaps={result.swaps}"
    if result.export_dir is not None:
        text = f"{text}\n{result.export_dir / 'book.vxbook'}"
    return _emit(args, body, text)


def _bakeoff(args: argparse.Namespace) -> int:
    archive = run_bakeoff(
        args.results,
        mock=bool(args.mock),
        limit=int(args.limit),
        allow_other_license=bool(args.allow_other_license),
    )
    print(archive)
    return 0


def _gui(args: argparse.Namespace) -> int:
    os.environ.setdefault("PLOTWEAVER_NO_UPDATE_CHECK", "1")
    if not args.mock and not args.selftest:
        require_supported_gpu()
    if args.selftest:
        os.environ["PLOTWEAVER_UI_PROJECT"] = tempfile.mkdtemp(prefix="plotweaver-selftest-")
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    splash = Splash()
    splash.show()
    app.processEvents()
    window = MainWindow(mock=bool(args.mock or args.selftest))
    window.show()
    if args.selftest:
        splash.close()
        window.run_selftest()
        return 0
    QTimer.singleShot(900, splash.close)
    return int(app.exec())
