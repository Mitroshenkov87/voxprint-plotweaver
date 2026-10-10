"""Book request and the small enums the pipeline branches on."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Language(StrEnum):
    RU = "ru"
    EN = "en"


class BookMode(StrEnum):
    AUTOPILOT = "autopilot"
    COPILOT = "copilot"
    MANUAL = "manual"


class ModelTier(StrEnum):
    STANDARD = "standard"
    LOW_REFUSAL = "low-refusal"


class Gender(StrEnum):
    MALE = "male"
    FEMALE = "female"
    UNSPECIFIED = "unspecified"


class ExportFormat(StrEnum):
    """User-facing book files. EPUB is always written; the others are optional."""

    EPUB = "epub"
    FB2 = "fb2"
    DOCX = "docx"
    MARKDOWN = "markdown"


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


def parse_gender(value: object) -> Gender:
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
    low_refusal_model_id: str = ""
    main_gguf: str = ""
    low_refusal_gguf: str = ""
    scene_words: int | None = None
    author: str = ""
    export_formats: list[str] = field(default_factory=lambda: [ExportFormat.EPUB.value])

    def shape(self) -> tuple[int, int, int]:
        """Return (chapters, scenes per chapter, words per scene)."""
        if self.chapter_count is not None and self.chapter_count > 0:
            chapters = self.chapter_count
        else:
            chapters = min(40, max(8, round(self.target_words / 2500)))
        scenes = max(1, self.scenes_per_chapter)
        if self.scene_words is not None and self.scene_words > 0:
            per_scene = self.scene_words
        else:
            per_scene = max(400, self.target_words // (chapters * scenes))
        return chapters, scenes, per_scene


def request_to_dict(req: BookRequest) -> dict[str, object]:
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
        "low_refusal_model_id": req.low_refusal_model_id,
        "main_gguf": req.main_gguf,
        "low_refusal_gguf": req.low_refusal_gguf,
        "scene_words": req.scene_words,
        "author": req.author,
        "export_formats": normalize_formats(req.export_formats),
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
        tier=ModelTier(str(data.get("tier") or ModelTier.STANDARD)),
        mode=BookMode(str(data.get("mode") or BookMode.AUTOPILOT)),
        reference_paths=[str(item) for item in refs],
        main_model_id=str(data.get("main_model_id") or ""),
        low_refusal_model_id=str(data.get("low_refusal_model_id") or ""),
        main_gguf=str(data.get("main_gguf") or ""),
        low_refusal_gguf=str(data.get("low_refusal_gguf") or ""),
        scene_words=_optional_int(data.get("scene_words")),
        author=str(data.get("author") or ""),
        export_formats=normalize_formats(data.get("export_formats")),
    )


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
