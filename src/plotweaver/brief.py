"""Versioned book brief: JSON, the Markdown template, and the compiled context."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from plotweaver.domain import BookRequest
from plotweaver.errors import PlotweaverError
from plotweaver.paths import repo_root

BRIEF_VERSION = 1
DEFAULT_WORDS_PER_PAGE = 250
_GENDERS = ("male", "female", "unspecified")
_LANGUAGES = ("ru", "en")

_SECTION_TO_FIELD = {
    "title": "title",
    "language": "language",
    "length": "length",
    "genre": "genre",
    "subgenre": "subgenre",
    "tone": "tone",
    "point of view": "pov",
    "pov": "pov",
    "tense": "tense",
    "audience": "audience",
    "setting": "setting",
    "characters": "characters",
    "plot points": "plot_points",
    "ending": "ending_type",
    "style references": "style_references",
    "dark themes": "dark_themes",
    "synopsis": "synopsis",
    "guessed": "guessed",
}


@dataclass
class FieldError:
    """One invalid brief field."""

    field: str
    code: str

    def message(self) -> str:
        """English CLI text for this error. The window translates the code."""
        match self.code:
            case "required":
                return f"{self.field} is required."
            case "language":
                return "language must be en or ru."
            case "gender":
                return f"{self.field} must be male, female, or unspecified."
            case "positive":
                return f"{self.field} must be a positive number."
            case "bool":
                return "dark themes must be yes or no."
            case "version":
                return "brief version must be 1."
            case "target":
                return "target words must equal pages times words per page."
            case "json":
                return "the brief is not valid JSON."
            case "characters":
                return "each character needs a name, role, description, and gender."
            case "list":
                return f"{self.field} must be a list."
            case "type":
                return f"{self.field} has the wrong type."
            case _ as unreachable:
                return f"{self.field}: {unreachable}"


class BriefError(PlotweaverError):
    """The brief text failed validation. errors names each field."""

    def __init__(self, errors: list[FieldError]) -> None:
        self.errors = errors
        super().__init__("\n".join(item.message() for item in errors))


@dataclass
class Character:
    """One person the brief names."""

    name: str
    role: str
    description: str
    gender: str

    def to_dict(self) -> dict[str, str]:
        """JSON object for one character."""
        return {
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "gender": self.gender,
        }


@dataclass
class BookBrief:
    """The fields the new-book form and the generator share. Version 1."""

    title: str
    language: str
    pages: int
    words_per_page: int
    genre: str
    subgenre: str
    tone: str
    pov: str
    tense: str
    audience: str
    setting: str
    characters: list[Character]
    plot_points: list[str]
    ending_type: str
    style_references: list[str]
    dark_themes: bool
    synopsis: str
    guessed: list[str] = field(default_factory=list)
    chapter_count: int | None = None
    scenes_per_chapter: int | None = None
    version: int = BRIEF_VERSION

    @property
    def target_words(self) -> int:
        """Pages times words per page."""
        return self.pages * self.words_per_page

    def derived_chapters(self) -> int:
        """Chapter count, or the same automatic split the pipeline uses."""
        if self.chapter_count is not None and self.chapter_count > 0:
            return self.chapter_count
        return min(40, max(8, round(self.target_words / 2500)))

    def derived_scenes(self) -> int:
        """Scenes per chapter. An empty override means 2."""
        if self.scenes_per_chapter is not None and self.scenes_per_chapter > 0:
            return self.scenes_per_chapter
        return 2

    def to_dict(self) -> dict[str, object]:
        """JSON object for version 1."""
        return {
            "version": self.version,
            "title": self.title,
            "language": self.language,
            "pages": self.pages,
            "words_per_page": self.words_per_page,
            "target_words": self.target_words,
            "chapter_count": self.chapter_count,
            "scenes_per_chapter": self.scenes_per_chapter,
            "genre": self.genre,
            "subgenre": self.subgenre,
            "tone": self.tone,
            "pov": self.pov,
            "tense": self.tense,
            "audience": self.audience,
            "setting": self.setting,
            "characters": [item.to_dict() for item in self.characters],
            "plot_points": list(self.plot_points),
            "ending_type": self.ending_type,
            "style_references": list(self.style_references),
            "dark_themes": self.dark_themes,
            "synopsis": self.synopsis,
            "guessed": list(self.guessed),
        }


def parse_brief(text: str) -> BookBrief:
    """Read a version-1 JSON object or the Markdown template."""
    stripped = text.strip()
    if not stripped:
        raise BriefError([FieldError("brief", "required")])
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            raise BriefError([FieldError("brief", "json")]) from None
        if not isinstance(payload, dict):
            raise BriefError([FieldError("brief", "json")])
        return brief_from_dict(payload, strict=True)
    return _parse_markdown(stripped)


def brief_from_dict(payload: dict[str, object], *, strict: bool) -> BookBrief:
    """Validate a JSON object. Strict import rejects missing required fields."""
    errors: list[FieldError] = []
    version = payload.get("version", BRIEF_VERSION)
    if version != BRIEF_VERSION:
        errors.append(FieldError("version", "version"))
    title = _text(payload.get("title"))
    language = _text(payload.get("language")).lower()
    pages = _positive(payload.get("pages"), "pages", errors)
    words_per_page = _positive(payload.get("words_per_page"), "words_per_page", errors)
    if "target_words" in payload and payload.get("target_words") not in (None, ""):
        stated = _positive(payload.get("target_words"), "target_words", errors)
        if pages and words_per_page and stated and stated != pages * words_per_page:
            errors.append(FieldError("target_words", "target"))
    genre = _text(payload.get("genre"))
    subgenre = _text(payload.get("subgenre"))
    tone = _text(payload.get("tone"))
    pov = _text(payload.get("pov"))
    tense = _text(payload.get("tense"))
    audience = _text(payload.get("audience"))
    setting = _text(payload.get("setting"))
    ending = _text(payload.get("ending_type"))
    synopsis = _text(payload.get("synopsis"))
    dark = _bool(payload.get("dark_themes"), errors)
    characters = _characters(payload.get("characters"), errors)
    plot_points = _str_list(payload.get("plot_points"), "plot_points", errors)
    styles = _str_list(payload.get("style_references"), "style_references", errors)
    guessed = _str_list(payload.get("guessed", []), "guessed", errors)
    chapters = _optional_positive(payload.get("chapter_count"), "chapter_count", errors)
    scenes = _optional_positive(payload.get("scenes_per_chapter"), "scenes_per_chapter", errors)
    if not language:
        if strict:
            errors.append(FieldError("language", "required"))
    elif language not in _LANGUAGES:
        errors.append(FieldError("language", "language"))
    if strict:
        for name, value in (
            ("title", title),
            ("genre", genre),
            ("pov", pov),
            ("tense", tense),
            ("synopsis", synopsis),
        ):
            if not value:
                errors.append(FieldError(name, "required"))
        if not characters:
            errors.append(FieldError("characters", "required"))
    if errors:
        raise BriefError(errors)
    return BookBrief(
        title=title,
        language=language,
        pages=pages or 1,
        words_per_page=words_per_page or DEFAULT_WORDS_PER_PAGE,
        genre=genre,
        subgenre=subgenre,
        tone=tone,
        pov=pov,
        tense=tense,
        audience=audience,
        setting=setting,
        characters=characters,
        plot_points=plot_points,
        ending_type=ending,
        style_references=styles,
        dark_themes=dark,
        synopsis=synopsis,
        guessed=guessed,
        chapter_count=chapters,
        scenes_per_chapter=scenes,
    )


def brief_from_payload(payload: dict[str, object], *, idea: str, language: str) -> BookBrief:
    """Fill every field from a model object. Anything it omitted is marked guessed."""
    guessed = _str_list(payload.get("guessed", []), "guessed", [])
    data = dict(payload)
    data["version"] = BRIEF_VERSION
    data["language"] = language
    defaults: dict[str, object] = {
        "title": _first_line(idea) or "Untitled",
        "pages": 80,
        "words_per_page": DEFAULT_WORDS_PER_PAGE,
        "genre": "fiction",
        "subgenre": "",
        "tone": "plain",
        "pov": "third-person limited",
        "tense": "past",
        "audience": "adult",
        "setting": "",
        "ending_type": "closed",
        "synopsis": idea.strip() or "A story.",
        "dark_themes": False,
        "plot_points": [],
        "style_references": [],
        "characters": [
            {
                "name": "Protagonist",
                "role": "protagonist",
                "description": "The person the notes follow.",
                "gender": "unspecified",
            }
        ],
    }
    for key, value in defaults.items():
        current = data.get(key)
        empty = current in (None, "", [], {})
        if empty:
            data[key] = value
            if key not in guessed:
                guessed.append(key)
    data["guessed"] = guessed
    data.pop("target_words", None)
    return brief_from_dict(data, strict=False)


def compile_brief(brief: BookBrief) -> str:
    """The brief block inserted into the header and the bible and outline prompts."""
    people = "; ".join(
        f"{item.name} ({item.gender}), {item.role}: {item.description}".strip()
        for item in brief.characters
    )
    points = "; ".join(brief.plot_points)
    styles = "; ".join(brief.style_references)
    chapters = brief.derived_chapters()
    scenes = brief.derived_scenes()
    chapter_note = "set by the brief" if brief.chapter_count else "derived from the length"
    lines = [
        "BOOK BRIEF (binding):",
        f"title: {brief.title}",
        f"language: {brief.language}",
        f"pages: {brief.pages}",
        f"words_per_page: {brief.words_per_page}",
        f"target_words: {brief.target_words}",
        f"chapter_count: {chapters} ({chapter_note})",
        f"scenes_per_chapter: {scenes}",
        f"genre: {brief.genre}",
        f"subgenre: {brief.subgenre}",
        f"tone: {brief.tone}",
        f"pov: {brief.pov}",
        f"tense: {brief.tense}",
        f"audience: {brief.audience}",
        f"setting: {brief.setting}",
        f"ending_type: {brief.ending_type}",
        f"dark_themes: {str(brief.dark_themes).lower()}",
        f"characters: {people}",
        f"plot_points: {points}",
        f"style_references: {styles}",
        "Use these fields as given. Do not infer a different point of view, tense, "
        "genre, cast, ending, or audience from the synopsis.",
    ]
    return "\n".join(lines)


def attach_context(req: BookRequest) -> BookRequest:
    """Set generation_context from an edited preview, or from the stored brief."""
    if req.prompt_override.strip():
        req.generation_context = req.prompt_override.strip()
        return req
    if isinstance(req.brief, dict) and req.brief:
        try:
            req.generation_context = compile_brief(brief_from_dict(req.brief, strict=False))
        except BriefError:
            req.generation_context = ""
        return req
    req.generation_context = ""
    return req


def apply_brief(req: BookRequest, brief: BookBrief) -> BookRequest:
    """Copy brief fields onto the book request the pipeline already stores."""
    req.title = brief.title or req.title
    req.language = req.language.__class__(brief.language)
    req.synopsis = brief.synopsis
    req.genre = brief.genre
    req.target_words = brief.target_words
    req.chapter_count = brief.chapter_count
    req.scenes_per_chapter = brief.derived_scenes()
    req.pov = brief.pov or req.pov
    req.tense = brief.tense or req.tense
    req.dark_themes = brief.dark_themes
    req.brief = brief.to_dict()
    return req


def markdown_template() -> str:
    """Empty Markdown brief. Headings stay in English so the importer can find them."""
    return "\n".join(
        [
            "# Book brief",
            "",
            "version: 1",
            "",
            "## Title",
            "",
            "## Language",
            "",
            "en",
            "",
            "## Length",
            "",
            "pages: 80",
            "words_per_page: 250",
            "chapters:",
            "scenes_per_chapter:",
            "",
            "## Genre",
            "",
            "## Subgenre",
            "",
            "## Tone",
            "",
            "## Point of view",
            "",
            "third-person limited",
            "",
            "## Tense",
            "",
            "past",
            "",
            "## Audience",
            "",
            "adult",
            "",
            "## Setting",
            "",
            "## Characters",
            "",
            "- name:",
            "  role:",
            "  description:",
            "  gender: unspecified",
            "",
            "## Plot points",
            "",
            "- ",
            "",
            "## Ending",
            "",
            "## Style references",
            "",
            "- ",
            "",
            "## Dark themes",
            "",
            "no",
            "",
            "## Synopsis",
            "",
            "## Guessed",
            "",
            "- ",
            "",
        ]
    )


def render_markdown(brief: BookBrief) -> str:
    """Write the brief in the Markdown template."""
    chapters = "" if brief.chapter_count is None else str(brief.chapter_count)
    scenes = "" if brief.scenes_per_chapter is None else str(brief.scenes_per_chapter)
    people = []
    for item in brief.characters:
        people.extend(
            [
                f"- name: {item.name}",
                f"  role: {item.role}",
                f"  description: {item.description}",
                f"  gender: {item.gender}",
            ]
        )
    if not people:
        people = ["- name:", "  role:", "  description:", "  gender: unspecified"]
    points = [f"- {item}" for item in brief.plot_points] or ["- "]
    styles = [f"- {item}" for item in brief.style_references] or ["- "]
    guessed = [f"- {item}" for item in brief.guessed] or ["- "]
    dark = "yes" if brief.dark_themes else "no"
    sections = [
        ("Title", brief.title),
        ("Language", brief.language),
        (
            "Length",
            "\n".join(
                [
                    f"pages: {brief.pages}",
                    f"words_per_page: {brief.words_per_page}",
                    f"chapters: {chapters}",
                    f"scenes_per_chapter: {scenes}",
                ]
            ),
        ),
        ("Genre", brief.genre),
        ("Subgenre", brief.subgenre),
        ("Tone", brief.tone),
        ("Point of view", brief.pov),
        ("Tense", brief.tense),
        ("Audience", brief.audience),
        ("Setting", brief.setting),
        ("Characters", "\n".join(people)),
        ("Plot points", "\n".join(points)),
        ("Ending", brief.ending_type),
        ("Style references", "\n".join(styles)),
        ("Dark themes", dark),
        ("Synopsis", brief.synopsis),
        ("Guessed", "\n".join(guessed)),
    ]
    parts = ["# Book brief", "", "version: 1", ""]
    for heading, body in sections:
        parts.extend([f"## {heading}", "", body, ""])
    return "\n".join(parts).rstrip() + "\n"


def writing_guide_path() -> Path:
    """The writing guide shipped with the app, or the repo copy when developing."""
    packaged = Path(__file__).resolve().parent / "data" / "writing-a-brief.md"
    if packaged.is_file():
        return packaged
    return repo_root() / "docs" / "WRITING-A-BRIEF.md"


def chat_prompt(language: str) -> str:
    """Self-contained instructions that turn a rough idea into this Markdown template."""
    return (
        "You fill a book brief for a novel. The reader will paste a rough idea after "
        "these instructions. Return only the Markdown brief, with the headings exactly "
        "as in the template. Write the prose values in the book language "
        f"({language}). Keep every heading in English. Leave chapters and "
        "scenes_per_chapter empty when you want them derived from the length. "
        "Under ## Guessed, list every field you chose because the idea did not say it. "
        "Do not add a preamble or a code fence.\n\n"
        f"{markdown_template()}"
    )


def _parse_markdown(text: str) -> BookBrief:
    version = BRIEF_VERSION
    for line in text.splitlines():
        if line.lower().startswith("version:"):
            raw = line.split(":", 1)[1].strip()
            if raw and raw != "1":
                raise BriefError([FieldError("version", "version")])
    sections = _sections(text)
    length = sections.get("length", "")
    length_map = _pairs(length)
    payload: dict[str, object] = {
        "version": version,
        "title": sections.get("title", "").strip(),
        "language": sections.get("language", "").strip(),
        "pages": length_map.get("pages", ""),
        "words_per_page": length_map.get("words_per_page", ""),
        "chapter_count": length_map.get("chapters", "") or None,
        "scenes_per_chapter": length_map.get("scenes_per_chapter", "") or None,
        "genre": sections.get("genre", "").strip(),
        "subgenre": sections.get("subgenre", "").strip(),
        "tone": sections.get("tone", "").strip(),
        "pov": sections.get("pov", "").strip(),
        "tense": sections.get("tense", "").strip(),
        "audience": sections.get("audience", "").strip(),
        "setting": sections.get("setting", "").strip(),
        "characters": _character_blocks(sections.get("characters", "")),
        "plot_points": _bullets(sections.get("plot_points", "")),
        "ending_type": sections.get("ending_type", "").strip(),
        "style_references": _bullets(sections.get("style_references", "")),
        "dark_themes": sections.get("dark_themes", "").strip(),
        "synopsis": sections.get("synopsis", "").strip(),
        "guessed": _bullets(sections.get("guessed", "")),
    }
    return brief_from_dict(payload, strict=True)


def _sections(text: str) -> dict[str, str]:
    current = ""
    buckets: dict[str, list[str]] = {}
    for line in text.splitlines():
        if line.startswith("## "):
            heading = line[3:].strip().lower()
            current = _SECTION_TO_FIELD.get(heading, "")
            buckets.setdefault(current, [])
            continue
        if current:
            buckets.setdefault(current, []).append(line)
    return {key: "\n".join(lines).strip() for key, lines in buckets.items() if key}


def _pairs(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        found[key.strip()] = value.strip()
    return found


def _bullets(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if value:
                items.append(value)
    return items


def _character_blocks(text: str) -> list[dict[str, str]]:
    people: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- name:"):
            if current and current.get("name"):
                people.append(current)
            current = {
                "name": stripped.split(":", 1)[1].strip(),
                "role": "",
                "description": "",
                "gender": "unspecified",
            }
            continue
        if current is None or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        if key in {"role", "description", "gender"}:
            current[key] = value.strip()
    if current and current.get("name"):
        people.append(current)
    return people


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_line(idea: str) -> str:
    for line in idea.splitlines():
        if line.strip():
            return line.strip()[:80]
    return ""


def _positive(value: object, name: str, errors: list[FieldError]) -> int:
    if value in (None, ""):
        errors.append(FieldError(name, "required"))
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        errors.append(FieldError(name, "positive"))
        return 0
    try:
        number = int(str(value).strip())
    except ValueError:
        errors.append(FieldError(name, "positive"))
        return 0
    if number <= 0:
        errors.append(FieldError(name, "positive"))
        return 0
    return number


def _optional_positive(value: object, name: str, errors: list[FieldError]) -> int | None:
    if value in (None, ""):
        return None
    number = _positive(value, name, errors)
    if number <= 0:
        return None
    return number


def _bool(value: object, errors: list[FieldError]) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"yes", "true", "1"}:
            return True
        if text in {"no", "false", "0", ""}:
            return False
    if value in (None, ""):
        return False
    errors.append(FieldError("dark_themes", "bool"))
    return False


def _characters(value: object, errors: list[FieldError]) -> list[Character]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        errors.append(FieldError("characters", "list"))
        return []
    people: list[Character] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(FieldError(f"characters[{index}]", "characters"))
            continue
        name = _text(item.get("name"))
        role = _text(item.get("role"))
        description = _text(item.get("description"))
        gender = _text(item.get("gender")).lower() or "unspecified"
        if not name:
            errors.append(FieldError(f"characters[{index}].name", "required"))
            continue
        if gender not in _GENDERS:
            errors.append(FieldError(f"characters[{index}].gender", "gender"))
            continue
        people.append(Character(name, role, description, gender))
    return people


def _str_list(value: object, name: str, errors: list[FieldError]) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        errors.append(FieldError(name, "list"))
        return []
    items: list[str] = []
    for item in value:
        text = _text(item)
        if text:
            items.append(text)
    return items
