"""Synopsis to exported book. Checkpointed after every step. One large model at a time.

Dark-themes OFF: the main model plans, drafts, checks, and proofreads. No swap.
Dark-themes ON: pass 1 leaves dark or refused scenes as placeholders. Pass 2 loads the
least-censored model once, fills every placeholder, and proofreads while that model is loaded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plotweaver.atomic import write_json
from plotweaver.brief import BookBrief, attach_context, brief_from_payload
from plotweaver.checks import chapter_problems, is_refusal, is_sanitised
from plotweaver.domain import BookMode, BookRequest, Gender, ModelTier, parse_gender
from plotweaver.errors import ModelOutputError, PlotweaverError, assert_never
from plotweaver.export import (
    RenderedChapter,
    RenderedParagraph,
    publish_exports,
    write_bundle,
)
from plotweaver.gpu_lock import gpu_job
from plotweaver.hardware import ThermalGuard
from plotweaver.jsontext import parse_json_object
from plotweaver.llm import ChatMessage, LLMBackend, ModelSpec, complete_json
from plotweaver.prompts import (
    beats_prompt,
    bible_prompt,
    brief_draft_prompt,
    draft_prompt,
    extract_prompt,
    fill_prompt,
    outline_prompt,
    proofread_prompt,
    rewrite_prompt,
    style_prompt,
    system_message,
)
from plotweaver.references import compare_texts, measure_style, read_reference
from plotweaver.sound import add_sound
from plotweaver.store import Project
from plotweaver.textio import read_text
from plotweaver.textutil import prepare_prose
from plotweaver.vxbook import build_character_speakers, emitted_chapter_id, even_utc_now, name_key

Progress = Any


@dataclass
class RunResult:
    """What a book run finished with: status, gate, and the export counts."""

    status: str
    gate: str | None
    export_dir: Path | None
    swaps: int
    refusals: int
    placeholders: int
    rewrites: int


def draft_book_brief(idea: str, language: str, backend: LLMBackend) -> BookBrief:
    """Expand loose notes into a full brief. The caller reviews it before writing."""
    payload = complete_json(
        backend,
        [
            ChatMessage("system", system_message()),
            ChatMessage("user", brief_draft_prompt(idea, language)),
        ],
        temperature=0.3,
        max_tokens=2048,
    )
    return brief_from_payload(payload, idea=idea, language=language)


def run_book(
    project: Project,
    backend: LLMBackend,
    *,
    yes: bool = False,
    approve: bool = False,
    on_progress: Progress | None = None,
    export_to: Path | None = None,
    thermal: ThermalGuard | None = None,
) -> RunResult:
    """Run or resume a book. ``yes`` skips gates. ``approve`` clears the current gate."""
    if approve and not yes:
        waiting = project.status().get("gate")
        if isinstance(waiting, str) and waiting:
            project.approve_gate(waiting)
    engine = _Engine(
        project,
        backend,
        yes=yes,
        on_progress=on_progress or (lambda _message: None),
        export_to=export_to,
        thermal=thermal or ThermalGuard(),
    )
    job = f"book:{project.request().title}"
    with gpu_job(job, eta_s=10 * 3600):
        return engine.run()


def export_book(
    project: Project,
    backend: LLMBackend | None,
    *,
    formats: list[str],
    sound: bool,
    export_to: Path | None,
) -> Path:
    """Write the export bundle for a project that already has an outline.

    This does not draft. Sound markup is the only step that calls a model.
    """
    request = project.request()
    request.export_formats = list(formats)
    request.sound_markup = sound
    if not (project.artefacts / "outline.json").is_file():
        raise PlotweaverError("the project has no outline to export")
    outline = _obj(project.read_artefact("outline.json"))
    chapters = [item for item in _list(outline.get("chapters")) if isinstance(item, dict)]
    if not chapters:
        raise PlotweaverError("the outline has no chapters")
    if sound and backend is None:
        raise PlotweaverError("sound markup needs a model")
    if not request.created:
        request.created = even_utc_now()
    project.save_request(request)
    overlap_path = project.artefacts / "overlap.json"
    overlap = _obj(project.read_artefact("overlap.json")) if overlap_path.is_file() else {}
    rendered = _render(project, request, chapters)
    directory = project.export_dir
    write_bundle(
        directory,
        request.title,
        request.language.value,
        rendered,
        overlap,
        author=request.author,
        genre=request.genre,
        synopsis=request.synopsis,
        formats=request.export_formats,
        created=request.created,
        speakers=build_character_speakers(_character_rows(project)),
    )
    if sound:
        assert backend is not None
        add_sound(directory / "book.vxbook", directory / "book.sound.vxbook", backend)
    if export_to is not None:
        publish_exports(directory, export_to)
        return export_to
    return directory


class _Engine:
    def __init__(
        self,
        project: Project,
        backend: LLMBackend,
        *,
        yes: bool,
        on_progress: Progress,
        export_to: Path | None,
        thermal: ThermalGuard,
    ) -> None:
        self.project = project
        self.backend = backend
        self.yes = yes
        self.on_progress = on_progress
        self.export_to = export_to
        self.thermal = thermal
        self.ck = project.checkpoint()
        self.resident: str | None = None
        self.swaps = 0
        self.refusals = 0
        self.placeholders = 0
        self.rewrites = 0

    def run(self) -> RunResult:
        try:
            return self._run()
        except BaseException:
            self.backend.unload()
            self.resident = None
            raise

    def _run(self) -> RunResult:
        request = attach_context(self.project.request())
        main, low = _specs(request)
        self._use(main)
        self._intake(request)
        if not self.ck.done("bible"):
            self._log("story bible")
            bible = complete_json(
                self.backend,
                _messages(bible_prompt(request)),
                temperature=0.4,
                max_tokens=2048,
            )
            self.project.write_artefact("bible.json", bible)
            characters = bible.get("characters")
            if isinstance(characters, list):
                with self.project.canon() as canon:
                    canon.seed_characters(
                        [item for item in characters if isinstance(item, dict)],
                        "bible",
                    )
            self.ck.mark("bible")
        if self._wait("bible"):
            return self._waiting("bible")
        if not self.ck.done("outline"):
            self._log("outline")
            bible = _obj(self.project.read_artefact("bible.json"))
            outline = complete_json(
                self.backend,
                _messages(outline_prompt(request, bible)),
                temperature=0.4,
                max_tokens=2048,
            )
            chapters = outline.get("chapters")
            if not isinstance(chapters, list) or not chapters:
                raise ModelOutputError("the outline has no chapters")
            rows = [item for item in chapters if isinstance(item, dict)]
            _normalise_chapter_ids(rows)
            outline["chapters"] = rows
            self.project.write_artefact("outline.json", outline)
            self.ck.mark("outline")
        if self._wait("outline"):
            return self._waiting("outline")
        outline = _obj(self.project.read_artefact("outline.json"))
        chapters = [item for item in _list(outline.get("chapters")) if isinstance(item, dict)]
        if _normalise_chapter_ids(chapters):
            outline["chapters"] = chapters
            self.project.write_artefact("outline.json", outline)
        for index, chapter in enumerate(chapters, start=1):
            chapter_id = emitted_chapter_id(str(chapter.get("id") or ""), index, len(chapters))
            chapter["id"] = chapter_id
            scene_gate = self._chapter(request, chapter, index)
            if scene_gate is not None:
                return self._waiting(scene_gate)
            match request.mode:
                case BookMode.AUTOPILOT:
                    continue
                case BookMode.COPILOT | BookMode.MANUAL:
                    chapter_gate = f"chapter:{chapter_id}"
                    if self._wait(chapter_gate):
                        return self._waiting(chapter_gate)
                case _ as unreachable:
                    assert_never(unreachable)
        if request.dark_themes:
            self._pass2(request, low, chapters)
        else:
            self._use(main)
            self._proof_all(request, chapters)
        overlap = self._overlap(request)
        export_dir = self._export(request, chapters, overlap)
        self.project.set_status("completed", None)
        self._write_report(export_dir)
        self.backend.unload()
        self.resident = None
        return RunResult(
            "completed",
            None,
            export_dir,
            self.swaps,
            self.refusals,
            self.placeholders,
            self.rewrites,
        )

    def _chapter(self, request: BookRequest, chapter: dict[str, Any], index: int) -> str | None:
        chapter_id = emitted_chapter_id(str(chapter.get("id") or ""), index, max(index, 1))
        bible = _obj(self.project.read_artefact("bible.json"))
        if not self.ck.done(f"beats:{chapter_id}"):
            self._log(f"beats {chapter_id}")
            self.backend.prepare_batch()
            beats = complete_json(
                self.backend,
                _messages(beats_prompt(request, bible, chapter, index)),
                temperature=0.4,
                max_tokens=2048,
            )
            scene_rows = [item for item in _list(beats.get("scenes")) if isinstance(item, dict)]
            _bind_scene_ids(chapter_id, scene_rows)
            beats["scenes"] = scene_rows
            self.project.write_artefact(f"beats/{chapter_id}.json", beats)
            self.ck.mark(f"beats:{chapter_id}")
        beats = _obj(self.project.read_artefact(f"beats/{chapter_id}.json"))
        scenes = [item for item in _list(beats.get("scenes")) if isinstance(item, dict)]
        if _bind_scene_ids(chapter_id, scenes):
            beats["scenes"] = scenes
            self.project.write_artefact(f"beats/{chapter_id}.json", beats)
        for scene_index, scene in enumerate(scenes):
            scene_id = str(scene.get("id") or f"{chapter_id}-sc{scene_index + 1:02d}")
            scene["id"] = scene_id
            previous = scenes[scene_index - 1]["id"] if scene_index else ""
            nxt = scenes[scene_index + 1].get("id", "") if scene_index + 1 < len(scenes) else ""
            self._draft_scene(request, bible, chapter, scene, str(previous), str(nxt))
            if request.mode is BookMode.MANUAL:
                scene_gate = f"scene:{scene_id}"
                if self._wait(scene_gate):
                    return scene_gate
        self._check_chapter(request, chapter_id, scenes)
        return None

    def _draft_scene(
        self,
        request: BookRequest,
        bible: dict[str, Any],
        chapter: dict[str, Any],
        scene: dict[str, Any],
        previous_id: str,
        next_id: str,
    ) -> None:
        scene_id = str(scene["id"])
        step = f"draft:{scene_id}"
        if self.ck.done(step):
            return
        if request.dark_themes and bool(scene.get("dark")):
            self._write_placeholder(
                scene, str(chapter.get("id") or ""), previous_id, next_id, "preflagged"
            )
            self.ck.mark(step)
            return
        self._log(f"draft {scene_id}")
        self.backend.prepare_batch()
        self.thermal.pause_after_batch(log=self._log)
        style = _style_card(self.project)
        tail = _tail(self.project, previous_id)
        prompt = draft_prompt(request, bible, chapter, scene, tail, style)
        completion = self.backend.complete(
            _messages(prompt),
            temperature=0.9,
            max_tokens=_max_tokens(request),
            json_mode=True,
        )
        self.project.write_raw(step, completion.text)
        refused = is_refusal(completion.text) and parse_json_object(completion.text) is None
        sanitised = bool(scene.get("dark")) and is_sanitised(completion.text)
        if request.dark_themes and (refused or sanitised):
            self.refusals += 1
            self._write_placeholder(
                scene, str(chapter.get("id") or ""), previous_id, next_id, "refusal"
            )
            self.ck.mark(step)
            return
        if refused:
            self.refusals += 1
            paragraphs = [
                {"text": completion.text.strip(), "speaker": "NARRATOR", "gender": "unspecified"}
            ]
        else:
            parsed = parse_json_object(completion.text)
            if parsed is None:
                parsed = complete_json(
                    self.backend,
                    _messages(prompt),
                    temperature=0.2,
                    max_tokens=_max_tokens(request),
                )
            paragraphs = _paragraphs(parsed)
        self._save_prose(scene, str(chapter.get("id") or ""), paragraphs)
        self.ck.mark(step)

    def _check_chapter(
        self,
        request: BookRequest,
        chapter_id: str,
        scenes: list[dict[str, Any]],
    ) -> None:
        step = f"check:{chapter_id}"
        if self.ck.done(step):
            return
        prose_scenes = []
        flat: list[dict[str, str]] = []
        for scene in scenes:
            stored = _obj(self.project.read_artefact(f"scenes/{scene['id']}.json"))
            if stored.get("kind") == "placeholder":
                continue
            prose_scenes.append(stored)
            flat.extend(_paragraph_dicts(stored))
        text = "\n\n".join(item["text"] for item in flat)
        problems = chapter_problems(text)
        if problems and flat:
            self._log(f"one rewrite for {chapter_id}")
            rewritten = complete_json(
                self.backend,
                _messages(rewrite_prompt(request, text, problems)),
                temperature=0.4,
                max_tokens=_max_tokens(request),
            )
            new_paragraphs = _paragraphs(rewritten)
            if len(new_paragraphs) == len(flat):
                cursor = 0
                for stored in prose_scenes:
                    count = len(_paragraph_dicts(stored))
                    stored["paragraphs"] = new_paragraphs[cursor : cursor + count]
                    cursor += count
                    self.project.write_artefact(f"scenes/{stored['scene_id']}.json", stored)
            self.rewrites += 1
        extract = complete_json(
            self.backend,
            _messages(extract_prompt(request, chapter_id, text)),
            temperature=0.2,
            max_tokens=1024,
        )
        with self.project.canon() as canon:
            canon.commit_extraction(chapter_id, extract)
        self.ck.mark(step)

    def _pass2(
        self,
        request: BookRequest,
        low: ModelSpec,
        chapters: list[dict[str, Any]],
    ) -> None:
        self._use(low)
        for chapter in chapters:
            beats = _obj(self.project.read_artefact(f"beats/{chapter.get('id')}.json"))
            scenes = [item for item in _list(beats.get("scenes")) if isinstance(item, dict)]
            for scene in scenes:
                scene_id = str(scene.get("id"))
                path = f"scenes/{scene_id}.json"
                stored = _obj(self.project.read_artefact(path))
                if stored.get("kind") != "placeholder" or self.ck.done(f"fill:{scene_id}"):
                    continue
                self._log(f"fill {scene_id}")
                self.backend.prepare_batch()
                bible = _obj(self.project.read_artefact("bible.json"))
                prev_text = _scene_text(self.project, str(stored.get("prev_scene_id") or ""))
                next_text = _scene_text(self.project, str(stored.get("next_scene_id") or ""))
                filled = complete_json(
                    self.backend,
                    _messages(fill_prompt(request, bible, stored, prev_text, next_text)),
                    temperature=0.9,
                    max_tokens=_max_tokens(request),
                )
                stored["kind"] = "prose"
                stored["paragraphs"] = _paragraphs(filled)
                self.project.write_artefact(path, stored)
                self.ck.mark(f"fill:{scene_id}")
        self._proof_all(request, chapters)

    def _proof_all(self, request: BookRequest, chapters: list[dict[str, Any]]) -> None:
        for chapter in chapters:
            beats = _obj(self.project.read_artefact(f"beats/{chapter.get('id')}.json"))
            for scene in _list(beats.get("scenes")):
                if not isinstance(scene, dict):
                    continue
                scene_id = str(scene.get("id"))
                if self.ck.done(f"proof:{scene_id}"):
                    continue
                stored = _obj(self.project.read_artefact(f"scenes/{scene_id}.json"))
                if stored.get("kind") == "placeholder":
                    self.ck.mark(f"proof:{scene_id}")
                    continue
                original = _paragraph_dicts(stored)
                text = "\n\n".join(item["text"] for item in original)
                self._log(f"proofread {scene_id}")
                revised = complete_json(
                    self.backend,
                    _messages(
                        proofread_prompt(request, str(chapter.get("title") or scene_id), text)
                    ),
                    temperature=0.2,
                    max_tokens=_max_tokens(request),
                )
                updated = _paragraphs(revised)
                if len(updated) == len(original):
                    stored["paragraphs"] = updated
                    self.project.write_artefact(f"scenes/{scene_id}.json", stored)
                self.ck.mark(f"proof:{scene_id}")

    def _overlap(self, request: BookRequest) -> dict[str, object]:
        folder = self.project.root / "references"
        files = sorted(folder.glob("*.txt")) if folder.is_dir() else []
        if not files:
            return {"attached": False, "flagged": False, "hits": [], "note": "No reference books."}
        if self.ck.done("overlap"):
            return _obj(self.project.read_artefact("overlap.json"))
        generated = _book_text(self.project)
        report = None
        for ref in files:
            found = compare_texts(generated, read_text(ref))
            if report is None or found.flagged:
                report = found
            if found.flagged:
                break
        assert report is not None
        if report.flagged and not self.ck.done("overlap-rewrite"):
            problems = [f"{hit.kind}: {hit.excerpt}" for hit in report.hits]
            rewritten = complete_json(
                self.backend,
                _messages(rewrite_prompt(request, generated[:8000], problems)),
                temperature=0.4,
                max_tokens=_max_tokens(request),
            )
            # One targeted rewrite. We keep it on the first prose scene if the shape matches
            # that scene; otherwise the report still records the overlap.
            self._apply_overlap_rewrite(rewritten)
            self.rewrites += 1
            self.ck.mark("overlap-rewrite")
        payload = report.to_json()
        self.project.write_artefact("overlap.json", payload)
        self.ck.mark("overlap")
        return payload

    def _apply_overlap_rewrite(self, rewritten: dict[str, object]) -> None:
        outline = _obj(self.project.read_artefact("outline.json"))
        chapters = [item for item in _list(outline.get("chapters")) if isinstance(item, dict)]
        if not chapters:
            return
        beats = _obj(self.project.read_artefact(f"beats/{chapters[0].get('id')}.json"))
        scenes = [item for item in _list(beats.get("scenes")) if isinstance(item, dict)]
        if not scenes:
            return
        scene_id = str(scenes[0].get("id"))
        stored = _obj(self.project.read_artefact(f"scenes/{scene_id}.json"))
        original = _paragraph_dicts(stored)
        updated = _paragraphs(rewritten)
        if len(updated) == len(original):
            stored["paragraphs"] = updated
            self.project.write_artefact(f"scenes/{scene_id}.json", stored)

    def _export(
        self,
        request: BookRequest,
        chapters: list[dict[str, Any]],
        overlap: dict[str, object],
    ) -> Path:
        if not request.created:
            request.created = even_utc_now()
            self.project.save_request(request)
        rendered = _render(self.project, request, chapters)
        directory = self.project.export_dir
        write_bundle(
            directory,
            request.title,
            request.language.value,
            rendered,
            overlap,
            author=request.author,
            genre=request.genre,
            synopsis=request.synopsis,
            formats=request.export_formats,
            created=request.created,
            speakers=build_character_speakers(_character_rows(self.project)),
        )
        if request.sound_markup:
            self._log("sound markup")
            add_sound(
                directory / "book.vxbook",
                directory / "book.sound.vxbook",
                self.backend,
            )
        if self.export_to is not None:
            publish_exports(directory, self.export_to)
            return self.export_to
        return directory

    def _intake(self, request: BookRequest) -> None:
        if self.ck.done("intake"):
            return
        self._log("intake")
        copied: list[str] = []
        measured: list[str] = []
        for raw in request.reference_paths:
            path = Path(raw)
            text = read_reference(path)
            slug = path.stem
            target = self.project.root / "references" / f"{slug}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
            stats = measure_style(text)
            measured.append(f"{slug}: {stats}")
            copied.append(slug)
        self.project.write_artefact(
            "intake.json",
            {"references": copied, "measured": measured, "shape": list(request.shape())},
        )
        self.ck.mark("intake")
        if copied and not self.ck.done("style"):
            excerpt = ""
            folder = self.project.root / "references"
            files = sorted(folder.glob("*.txt"))
            if files:
                excerpt = read_text(files[0])[:1200]
            card = complete_json(
                self.backend,
                _messages(style_prompt(request, "\n".join(measured), excerpt)),
                temperature=0.3,
                max_tokens=512,
            )
            self.project.write_artefact("style.json", card)
            self.ck.mark("style")

    def _write_placeholder(
        self,
        scene: dict[str, Any],
        chapter_id: str,
        previous_id: str,
        next_id: str,
        reason: str,
    ) -> None:
        scene_id = str(scene["id"])
        payload: dict[str, Any] = {
            "scene_id": scene_id,
            "chapter_id": chapter_id,
            "kind": "placeholder",
            "dark": True,
            "reason": reason,
            "beats": scene,
            "pov": scene.get("pov") or "",
            "emotional_goal": scene.get("emotional_goal") or scene.get("emotional_shift") or "",
            "prev_scene_id": previous_id,
            "next_scene_id": next_id,
            "paragraphs": [],
        }
        self.project.write_artefact(f"scenes/{scene_id}.json", payload)
        self.placeholders += 1

    def _save_prose(
        self, scene: dict[str, Any], chapter_id: str, paragraphs: list[dict[str, str]]
    ) -> None:
        payload = {
            "scene_id": str(scene["id"]),
            "chapter_id": chapter_id,
            "kind": "prose",
            "dark": bool(scene.get("dark")),
            "paragraphs": paragraphs,
        }
        self.project.write_artefact(f"scenes/{payload['scene_id']}.json", payload)

    def _use(self, spec: ModelSpec) -> None:
        if self.resident == spec.id:
            return
        if self.resident is not None:
            self.swaps += 1
            self.backend.unload()
        self._log(f"load {spec.id}")
        self.backend.load(spec)
        self.resident = spec.id

    def _wait(self, gate: str) -> bool:
        if self.yes or gate in self.project.approved_gates():
            return False
        self.project.set_status("waiting", gate)
        self._write_report(None)
        return True

    def _waiting(self, gate: str) -> RunResult:
        self._log(f"waiting for approval: {gate}")
        return RunResult(
            "waiting",
            gate,
            None,
            self.swaps,
            self.refusals,
            self.placeholders,
            self.rewrites,
        )

    def _write_report(self, export_dir: Path | None) -> None:
        write_json(
            self.project.root / "run-report.json",
            {
                "swaps": self.swaps,
                "refusals": self.refusals,
                "placeholders": self.placeholders,
                "rewrites": self.rewrites,
                "export_dir": str(export_dir) if export_dir else "",
            },
        )

    def _log(self, message: str) -> None:
        self.on_progress(message)


def _specs(request: BookRequest) -> tuple[ModelSpec, ModelSpec]:
    main_id = request.main_model_id or "mock-main"
    low_id = request.least_censored_model_id or "mock-low"
    main_path = Path(request.main_gguf) if request.main_gguf else Path(f"{main_id}.gguf")
    low_path = (
        Path(request.least_censored_gguf) if request.least_censored_gguf else Path(f"{low_id}.gguf")
    )
    if request.tier is ModelTier.LEAST_CENSORED and not request.least_censored_gguf:
        low_id = main_id
        low_path = main_path
    main = ModelSpec(main_id, main_path, license="Apache-2.0")
    low = ModelSpec(low_id, low_path, license="Apache-2.0")
    if request.tier is ModelTier.LEAST_CENSORED and main.id == low.id:
        return main, low
    return main, low


def _messages(user: str) -> list[ChatMessage]:
    return [ChatMessage("system", system_message()), ChatMessage("user", user)]


def _obj(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    raise ModelOutputError("expected a JSON object artefact")


def _list(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    return []


def _paragraphs(payload: dict[str, object]) -> list[dict[str, str]]:
    raw = payload.get("paragraphs")
    if not isinstance(raw, list):
        raise ModelOutputError("the model returned no paragraphs")
    cleaned: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        cleaned.append(
            {
                "text": text,
                "speaker": str(item.get("speaker") or "NARRATOR"),
                "gender": parse_gender(item.get("gender")).value,
            }
        )
    if not cleaned:
        raise ModelOutputError("the model returned empty prose")
    return cleaned


def _paragraph_dicts(stored: dict[str, Any]) -> list[dict[str, str]]:
    raw = stored.get("paragraphs")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def _max_tokens(request: BookRequest) -> int:
    _chapters, _scenes, per_scene = request.shape()
    return min(4096, max(512, per_scene * 3))


def _style_card(project: Project) -> str:
    path = project.artefacts / "style.json"
    if not path.is_file():
        return ""
    payload = _obj(project.read_artefact("style.json"))
    return str(payload.get("style_card") or "")


def _tail(project: Project, scene_id: str) -> str:
    if not scene_id:
        return ""
    path = project.artefacts / "scenes" / f"{scene_id}.json"
    if not path.is_file():
        return ""
    stored = _obj(project.read_artefact(f"scenes/{scene_id}.json"))
    text = "\n\n".join(item.get("text", "") for item in _paragraph_dicts(stored))
    return text[-1500:]


def _scene_text(project: Project, scene_id: str) -> str:
    if not scene_id:
        return ""
    path = project.artefacts / "scenes" / f"{scene_id}.json"
    if not path.is_file():
        return ""
    stored = _obj(project.read_artefact(f"scenes/{scene_id}.json"))
    if stored.get("kind") == "placeholder":
        return str(stored.get("emotional_goal") or "")
    return "\n\n".join(item.get("text", "") for item in _paragraph_dicts(stored))


def _book_text(project: Project) -> str:
    parts: list[str] = []
    folder = project.artefacts / "scenes"
    if not folder.is_dir():
        return ""
    for path in sorted(folder.glob("*.json")):
        stored = _obj(project.read_artefact(f"scenes/{path.name}"))
        parts.extend(item.get("text", "") for item in _paragraph_dicts(stored))
    return "\n\n".join(parts)


def _render(
    project: Project,
    request: BookRequest,
    chapters: list[dict[str, Any]],
) -> list[RenderedChapter]:
    with project.canon() as canon:
        pronunciations = canon.pronunciations()
    rendered: list[RenderedChapter] = []
    for chapter in chapters:
        beats = _obj(project.read_artefact(f"beats/{chapter.get('id')}.json"))
        paragraphs: list[RenderedParagraph] = []
        for scene in _list(beats.get("scenes")):
            if not isinstance(scene, dict):
                continue
            stored = _obj(project.read_artefact(f"scenes/{scene.get('id')}.json"))
            for item in _paragraph_dicts(stored):
                text = prepare_prose(str(item.get("text") or ""), pronunciations)
                speaker = prepare_prose(str(item.get("speaker") or "NARRATOR"), pronunciations)
                gender = parse_gender(item.get("gender"))
                if gender is Gender.UNSPECIFIED and speaker.upper() != "NARRATOR":
                    gender = Gender.UNSPECIFIED
                paragraphs.append(RenderedParagraph(text, speaker, gender))
        rendered.append(
            RenderedChapter(
                str(chapter.get("title") or chapter.get("id")),
                paragraphs,
                id=str(chapter.get("id") or ""),
            )
        )
    return rendered


def _normalise_chapter_ids(chapters: list[dict[str, Any]]) -> bool:
    count = len(chapters)
    changed = False
    for index, chapter in enumerate(chapters, start=1):
        current = str(chapter.get("id") or "")
        nxt = emitted_chapter_id(current, index, count)
        if nxt != current:
            chapter["id"] = nxt
            changed = True
    return changed


def _bind_scene_ids(chapter_id: str, scenes: list[dict[str, Any]]) -> bool:
    changed = False
    prefix = f"{chapter_id}-"
    for index, scene in enumerate(scenes, start=1):
        raw = str(scene.get("id") or "")
        nxt = raw if raw.startswith(prefix) else f"{chapter_id}-sc{index:02d}"
        if scene.get("id") != nxt:
            scene["id"] = nxt
            changed = True
    return changed


def _character_rows(project: Project) -> list[dict[str, object]]:
    extras: dict[str, dict[str, object]] = {}
    if (project.artefacts / "bible.json").is_file():
        bible = _obj(project.read_artefact("bible.json"))
        for item in _list(bible.get("characters")):
            if isinstance(item, dict):
                key = name_key(str(item.get("name") or ""))
                if key:
                    extras[key] = item
    with project.canon() as canon:
        stored = canon.characters()
    if not stored:
        return list(extras.values())
    rows: list[dict[str, object]] = []
    for row in stored:
        extra = extras.get(name_key(row["name"]), {})
        rows.append(
            {
                "name": row["name"],
                "gender": row["gender"],
                "voice": row["voice"],
                "age_group": extra.get("age_group", ""),
                "age": extra.get("age"),
                "voice_hints": extra.get("voice_hints"),
                "aliases": extra.get("aliases"),
            }
        )
    return rows
