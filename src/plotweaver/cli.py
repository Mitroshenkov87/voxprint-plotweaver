"""Command line: run a book, open the window, bake off models, or run the Mars scenario."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from plotweaver.appinfo import APP_NAME, version_label
from plotweaver.bakeoff import run_bakeoff
from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.errors import GpuUnsupported, PlotweaverError
from plotweaver.hardware import require_supported_gpu, vram_budget_gb, vram_headroom_gb
from plotweaver.llama_release import ensure_llama_server
from plotweaver.llama_server import LlamaServer
from plotweaver.llm import LLMBackend, MockBackend
from plotweaver.runner import run_book
from plotweaver.scenarios import mars_request
from plotweaver.store import Project
from plotweaver.ui.window import MainWindow


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="plotweaver", description=APP_NAME)
    sub = parser.add_subparsers(dest="command", required=True)

    version = sub.add_parser("version", help="Print the version and codename.")
    version.set_defaults(func=_version)

    doctor = sub.add_parser("doctor", help="Show the GPU check.")
    doctor.add_argument("--mock", action="store_true")
    doctor.set_defaults(func=_doctor)

    run = sub.add_parser("run", help="Write or resume one book.")
    _add_book_args(run)
    run.set_defaults(func=_run)

    scenario = sub.add_parser(
        "scenario-mars",
        help="Write the short Russian Mars story and the Audiobook Builder export.",
    )
    scenario.add_argument("--project", type=Path, default=Path("out/mars-e2e/project"))
    scenario.add_argument("--export-dir", type=Path, default=Path("out/mars-e2e"))
    scenario.add_argument("--mock", action="store_true")
    scenario.add_argument("--yes", action="store_true", help="Skip bible and outline approval.")
    scenario.add_argument("--main-gguf", default="")
    scenario.add_argument("--low-refusal-gguf", default="")
    scenario.add_argument("--main-model-id", default="")
    scenario.add_argument("--low-refusal-model-id", default="")
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

    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GpuUnsupported as exc:
        print(exc, file=sys.stderr)
        return 2
    except PlotweaverError as exc:
        print(exc, file=sys.stderr)
        return 1


def _add_book_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--synopsis", type=Path)
    parser.add_argument("--title", default="Untitled")
    parser.add_argument("--language", choices=["ru", "en"], default="ru")
    parser.add_argument("--genre", default="")
    parser.add_argument("--target-words", type=int, default=80_000)
    parser.add_argument("--chapters", type=int, default=0)
    parser.add_argument("--scenes-per-chapter", type=int, default=2)
    parser.add_argument("--dark-themes", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--tier", choices=["standard", "low-refusal"], default="standard")
    parser.add_argument("--mode", choices=["autopilot", "copilot", "manual"], default="autopilot")
    parser.add_argument("--reference", action="append", default=[])
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--yes", action="store_true", help="Do not stop for approval.")
    parser.add_argument(
        "--approve", action="store_true", help="Clear the gate the book is waiting on."
    )
    parser.add_argument("--export-dir", type=Path)
    parser.add_argument("--main-gguf", default="")
    parser.add_argument("--low-refusal-gguf", default="")
    parser.add_argument("--main-model-id", default="")
    parser.add_argument("--low-refusal-model-id", default="")


def _version(_args: argparse.Namespace) -> int:
    print(f"{APP_NAME} {version_label()}")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    print(f"{APP_NAME} {version_label()}")
    if args.mock:
        print("Mock mode: the GPU check is skipped.")
        return 0
    info = require_supported_gpu()
    budget = vram_budget_gb(info.free_gb, info.total_gb)
    print(
        f"{info.name}: compute {info.compute_cap}, "
        f"VRAM {info.free_gb:.1f} of {info.total_gb:.1f} GB free, "
        f"budget {budget:.1f} GB (headroom {vram_headroom_gb(info.total_gb):.1f} GB)."
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
    if args.low_refusal_gguf:
        request.low_refusal_gguf = args.low_refusal_gguf
        request.low_refusal_model_id = args.low_refusal_model_id or Path(args.low_refusal_gguf).stem
    elif args.low_refusal_model_id:
        request.low_refusal_model_id = args.low_refusal_model_id
    if not args.mock and not request.main_gguf:
        raise PlotweaverError(
            "A real run needs --main-gguf PATH. "
            "scripts/bakeoff.sh downloads the candidate weights on the GPU machine."
        )


def _run(args: argparse.Namespace) -> int:
    if args.synopsis is None and not (args.project / "project.json").is_file():
        raise PlotweaverError("--synopsis is required when the project does not exist yet")
    synopsis = ""
    if args.synopsis is not None:
        synopsis = args.synopsis.read_text(encoding="utf-8")
    request = BookRequest(
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
    )
    _apply_models(request, args)
    project = Project.open_or_create(args.project, request)
    if args.synopsis is not None:
        stored = project.request()
        request.synopsis = synopsis
        # Keep model paths already stored when the caller only resumes.
        if not request.main_gguf:
            request.main_gguf = stored.main_gguf
            request.main_model_id = stored.main_model_id
        if not request.low_refusal_gguf:
            request.low_refusal_gguf = stored.low_refusal_gguf
            request.low_refusal_model_id = stored.low_refusal_model_id
        project.save_request(request)
    result = run_book(
        project,
        _backend(args.mock),
        yes=bool(args.yes),
        approve=bool(args.approve),
        on_progress=print,
        export_to=args.export_dir,
    )
    print(f"status={result.status} gate={result.gate or '-'} swaps={result.swaps}")
    if result.export_dir is not None:
        print(result.export_dir)
    return 0


def _scenario_mars(args: argparse.Namespace) -> int:
    request = mars_request()
    request.main_gguf = args.main_gguf
    request.low_refusal_gguf = args.low_refusal_gguf
    if args.main_gguf:
        request.main_model_id = args.main_model_id or Path(args.main_gguf).stem
    elif args.main_model_id:
        request.main_model_id = args.main_model_id
    if args.low_refusal_gguf:
        request.low_refusal_model_id = args.low_refusal_model_id or Path(args.low_refusal_gguf).stem
    elif args.low_refusal_model_id:
        request.low_refusal_model_id = args.low_refusal_model_id
    if not args.mock and not request.main_gguf:
        raise PlotweaverError(
            "scenario-mars on a GPU needs --main-gguf. "
            "Use --mock to exercise the same path without a model."
        )
    project = Project.open_or_create(args.project, request)
    project.save_request(request)
    result = run_book(
        project,
        _backend(bool(args.mock)),
        yes=bool(args.yes),
        on_progress=print,
        export_to=args.export_dir,
    )
    print(f"status={result.status} swaps={result.swaps}")
    if result.export_dir is not None:
        print(result.export_dir / "audiobook" / "speaker-marks.txt")
    return 0 if result.status == "completed" else 3


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
    window = MainWindow(mock=bool(args.mock or args.selftest))
    window.show()
    if args.selftest:
        window.run_selftest()
        return 0
    return int(app.exec())
