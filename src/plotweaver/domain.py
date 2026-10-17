"""Book request and the small enums the pipeline branches on."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from plotweaver.length import plan_shape


class Language(StrEnum):
    """Book language: Russian or English."""

    RU = "ru"
    EN = "en"


class BookMode(StrEnum):
    """How far the user stops the pipeline: autopilot, copilot, or manual."""

    AUTOPILOT = "autopilot"
    COPILOT = "copilot"
    MANUAL = "manual"


class ModelTier(StrEnum):
    """STANDARD is the usual drafter.

    LEAST_CENSORED is an installed Model Forge model. The stock drafter is the fallback.
    """

    STANDARD = "standard"
    LEAST_CENSORED = "least-censored"


class Gender(StrEnum):
    """Character gender used for speakers and voice."""

    MALE = "male"
    FEMALE = "female"
    UNSPECIFIED = "unspecified"


class ExportFormat(StrEnum):
    """User-facing book files. EPUB and .vxbook are always written."""

    EPUB = "epub"
    FB2 = "fb2"
    DOCX = "docx"
    MARKDOWN = "markdown"
    SPEAKER_MARKS = "speaker-marks"


class Task(StrEnum):
    """Routing label on every model call. The mock backend switches on it."""

    BIBLE = "bible"
    OUTLINE = "outline"
    BEATS = "beats"
    DRAFT = "draft"
    EXTRACT = "extract"
    REWRITE = "rewrite"
    FILL = "fill"
    PROOFREAD = "proofread"
    STYLE = "style"
    JUDGE = "judge"
    SOUND = "sound"
    PROBE = "probe"
    BRIEF = "brief"


def parse_gender(value: object) -> Gender:
    """Map a model value to male, female, or unspecified."""
    if value == Gender.MALE or value == "male":
        return Gender.MALE
    if value == Gender.FEMALE or value == "female":
        return Gender.FEMALE
    return Gender.UNSPECIFIED


@dataclass
class BookRequest:
    """What the user sets when a book is created. Stored as project.json."""

    title: str
    language: Language
    synopsis: str
    genre: str = ""
    target_words: int = 80_000
    chapter_count: int | None = None
    scenes_per_chapter: int = 2
    pov: str = "third-person limited"
    tense: str = "past"
    dark_themes: bool = False
    tier: ModelTier = ModelTier.STANDARD
    mode: BookMode = BookMode.AUTOPILOT
    reference_paths: list[str] = field(default_factory=list)
    main_model_id: str = ""
    least_censored_model_id: str = ""
    main_gguf: str = ""
    least_censored_gguf: str = ""
    scene_words: int | None = None
    author: str = ""
    export_formats: list[str] = field(default_factory=lambda: [ExportFormat.EPUB.value])
    created: str = ""
    sound_markup: bool = False
    brief: dict[str, object] | None = None
    prompt_override: str = ""
    generation_context: str = ""

    def shape(self) -> tuple[int, int, int]:
        """Return (chapters, scenes per chapter, words per scene)."""
        return plan_shape(
            self.target_words,
            self.language.value,
            self.chapter_count,
            self.scenes_per_chapter,
            self.scene_words,
        )


def request_to_dict(req: BookRequest) -> dict[str, object]:
    """Serialise a book request for project.json."""
    return {
        "title": req.title,
        "language": req.language.value,
        "synopsis": req.synopsis,
        "genre": req.genre,
        "target_words": req.target_words,
        "chapter_count": req.chapter_count,
        "scenes_per_chapter": req.scenes_per_chapter,
        "pov": req.pov,
        "tense": req.tense,
        "dark_themes": req.dark_themes,
        "tier": req.tier.value,
        "mode": req.mode.value,
        "reference_paths": list(req.reference_paths),
        "main_model_id": req.main_model_id,
        "least_censored_model_id": req.least_censored_model_id,
        "main_gguf": req.main_gguf,
        "least_censored_gguf": req.least_censored_gguf,
        "scene_words": req.scene_words,
        "author": req.author,
        "export_formats": normalize_formats(req.export_formats),
        "created": req.created,
        "sound_markup": req.sound_markup,
        "brief": req.brief,
        "prompt_override": req.prompt_override,
    }


def _as_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return default


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return int(value)
    return None


def request_from_dict(data: dict[str, object]) -> BookRequest:
    """Read a book request back from project.json."""
    refs = data.get("reference_paths") or []
    if not isinstance(refs, list):
        refs = []
    return BookRequest(
        title=str(data.get("title") or "Untitled"),
        language=Language(str(data.get("language") or Language.RU)),
        synopsis=str(data.get("synopsis") or ""),
        genre=str(data.get("genre") or ""),
        target_words=_as_int(data.get("target_words"), 80_000),
        chapter_count=_optional_int(data.get("chapter_count")),
        scenes_per_chapter=_as_int(data.get("scenes_per_chapter"), 2),
        pov=str(data.get("pov") or "third-person limited"),
        tense=str(data.get("tense") or "past"),
        dark_themes=bool(data.get("dark_themes")),
        tier=_tier_from_stored(data.get("tier")),
        mode=BookMode(str(data.get("mode") or BookMode.AUTOPILOT)),
        reference_paths=[str(item) for item in refs],
        main_model_id=str(data.get("main_model_id") or ""),
        least_censored_model_id=str(
            data.get("least_censored_model_id") or data.get("low_refusal_model_id") or ""
        ),
        main_gguf=str(data.get("main_gguf") or ""),
        least_censored_gguf=str(
            data.get("least_censored_gguf") or data.get("low_refusal_gguf") or ""
        ),
        scene_words=_optional_int(data.get("scene_words")),
        author=str(data.get("author") or ""),
        export_formats=normalize_formats(data.get("export_formats")),
        created=str(data.get("created") or ""),
        sound_markup=bool(data.get("sound_markup")),
        brief=_brief_dict(data.get("brief")),
        prompt_override=str(data.get("prompt_override") or ""),
    )


def _brief_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return value
    return None


def _tier_from_stored(value: object) -> ModelTier:
    text = str(value or ModelTier.STANDARD)
    if text == "low-refusal":
        return ModelTier.LEAST_CENSORED
    return ModelTier(text)


def normalize_formats(value: object) -> list[str]:
    """EPUB 3 is always included. Unknown names are dropped."""
    allowed = {item.value for item in ExportFormat}
    raw: list[object] = list(value) if isinstance(value, list) else []
    chosen: list[str] = []
    for item in [ExportFormat.EPUB.value, *raw]:
        text = str(item)
        if text in allowed and text not in chosen:
            chosen.append(text)
    return chosen


def repo_file(name: str) -> Path:
    """A path relative to the checkout, used by scenarios and the bake-off."""
    return Path(name)
