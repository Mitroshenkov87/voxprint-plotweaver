"""Model call types, JSON completion with one repair, and the deterministic mock."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from plotweaver.domain import Task
from plotweaver.errors import ModelOutputError, assert_never
from plotweaver.jsontext import parse_json_object
from plotweaver.sound import mock_sound_document


@dataclass
class ChatMessage:
    """One message in a model chat."""

    role: str
    content: str


@dataclass
class Completion:
    """Text and token counts from one model reply."""

    text: str
    prompt_tokens: int
    completion_tokens: int
    model_id: str


@dataclass
class ModelSpec:
    """One GGUF the worker may load. Only one large model is resident at a time."""

    id: str
    path: Path
    context: int = 8192
    license: str = "Apache-2.0"
    moe: bool = False


class LLMBackend(Protocol):
    """The model caller the pipeline uses."""

    model_id: str

    def load(self, spec: ModelSpec) -> None:
        """Load this model, unloading any other large model first."""

    def unload(self) -> None:
        """Drop the resident model so the next load is the only one in memory."""

    def prepare_batch(self) -> None:
        """Re-measure VRAM before a batch. The mock does nothing."""

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Completion:
        """One non-streaming completion."""


def task_of(messages: list[ChatMessage]) -> Task:
    """Read the TASK line from the latest user message."""
    for message in reversed(messages):
        if message.role != "user":
            continue
        for line in message.content.splitlines():
            if line.startswith("TASK:"):
                return Task(line.split(":", 1)[1].strip())
    raise ModelOutputError("prompt has no TASK line")


def complete_json(
    backend: LLMBackend,
    messages: list[ChatMessage],
    *,
    temperature: float,
    max_tokens: int,
) -> dict[str, object]:
    """Ask for JSON. One repair call if the first reply does not parse. No further retries."""
    first = backend.complete(
        messages, temperature=temperature, max_tokens=max_tokens, json_mode=True
    )
    parsed = parse_json_object(first.text)
    if parsed is not None:
        return parsed
    original = messages[-1].content if messages else ""
    repair = [
        *messages,
        ChatMessage("assistant", first.text),
        ChatMessage(
            "user",
            original
            + "\n\nYour previous reply was not a JSON object. Return one JSON object only.",
        ),
    ]
    second = backend.complete(repair, temperature=0.2, max_tokens=max_tokens, json_mode=True)
    parsed = parse_json_object(second.text)
    if parsed is None:
        raise ModelOutputError("the model did not return JSON")
    return parsed


def _language_ru(user: str) -> bool:
    return "language: ru" in user


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
        self.last_user = ""

    def load(self, spec: ModelSpec) -> None:
        self.loads.append(spec.id)
        self.model_id = spec.id

    def unload(self) -> None:
        self.model_id = ""

    def prepare_batch(self) -> None:
        return None

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float,
        max_tokens: int,
        json_mode: bool,
    ) -> Completion:
        del temperature, max_tokens, json_mode
        user = ""
        for message in reversed(messages):
            if message.role == "user":
                user = message.content
                break
        self.last_user = user
        task = task_of(messages)
        self.tasks.append(task.value)
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
        count = _chapter_count(user)
        chapters = []
        for index in range(1, count + 1):
            chapters.append(
                {
                    "id": f"ch{index:02d}",
                    "title": f"Chapter {index}",
                    "purpose": f"Move the story through part {index} of {count}.",
                    "pov": "Илья Воронов" if _language_ru(user) else "Ilya Voronov",
                    "word_budget": 1000,
                    "dark_hint": False,
                }
            )
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
