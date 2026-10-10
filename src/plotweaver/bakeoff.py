"""Headless Russian bake-off: synopses, one model at a time, then a blind packet.

The GPU machine runs every candidate. CI runs the same code with the mock backend
on a slice of the set (--mock --limit 1) plus the two-pass dark path.
"""

from __future__ import annotations

import shutil
import tarfile
import time
from dataclasses import dataclass
from pathlib import Path

from plotweaver.atomic import read_json, write_json
from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.errors import PlotweaverError
from plotweaver.hardware import query_gpu, require_supported_gpu
from plotweaver.jsontext import parse_json_object
from plotweaver.llama_release import ensure_llama_server
from plotweaver.llama_server import LlamaServer
from plotweaver.llm import ChatMessage, LLMBackend, MockBackend, ModelSpec
from plotweaver.paths import repo_root
from plotweaver.prompts import judge_prompt, system_message
from plotweaver.registry import RegistryEntry, download_model, load_registry
from plotweaver.runner import run_book
from plotweaver.store import Project


@dataclass
class Synopsis:
    id: str
    title: str
    genre: str
    dark: bool
    body: str


def synopses_dir() -> Path:
    return repo_root() / "bakeoff" / "synopses"


def registry_path() -> Path:
    return repo_root() / "bakeoff" / "models.toml"


def load_synopses() -> list[Synopsis]:
    found: list[Synopsis] = []
    for path in sorted(synopses_dir().glob("*.md")):
        meta, body = _front_matter(path.read_text(encoding="utf-8"))
        found.append(
            Synopsis(
                id=str(meta.get("id") or path.stem),
                title=str(meta.get("title") or path.stem),
                genre=str(meta.get("genre") or ""),
                dark=str(meta.get("dark") or "").lower() == "true",
                body=body.strip(),
            )
        )
    if len(found) != 10:
        raise PlotweaverError(f"expected 10 synopses in {synopses_dir()}, found {len(found)}")
    return found


def _front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text
    meta: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, text[end + 5 :]


def run_bakeoff(
    results: Path,
    *,
    mock: bool,
    limit: int = 0,
    allow_other_license: bool = False,
) -> Path:
    """Run the comparison and return the results archive path."""
    if not mock:
        require_supported_gpu()
    stories = load_synopses()
    if limit > 0:
        stories = stories[:limit]
    results.mkdir(parents=True, exist_ok=True)
    if mock:
        main_spec = ModelSpec("mock-main", Path("mock-main.gguf"))
        low_spec = ModelSpec("mock-low", Path("mock-low.gguf"))
        specs = [main_spec, low_spec]
        backend: LLMBackend = MockBackend()
    else:
        specs = _real_specs(allow_other_license)
        backend = LlamaServer(ensure_llama_server())
    solo_specs, low_specs, main_for_pass2 = _split_roles(specs, mock)
    for spec in solo_specs:
        for story in stories:
            _one_book(
                results / "solo" / spec.id / story.id,
                story,
                backend,
                main=spec,
                low=spec,
                dark=False,
                chapters=2 if mock else 3,
            )
    if main_for_pass2 is not None:
        for low in low_specs:
            for story in stories:
                _one_book(
                    results / "two-pass" / f"{main_for_pass2.id}__{low.id}" / story.id,
                    story,
                    backend,
                    main=main_for_pass2,
                    low=low,
                    dark=True,
                    chapters=2 if mock else 3,
                )
    if main_for_pass2 is not None and not mock:
        backend.load(main_for_pass2)
    _judge(results, backend)
    _blind(results)
    archive = results / "bakeoff-results.tar.gz"
    _tar(results, archive)
    return archive


def _split_roles(
    specs: list[ModelSpec], mock: bool
) -> tuple[list[ModelSpec], list[ModelSpec], ModelSpec | None]:
    if mock:
        main = specs[0]
        low = specs[1]
        return [main, low], [low], main
    # Real ids from the registry are attached via spec.id. The download step stored role
    # in a sidecar next to the file name: we re-read the registry.
    entries = [entry for entry in load_registry(registry_path()) if _matches(entry, specs)]
    low_ids = {entry.id for entry in entries if entry.role == "low-refusal"}
    main_ids = [entry.id for entry in entries if entry.role == "main"]
    low_specs = [spec for spec in specs if spec.id in low_ids]
    chosen = next((spec for spec in specs if spec.id == (main_ids[0] if main_ids else "")), None)
    return list(specs), low_specs, chosen


def _matches(entry: RegistryEntry, specs: list[ModelSpec]) -> bool:
    return any(spec.id == entry.id for spec in specs)


def _real_specs(allow_other: bool) -> list[ModelSpec]:
    gpu = query_gpu()
    free = gpu.free_gb if gpu else 0.0
    specs: list[ModelSpec] = []
    for entry in load_registry(registry_path()):
        if entry.min_vram_gb > free + 0.5:
            print(f"skip {entry.id}: needs {entry.min_vram_gb} GB, {free:.1f} GB free")
            continue
        path = download_model(entry, allow_other=allow_other)
        specs.append(
            ModelSpec(
                id=entry.id,
                path=path,
                context=entry.context,
                license=entry.license,
                moe=entry.moe,
            )
        )
    if not specs:
        raise PlotweaverError("no candidate model fits the free VRAM")
    return specs


def _one_book(
    folder: Path,
    story: Synopsis,
    backend: LLMBackend,
    *,
    main: ModelSpec,
    low: ModelSpec,
    dark: bool,
    chapters: int,
) -> None:
    metrics_path = folder / "metrics.json"
    if metrics_path.is_file():
        existing = read_json(metrics_path)
        if isinstance(existing, dict) and existing.get("status") == "completed":
            return
    project_dir = folder / "project"
    if project_dir.exists():
        shutil.rmtree(project_dir)
    request = BookRequest(
        title=story.title,
        language=Language.RU,
        synopsis=story.body,
        genre=story.genre,
        target_words=4200 if chapters == 3 else 1600,
        chapter_count=chapters,
        scenes_per_chapter=2,
        dark_themes=dark,
        tier=ModelTier.LOW_REFUSAL if main.id == low.id and dark else ModelTier.STANDARD,
        mode=BookMode.AUTOPILOT,
        main_model_id=main.id,
        low_refusal_model_id=low.id,
        main_gguf=str(main.path) if main.path.suffix == ".gguf" and main.path.is_file() else "",
        low_refusal_gguf=str(low.path) if low.path.suffix == ".gguf" and low.path.is_file() else "",
    )
    project = Project.open_or_create(project_dir, request)
    started = time.monotonic()
    result = run_book(project, backend, yes=True, on_progress=print, export_to=folder / "export")
    elapsed = time.monotonic() - started
    write_json(
        metrics_path,
        {
            "status": result.status,
            "model_id": main.id,
            "low_refusal_model_id": low.id,
            "synopsis_id": story.id,
            "dark_themes": dark,
            "genre": story.genre,
            "source_dark": story.dark,
            "swaps": result.swaps,
            "refusals": result.refusals,
            "placeholders": result.placeholders,
            "rewrites": result.rewrites,
            "seconds": round(elapsed, 3),
        },
    )


def _judge(results: Path, backend: LLMBackend) -> None:
    scores_dir = results / "judge"
    scores_dir.mkdir(parents=True, exist_ok=True)
    scores: list[dict[str, object]] = []
    for metrics_path in sorted(results.glob("*/*/*/metrics.json")) + sorted(
        results.glob("*/*/metrics.json")
    ):
        book = metrics_path.parent / "export" / "book.md"
        if not book.is_file():
            book = metrics_path.parent / "export" / "audiobook" / "book.md"
        if not book.is_file():
            continue
        packet = book.read_text(encoding="utf-8")[:6000]
        completion = backend.complete(
            [ChatMessage("system", system_message()), ChatMessage("user", judge_prompt(packet))],
            temperature=0.2,
            max_tokens=512,
            json_mode=True,
        )
        parsed = parse_json_object(completion.text) or {}
        parsed["book"] = str(book)
        scores.append(parsed)
    write_json(scores_dir / "scores.json", {"scores": scores})


def _blind(results: Path) -> None:
    """A reading folder with the model names removed, and a key kept beside it."""
    reader = results / "blind-packet" / "reader"
    if reader.exists():
        shutil.rmtree(reader)
    reader.mkdir(parents=True)
    key: dict[str, str] = {}
    letter = ord("A")
    for metrics_path in sorted(results.glob("solo/*/*/metrics.json")):
        model_id = metrics_path.parent.parent.name
        code = f"model-{chr(letter)}"
        letter += 1
        if model_id not in key.values():
            key[code] = model_id
        else:
            code = next(name for name, value in key.items() if value == model_id)
        story_id = metrics_path.parent.name
        source = metrics_path.parent / "export" / "book.md"
        if not source.is_file():
            source = metrics_path.parent / "export" / "audiobook" / "book.md"
        if source.is_file():
            target = reader / code
            target.mkdir(exist_ok=True)
            shutil.copy2(source, target / f"{story_id}.md")
    instructions = (
        "# Blind reading\n\n"
        "Read the folders in any order. Do not open assignment-key.json until you have "
        "written notes. Score ordinary scenes and dark scenes separately, and mark any "
        "chapter whose voice seems to change. The key is one directory above this folder.\n"
    )
    (reader / "README.md").write_text(instructions, encoding="utf-8")
    write_json(results / "assignment-key.json", key)


def _tar(results: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz") as bundle:
        for path in results.rglob("*"):
            if path == archive or not path.is_file():
                continue
            bundle.add(path, arcname=str(path.relative_to(results)))
