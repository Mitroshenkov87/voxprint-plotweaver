"""Deterministic mock LLM and the sound document it returns.

Imported only when the Plotweaver dev extra is installed. The product wheel
does not contain this package.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from plotweaver.domain import Task
from plotweaver.errors import assert_never
from plotweaver.llm import ChatMessage, Completion, ModelSpec, task_of
from plotweaver.sound import DEFAULTS


def mock_sound_document(user: str) -> dict[str, object]:
    """Deterministic markup the CI mock returns for TASK: sound."""
    payload = _prompt_data(user)
    rows = payload.get("paragraphs")
    paragraphs = rows if isinstance(rows, list) else []
    scenes: list[dict[str, object]] = []
    current: list[dict[str, object]] = []
    for item in paragraphs:
        if not isinstance(item, dict):
            continue
        if item.get("scene_start") is True and current:
            scenes.append(_mock_scene(len(scenes) + 1, current))
            current = []
        current.append(item)
    if current:
        scenes.append(_mock_scene(len(scenes) + 1, current))
    cues: list[dict[str, object]] = []
    for scene in scenes:
        start = _as_int(scene.get("start_paragraph"))
        end = _as_int(scene.get("end_paragraph"))
        mood = _as_str(scene.get("mood"))
        cues.append(
            {
                "id": f"bed-{start}",
                "kind": "bed",
                "layer": "music",
                "prompt": f"soft {mood} ambient music bed, no percussion, no vocals",
                "mood": mood,
                "intensity": scene.get("intensity"),
                "start_paragraph": start,
                "end_paragraph": end,
                "gain_db": DEFAULTS["bed_gain_db"],
                "duck_db": DEFAULTS["duck_db"],
                "loop": True,
                "src": "auto",
                "conf": 0.8,
            }
        )
        if start != 1:
            at = "chapter_start" if _chapter_first(paragraphs, start) else "scene_break"
            cues.append(
                {
                    "id": f"tr-{start}",
                    "kind": "transition",
                    "at": at,
                    "prompt": "short warm musical cadence for a scene change, no vocals",
                    "mood": mood,
                    "intensity": 0.3,
                    "start_paragraph": start,
                    "position": "before",
                    "gain_db": DEFAULTS["transition_gain_db"],
                    "src": "auto",
                    "conf": 0.7,
                }
            )
        if end > start:
            cues.append(
                {
                    "id": f"ac-{start + 1}",
                    "kind": "accent",
                    "prompt": "brief low string swell, two seconds, no percussion, no vocals",
                    "mood": "tense",
                    "intensity": 0.4,
                    "start_paragraph": start + 1,
                    "position": "before",
                    "gain_db": DEFAULTS["accent_gain_db"],
                    "src": "auto",
                    "conf": 0.66,
                }
            )
    return {"scenes": scenes, "cues": cues}


class MockBackend:
    """Deterministic local backend for CI and the UI self-test.

    It never touches a GPU. Dark scenes are not written here: the pipeline asks for
    beats, and this backend marks one scene dark when the book toggle is on.
    """

    def __init__(self, refuse_drafts: int = 0) -> None:
        self.model_id = "mock-main"
        self.refuse_drafts = refuse_drafts
        self.tasks: list[str] = []
        self.loads: list[str] = []
        self.calls: list[dict[str, object]] = []
        self.last_user = ""

    def load(self, spec: ModelSpec) -> None:
        """Remember the loaded model id. Nothing is read from disk."""
        self.loads.append(spec.id)
        self.model_id = spec.id

    def unload(self) -> None:
        """Forget the resident model id."""
        self.model_id = ""

    def prepare_batch(self) -> None:
        """The mock does not measure VRAM."""
        return None

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
        response_format: Mapping[str, object] | None = None,
    ) -> Completion:
        """One deterministic reply for the TASK line in the latest user message."""
        del temperature, json_mode, response_format
        user = ""
        for message in reversed(messages):
            if message.role != "user":
                continue
            user = message.content
            break
        self.last_user = user
        task = task_of(messages)
        self.tasks.append(task.value)
        self.calls.append(
            {
                "task": task.value,
                "max_tokens": max_tokens,
                "phase": _flag(user, "outline_phase") or _flag(user, "extract_phase"),
                "user": user,
            }
        )
        if task is Task.DRAFT and self.refuse_drafts > 0:
            self.refuse_drafts -= 1
            text = "I cannot write this scene."
        else:
            text = self._reply(task, user)
        return Completion(text, 12, max(1, len(text) // 4), self.model_id or "mock")

    def _reply(self, task: Task, user: str) -> str:
        match task:
            case Task.BIBLE:
                return json.dumps(self._bible(user), ensure_ascii=False)
            case Task.OUTLINE:
                return json.dumps(self._outline(user), ensure_ascii=False)
            case Task.BEATS:
                return json.dumps(self._beats(user), ensure_ascii=False)
            case Task.DRAFT | Task.FILL | Task.REWRITE | Task.PROOFREAD:
                return json.dumps({"paragraphs": self._paragraphs(user, task)}, ensure_ascii=False)
            case Task.EXTRACT:
                chapter_id = _flag(user, "chapter_id") or "ch01"
                summary = f"{chapter_id} keeps the mission moving."
                previous = _story_so_far(user)
                story = (previous + " " + summary).strip()
                if len(story) > 700:
                    story = story[-700:].lstrip()
                return json.dumps(
                    {
                        "facts": [{"text": "The crew is still on the mission.", "paragraph": 0}],
                        "timeline": [
                            {"description": "The chapter happens after the synopsis opening."}
                        ],
                        "threads": [
                            {"description": "The landing promise is still open.", "status": "open"}
                        ],
                        "knowledge": [],
                        "summary": summary,
                        "story_so_far": story,
                    },
                    ensure_ascii=False,
                )
            case Task.STYLE:
                return json.dumps(
                    {"style_card": "Short sentences, concrete nouns, dialogue in dashes."},
                    ensure_ascii=False,
                )
            case Task.JUDGE:
                return json.dumps(
                    {
                        "ordinary_prose": 4,
                        "dark_prose": 4,
                        "coherence": 4,
                        "voice_match": 4,
                        "refusal": 5,
                        "notes": "Mock judge. Replace with a local model on the GPU machine.",
                    },
                    ensure_ascii=False,
                )
            case Task.SOUND:
                return json.dumps(mock_sound_document(user), ensure_ascii=False)
            case Task.BRIEF:
                return json.dumps(self._brief(user), ensure_ascii=False)
            case Task.PROBE:
                if self.model_id in {"mock-low"} or "abliterated" in (self.model_id or ""):
                    return "The scene continues. Dust stayed on the hatch and nobody lectured."
                return "I cannot write this scene."
            case _ as unreachable:
                assert_never(unreachable)

    def _brief(self, user: str) -> dict[str, object]:
        idea = ""
        if "IDEA:" in user:
            idea = user.split("IDEA:", 1)[1].strip()
        title = idea.splitlines()[0].strip()[:80] if idea else "Untitled"
        language = "ru" if "language: ru" in user else "en"
        return {
            "version": 1,
            "title": title or "Untitled",
            "language": language,
            "pages": 40,
            "words_per_page": 250,
            "genre": "science fiction",
            "subgenre": "expedition",
            "tone": "dry",
            "pov": "third-person limited",
            "tense": "past",
            "audience": "adult",
            "setting": "a research station",
            "characters": [
                {
                    "name": "Ilya",
                    "role": "commander",
                    "description": "Short orders.",
                    "gender": "male",
                }
            ],
            "plot_points": ["The seal fails.", "The crew stays."],
            "ending_type": "bittersweet",
            "style_references": ["a field log"],
            "dark_themes": False,
            "synopsis": idea or "A crew keeps a station.",
            "guessed": ["tone", "pov", "tense", "audience", "ending_type", "subgenre"],
        }

    def _bible(self, user: str) -> dict[str, object]:
        if _language_ru(user):
            characters: list[dict[str, str]] = [
                {
                    "name": "Илья Воронов",
                    "gender": "male",
                    "role": "commander",
                    "goals": "Finish the mission.",
                    "secrets": "He fears an early ascent.",
                    "voice": "Short orders.",
                    "arc": "Learns to stop when the engineer says stop.",
                    "pronunciation": "Илья\u0301 Воронов",
                },
                {
                    "name": "Марина Лебедева",
                    "gender": "female",
                    "role": "engineer",
                    "goals": "Keep the seal intact.",
                    "secrets": "She has already counted the crack.",
                    "voice": "Precise, dry.",
                    "arc": "Makes the commander hear the machine.",
                    "pronunciation": "Мари\u0301на Лебедева",
                },
            ]
            logline = "Экипаж держит корабль на чужой пыли и решает, уходить или остаться."
        else:
            characters = [
                {
                    "name": "Ilya Voronov",
                    "gender": "male",
                    "role": "commander",
                    "goals": "Finish the mission.",
                    "secrets": "He fears an early ascent.",
                    "voice": "Short orders.",
                    "arc": "He learns to stop.",
                    "pronunciation": "Ilya Voronov",
                },
                {
                    "name": "Marina Lebedeva",
                    "gender": "female",
                    "role": "engineer",
                    "goals": "Keep the ship intact.",
                    "secrets": "She has counted the crack.",
                    "voice": "Precise.",
                    "arc": "She makes him listen.",
                    "pronunciation": "Marina Lebedeva",
                },
            ]
            logline = "A crew decides whether to stay or leave."
        return {
            "logline": logline,
            "theme": "A schedule is not a promise the machine can keep.",
            "genre_contract": "Science fiction with a quiet ending.",
            "tone": "Dry, concrete.",
            "ending_intent": "They leave with less than the contract asked, and they say so.",
            "characters": characters,
        }

    def _outline(self, user: str) -> dict[str, object]:
        phase = _flag(user, "outline_phase")
        count = _chapter_count(user)
        if phase in {"parts", "repair-parts"}:
            return {"parts": _mock_parts(user, count)}
        if phase in {"chapters", "repair-chapters"}:
            return {"chapters": _mock_chapter_rows(user)}
        chapters = []
        for index in range(1, count + 1):
            chapters.append(_mock_chapter(index, count, user))
        return {"chapters": chapters}

    def _beats(self, user: str) -> dict[str, object]:
        chapter_id = _flag(user, "chapter_id") or "ch01"
        try:
            scenes_n = max(1, int(_flag(user, "scenes_per_chapter") or "2"))
        except ValueError:
            scenes_n = 2
        dark_book = _flag(user, "dark_themes") == "true"
        chapter_index = _flag(user, "chapter_index")
        scenes = []
        for number in range(1, scenes_n + 1):
            dark = dark_book and chapter_index == "2" and number == scenes_n
            scenes.append(
                {
                    "id": f"{chapter_id}-sc{number:02d}",
                    "goal": "Press the scene forward.",
                    "conflict": "The machine and the schedule disagree.",
                    "outcome": "A decision is delayed by one concrete fact.",
                    "new_info": "Something in the ship has changed.",
                    "emotional_shift": "From certainty to attention.",
                    "emotional_goal": "Stay honest.",
                    "pov": "Илья Воронов" if _language_ru(user) else "Ilya Voronov",
                    "pov_gender": "male",
                    "dark": dark,
                }
            )
        return {"scenes": scenes}

    def _paragraphs(self, user: str, task: Task) -> list[dict[str, str]]:
        ru = _language_ru(user)
        if ru:
            narrator = (
                "Ещё не всё было сказано вслух. Илья\u0301 смотрел на пыль и молчал, "
                "пока Мари\u0301на держала схему шва."
            )
            male = "— Мы не уйдём, пока шов держит, — сказал Илья\u0301."
            female = "— Шов держит, пока мы его не торопим, — ответила Мари\u0301на."
            male_name, female_name = "Илья Воронов", "Марина Лебедева"
        else:
            narrator = "The room stayed quiet. Ilya watched the dust and waited."
            male = '"We stay while the seam holds," Ilya said.'
            female = '"The seam holds if we stop rushing it," Marina said.'
            male_name, female_name = "Ilya Voronov", "Marina Lebedeva"
        if task is Task.FILL:
            narrator = "Placeholder filled. " + narrator
        return [
            {"text": narrator, "speaker": "NARRATOR", "gender": ""},
            {"text": male, "speaker": male_name, "gender": "male"},
            {"text": female, "speaker": female_name, "gender": "female"},
        ]


def _language_ru(user: str) -> bool:
    return "language: ru" in user


def _mock_parts(user: str, count: int) -> list[dict[str, object]]:
    spans = _part_spans(user)
    if not spans:
        spans = [(1, count)] if count else []
    parts: list[dict[str, object]] = []
    for index, (start, end) in enumerate(spans, start=1):
        parts.append(
            {
                "index": index,
                "title": f"Part {index}",
                "purpose": f"Cover chapters {start} through {end}.",
                "chapter_start": start,
                "chapter_end": end,
            }
        )
    return parts


def _mock_chapter_rows(user: str) -> list[dict[str, object]]:
    count = _chapter_count(user)
    missing = _missing_indexes(user)
    if missing:
        indexes = missing
    else:
        start = _positive_flag(user, "chapter_start", 1)
        end = _positive_flag(user, "chapter_end", start)
        indexes = list(range(start, end + 1))
    return [_mock_chapter(index, count, user) for index in indexes]


def _mock_chapter(index: int, count: int, user: str) -> dict[str, object]:
    return {
        "index": index,
        "id": f"ch{index:02d}",
        "title": f"Chapter {index}",
        "purpose": f"Move the story through chapter {index} of {count}.",
        "pov": "Илья Воронов" if _language_ru(user) else "Ilya Voronov",
        "word_budget": 1000,
        "dark_hint": False,
    }


def _part_spans(user: str) -> list[tuple[int, int]]:
    found: list[tuple[int, int]] = []
    for line in user.splitlines():
        stripped = line.strip()
        if not stripped.startswith("part_span:"):
            continue
        raw = stripped.split(":", 1)[1].strip()
        if "-" not in raw:
            continue
        left, right = raw.split("-", 1)
        try:
            start, end = int(left), int(right)
        except ValueError:
            continue
        if end >= start >= 1:
            found.append((start, end))
    return found


def _missing_indexes(user: str) -> list[int]:
    raw = _flag(user, "missing")
    if not raw:
        return []
    found: list[int] = []
    for part in raw.split(","):
        try:
            found.append(int(part.strip()))
        except ValueError:
            continue
    return found


def _positive_flag(user: str, name: str, default: int) -> int:
    raw = _flag(user, name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _story_so_far(user: str) -> str:
    marker = "STORY SO FAR:"
    if marker not in user:
        return ""
    lines: list[str] = []
    for line in user.split(marker, 1)[1].splitlines():
        if line.startswith(("PROSE:", "FACTS:", "TASK:", "CHAPTER:")):
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _chapter_count(user: str) -> int:
    for line in user.splitlines():
        if line.startswith("chapter_count:"):
            try:
                return max(1, int(line.split(":", 1)[1].strip()))
            except ValueError:
                return 1
    return 1


def _flag(user: str, name: str) -> str:
    prefix = f"{name}:"
    for line in user.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return ""


def _prompt_data(user: str) -> dict[str, object]:
    for line in user.splitlines():
        if line.startswith("DATA: "):
            parsed = json.loads(line.removeprefix("DATA: "))
            if isinstance(parsed, dict):
                return parsed
    return {}


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _mock_scene(number: int, rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    moods = ("mysterious", "calm", "warm", "tense")
    start = _as_int(rows[0].get("index"))
    end = _as_int(rows[-1].get("index"))
    return {
        "id": f"s{number}",
        "chapter": _as_str(rows[0].get("chapter")),
        "start_paragraph": start,
        "end_paragraph": end,
        "mood": moods[(number - 1) % len(moods)],
        "intensity": 0.4,
        "src": "auto",
        "conf": 0.8,
    }


def _chapter_first(paragraphs: Sequence[object], start: int) -> bool:
    chapter = ""
    first = 0
    for item in paragraphs:
        if not isinstance(item, dict):
            continue
        if _as_int(item.get("index")) == start:
            chapter = _as_str(item.get("chapter"))
            break
    for item in paragraphs:
        if isinstance(item, dict) and _as_str(item.get("chapter")) == chapter:
            first = _as_int(item.get("index"))
            break
    return first == start
