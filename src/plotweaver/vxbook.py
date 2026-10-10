"""Voxprint Book (.vxbook) writer and validator. Spec v1.0.

The archive is the Audiobook Builder hand-off. Legacy numbered speaker marks
are produced from the same file by the mapping in section 7 of the spec.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import unicodedata
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from PIL import Image

from plotweaver.appinfo import APP_VERSION
from plotweaver.errors import PlotweaverError, assert_never
from plotweaver.paths import repo_root
from plotweaver.sound import check_sound
from plotweaver.textutil import restore_yo

MIME = b"application/vnd.voxprint.book+zip"
_FORMAT = "1.0"
_APP = "plotweaver"
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_DIRECTIVE = re.compile(r'^<!-- vx:([a-z][a-z0-9_]*)((?: [a-z][a-z0-9_]*="[^"<>]*")*) -->$')
_ATTR = re.compile(r' ([a-z][a-z0-9_]*)="([^"<>]*)"')
_CONF = re.compile(r"^(?:0(?:\.\d{1,2})?|1(?:\.0{1,2})?)$")
_BCP47 = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$")
_VERSION = re.compile(r"^(\d+)\.(\d+)$")
_CREATED = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?Z$")
_ENTITY = re.compile(r"&(?:#x[0-9A-Fa-f]+|#\d+|[A-Za-z][A-Za-z0-9]+);")
_SPAN_STRIP = re.compile(r'</?span(?: data-vx-[a-z]+="[^"]*")*>')
_SOURCE_FORMATS = frozenset({"fb2", "epub", "txt", "md", "plotweaver", "vxbook"})
_GENDERS = frozenset({"male", "female", "unspecified"})
_AGES = frozenset({"child", "teen", "young_adult", "adult", "elderly", "unspecified"})
_PITCH = frozenset({"low", "medium", "high"})
_PACE = frozenset({"slow", "normal", "fast"})
_VOWELS = frozenset("аеиоуыэюяАЕИОУЫЭЮЯ")
_MAX_ENTRIES = 1000
_MAX_TOTAL = 512 * 1024 * 1024
_MAX_BOOK = 64 * 1024 * 1024
_MAX_JSON = 4 * 1024 * 1024
_MAX_COVER = 20 * 1024 * 1024
_MAX_NOTE = 8 * 1024 * 1024
_MAX_RATIO = 100
_MAX_PIXELS = 100_000_000
_MAX_PARAGRAPH = 20_000
_EPOCH = (1980, 1, 1, 0, 0, 0)

_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}

Severity = Literal["error", "warning"]


class BlockKind(StrEnum):
    PARAGRAPH = "paragraph"
    QUOTE = "quote"
    SCENE = "scene"
    SUBHEAD = "subhead"


class CoverStatus(StrEnum):
    OK = "ok"
    UNREADABLE = "unreadable"
    TOO_LARGE = "too_large"


@dataclass(frozen=True)
class VxbookIssue:
    severity: Severity
    message: str


@dataclass(frozen=True)
class VxPart:
    text: str
    speaker_id: str | None = None
    src: str | None = None


@dataclass(frozen=True)
class VxBlock:
    kind: BlockKind
    text: str = ""
    speaker_id: str | None = None
    src: str | None = None
    conf: str | None = None
    parts: tuple[VxPart, ...] = ()


@dataclass
class VxChapter:
    id: str
    title: str
    blocks: list[VxBlock] = field(default_factory=list)


@dataclass(frozen=True)
class VxSpeaker:
    id: str
    role: str
    name: str = ""
    gender: str = "unspecified"
    age_group: str = "unspecified"
    aliases: tuple[str, ...] = ()
    voice_hints: dict[str, str] | None = None


@dataclass(frozen=True)
class VxParagraph:
    """One counted paragraph, in the order Audiobook Builder already uses."""

    index: int
    chapter: str
    raw_line: str
    plain: str
    scene_start: bool
    mirrors: tuple[str, ...] = ()


@dataclass
class _ParsedParagraph:
    speaker_id: str | None
    spans: list[tuple[str, int]]
    raw_line: str = ""
    plain: str = ""
    chapter: str = ""
    scene_start: bool = False
    mirrors: list[str] = field(default_factory=list)


@dataclass
class _ParsedBook:
    paragraphs: list[_ParsedParagraph]
    plain_blocks: list[str]
    chapters: list[tuple[str, str, int]]


@dataclass
class _Cursor:
    chapter: str = ""
    scene_pending: bool = True


def even_utc_now() -> str:
    """UTC timestamp with even seconds, so the ZIP time matches the manifest."""
    now = datetime.now(UTC).replace(microsecond=0)
    if now.second % 2:
        now = now.replace(second=now.second - 1)
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def display_name(name: str) -> str:
    """NFC display name with stress marks and invisible characters removed."""
    text = unicodedata.normalize("NFC", name).replace("\u0301", "")
    kept = [char for char in text if unicodedata.category(char) not in {"Cc", "Cf"}]
    return " ".join("".join(kept).split())


def name_key(value: str) -> str:
    """Match key: NFC, stress removed, spaces collapsed, case folded."""
    return display_name(value).casefold()


def speaker_slug(name: str) -> str:
    """Transliterate a speaker name into the vxbook id grammar."""
    pieces: list[str] = []
    for char in display_name(name).casefold():
        mapped = _TRANSLIT.get(char)
        if mapped is not None:
            pieces.append(mapped)
        elif char.isascii() and char.isalnum():
            pieces.append(char)
        elif char.isspace() or char in "-_":
            pieces.append("-")
    slug = re.sub(r"-{2,}", "-", "".join(pieces)).strip("-_")[:64]
    if _ID.fullmatch(slug):
        return slug
    return ""


def narrator_speaker() -> VxSpeaker:
    return VxSpeaker(id="narrator", role="narrator")


def coerce_age_group(value: object, age: object = None) -> str:
    """Story-bible age_group, or an integer age mapped onto the spec's groups."""
    if isinstance(value, str) and value in _AGES:
        return value
    years = _as_years(age)
    if years is None:
        return "unspecified"
    if years < 13:
        return "child"
    if years < 18:
        return "teen"
    if years < 26:
        return "young_adult"
    if years < 65:
        return "adult"
    return "elderly"


def coerce_hints(value: object, voice: str = "") -> dict[str, str] | None:
    """Keep known voice-hint keys. A free-text bible voice becomes notes."""
    hints: dict[str, str] = {}
    if isinstance(value, dict):
        pitch = value.get("pitch")
        pace = value.get("pace")
        timbre = value.get("timbre")
        notes = value.get("notes")
        if isinstance(pitch, str) and pitch in _PITCH:
            hints["pitch"] = pitch
        if isinstance(pace, str) and pace in _PACE:
            hints["pace"] = pace
        if isinstance(timbre, str) and timbre.strip():
            hints["timbre"] = timbre.strip()
        if isinstance(notes, str) and notes.strip():
            hints["notes"] = notes.strip()
    if "notes" not in hints and voice.strip():
        hints["notes"] = voice.strip()
    return hints or None


def make_character(
    name: str,
    gender: str,
    used: set[str],
    *,
    age_group: str = "unspecified",
    aliases: tuple[str, ...] = (),
    voice_hints: dict[str, str] | None = None,
) -> VxSpeaker:
    cleaned = display_name(name)
    chosen = gender if gender in _GENDERS else "unspecified"
    group = age_group if age_group in _AGES else "unspecified"
    base = speaker_slug(cleaned)
    if not base:
        serial = 1 + sum(1 for item in used if item.startswith(f"{chosen}_"))
        base = f"{chosen}_{serial}"
    return VxSpeaker(
        id=_unique_id(base, used),
        role="character",
        name=cleaned,
        gender=chosen,
        age_group=group,
        aliases=aliases,
        voice_hints=voice_hints,
    )


def with_given_aliases(speakers: Sequence[VxSpeaker]) -> list[VxSpeaker]:
    """Add a given-name alias when that given name belongs to one character."""
    counts: dict[str, int] = {}
    givens: list[tuple[int, str, str]] = []
    for index, speaker in enumerate(speakers):
        parts = speaker.name.split()
        if speaker.role != "character" or len(parts) < 2:
            continue
        key = name_key(parts[0])
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        givens.append((index, parts[0], key))
    updated = list(speakers)
    for index, given, key in givens:
        if counts[key] != 1:
            continue
        speaker = updated[index]
        existing = {name_key(alias) for alias in speaker.aliases}
        if key in existing:
            continue
        updated[index] = VxSpeaker(
            id=speaker.id,
            role=speaker.role,
            name=speaker.name,
            gender=speaker.gender,
            age_group=speaker.age_group,
            aliases=(*speaker.aliases, given),
            voice_hints=speaker.voice_hints,
        )
    return updated


def build_character_speakers(rows: Sequence[Mapping[str, object]]) -> list[VxSpeaker]:
    """speakers.json characters from canon rows plus optional bible fields."""
    used = {"narrator"}
    speakers: list[VxSpeaker] = []
    for row in rows:
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        aliases = _alias_tuple(row.get("aliases"))
        speakers.append(
            make_character(
                name,
                str(row.get("gender") or "unspecified"),
                used,
                age_group=coerce_age_group(row.get("age_group"), row.get("age")),
                aliases=aliases,
                voice_hints=coerce_hints(row.get("voice_hints"), str(row.get("voice") or "")),
            )
        )
    return with_given_aliases(speakers)


def bundled_cover() -> bytes | None:
    """Committed suite cover. Runtime encoding would make the archive drift."""
    candidates: list[Path] = []
    try:
        candidates.append(repo_root() / "branding" / "plotweaver-cover.avif")
    except FileNotFoundError:
        pass
    candidates.append(Path(__file__).resolve().parents[2] / "branding" / "plotweaver-cover.avif")
    for path in candidates:
        if path.is_file():
            return path.read_bytes()
    return None


def pack_vxbook(
    path: Path, manifest: Mapping[str, object], members: Sequence[tuple[str, bytes]]
) -> None:
    """Write a reproducible stored-method archive. ``files`` is recomputed."""
    document: dict[str, object] = dict(manifest)
    ordered = _order_members(members)
    files: dict[str, object] = {}
    for name, data in ordered:
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    document["files"] = files
    payload = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    created = document.get("created")
    stamp = _zip_stamp(created if isinstance(created, str) else "")
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(_zip_info("mimetype", stamp), MIME)
        archive.writestr(_zip_info("manifest.json", stamp), payload)
        for name, data in ordered:
            archive.writestr(_zip_info(name, stamp), data)


def write_vxbook(
    path: Path,
    *,
    title: str,
    author: str,
    language: str,
    chapters: Sequence[VxChapter],
    speakers: Sequence[VxSpeaker],
    created: str = "",
    synopsis: str = "",
    cover: bytes | None = None,
) -> None:
    """Write one .vxbook and refuse to leave it on disk when validation fails."""
    stamp = created or even_utc_now()
    prepared = _prepare_chapters(chapters)
    people = _ensure_narrator(speakers)
    book, chapter_meta = _render_book(prepared, language)
    members: list[tuple[str, bytes]] = [
        ("book.md", book.encode("utf-8")),
        ("speakers.json", _render_speakers(people)),
    ]
    note = _render_note(synopsis)
    if note is not None:
        members.append(("notes/synopsis.md", note))
    image = cover if cover is not None else bundled_cover()
    if image is not None and inspect_cover(image)[0] is CoverStatus.OK:
        members.append(("cover.avif", image))
    manifest: dict[str, object] = {
        "format_version": _FORMAT,
        "title": _one_line(title) or "Untitled",
        "author": _one_line(author),
        "language": language or "ru",
        "created_by": {"app": _APP, "version": APP_VERSION},
        "generator": {"app": _APP, "version": APP_VERSION},
        "created": stamp,
        "source": {"format": "plotweaver"},
        "book": "book.md",
        "speakers": "speakers.json",
        "chapters": [
            {"id": item_id, "title": item_title, "anchor": item_id, "offset": offset}
            for item_id, item_title, offset in chapter_meta
        ],
    }
    if note is not None:
        manifest["notes"] = ["notes/synopsis.md"]
    if any(name == "cover.avif" for name, _data in members):
        manifest["cover"] = "cover.avif"
    pack_vxbook(path, manifest, members)
    problems = [issue.message for issue in validate_vxbook(path) if issue.severity == "error"]
    if problems:
        path.unlink(missing_ok=True)
        raise PlotweaverError("vxbook validation failed:\n" + "\n".join(problems))


def validate_vxbook(path: Path) -> list[VxbookIssue]:
    """Spec section 10. Warnings (offsets, a cover that will not decode) do not fail."""
    issues: list[VxbookIssue] = []
    if not path.is_file():
        return [_err(f"not a file: {path}")]
    with path.open("rb") as handle:
        head = handle.read(80)
    if not head.startswith(b"PK\x03\x04"):
        return [_err("ZIP does not start with a local file header")]
    if head[30:38] != b"mimetype" or head[38:71] != MIME:
        issues.append(
            _err("mimetype is not the stored media type application/vnd.voxprint.book+zip")
        )
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        return [_err(f"ZIP does not open: {exc}")]
    with archive:
        infos = archive.infolist()
        if len(infos) > _MAX_ENTRIES:
            return [_err("archive has more than 1000 entries")]
        if not infos:
            return [_err("archive is empty")]
        first = infos[0]
        if (
            first.filename != "mimetype"
            or first.compress_type != zipfile.ZIP_STORED
            or len(first.extra) != 0
            or first.flag_bits & 0x1
        ):
            issues.append(
                _err("the first entry must be stored mimetype, unencrypted, with no extra field")
            )
        members, read_issues, total = _read_members(archive, infos)
        issues.extend(read_issues)
    if total > _MAX_TOTAL:
        issues.append(_err("uncompressed size exceeds 512 MiB"))
    mime = members.get("mimetype")
    if mime is not None and mime != MIME:
        issues.append(_err("mimetype content is not application/vnd.voxprint.book+zip"))
    if any(issue.severity == "error" for issue in read_issues):
        return issues
    manifest_bytes = members.get("manifest.json")
    book_bytes = members.get("book.md")
    speakers_bytes = members.get("speakers.json")
    if manifest_bytes is None or book_bytes is None or speakers_bytes is None:
        issues.append(_err("manifest.json, book.md, and speakers.json are required"))
        return issues
    _check_listed(members, issues)
    manifest = _load_json(manifest_bytes, "manifest.json", issues)
    if not isinstance(manifest, dict):
        return issues
    version = _version_pair(manifest.get("format_version"))
    if version is None or version[0] != 1:
        issues.append(_err("made by a newer Plotweaver, please update"))
        return issues
    speakers_doc = _load_json(speakers_bytes, "speakers.json", issues)
    if not isinstance(speakers_doc, dict):
        return issues
    speakers_version = speakers_doc.get("format_version")
    if speakers_version != manifest.get("format_version"):
        issues.append(_err("manifest and speakers format_version differ"))
    speaker_version = _version_pair(speakers_version)
    if speaker_version is None or speaker_version[0] != 1:
        issues.append(_err("made by a newer Plotweaver, please update"))
        return issues
    _check_manifest_shape(manifest, members, issues)
    people = _check_speakers(speakers_doc, issues)
    book = _decode_text(book_bytes, "book.md", issues, exact_newline=True)
    if book is None:
        return issues
    language = manifest.get("language")
    lang = language if isinstance(language, str) else ""
    issues.extend(_stress_issues(book, lang, "book.md"))
    stacked = version >= (1, 1)
    _check_extensions(manifest, stacked, issues)
    parsed = _parse_book(book, issues, stacked=stacked)
    _check_chapters(manifest, parsed, issues)
    _check_spans_and_ids(parsed, people, issues)
    _check_cover_notes_cast(manifest, members, people, lang, issues)
    issues.extend(_sound_issues(manifest, members, parsed))
    plain, marks, warnings = _section7(parsed, people)
    for warning in warnings:
        issues.append(_warn(warning))
    if len(marks.splitlines()) != len(parsed.paragraphs):
        issues.append(_err("speaker marks do not have one line per paragraph"))
    del plain
    return issues


def legacy_pair(path: Path) -> tuple[str, str]:
    """Section 7 plain text and numbered speaker marks taken from a .vxbook."""
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise PlotweaverError(f"ZIP does not open: {exc}") from exc
    with archive:
        members, issues, _total = _read_members(archive, archive.infolist())
    errors = [issue.message for issue in issues if issue.severity == "error"]
    if errors:
        raise PlotweaverError(errors[0])
    book = members.get("book.md")
    raw_speakers = members.get("speakers.json")
    if book is None or raw_speakers is None:
        raise PlotweaverError("vxbook is missing book.md or speakers.json")
    text = book.decode("utf-8")
    document = json.loads(raw_speakers.decode("utf-8"))
    rows = document.get("speakers") if isinstance(document, dict) else []
    people = _people(rows if isinstance(rows, list) else [])
    parsed = _parse_book(text, [], stacked=True)
    plain, marks, _warnings = _section7(parsed, people)
    return plain, marks


def inspect_cover(data: bytes) -> tuple[CoverStatus, str]:
    """Decode a cover in memory and enforce the 100 megapixel cap."""
    if not data:
        return CoverStatus.UNREADABLE, "cover is empty"
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = _MAX_PIXELS
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > _MAX_PIXELS:
                return CoverStatus.TOO_LARGE, "cover exceeds 100 megapixels"
            image.load()
            return CoverStatus.OK, f"{width}x{height}"
    except Exception as exc:
        if exc.__class__.__name__ == "DecompressionBombError":
            return CoverStatus.TOO_LARGE, "cover exceeds 100 megapixels"
        return CoverStatus.UNREADABLE, str(exc)
    finally:
        Image.MAX_IMAGE_PIXELS = previous


def _err(message: str) -> VxbookIssue:
    return VxbookIssue("error", message)


def _warn(message: str) -> VxbookIssue:
    return VxbookIssue("warning", message)


def _as_years(age: object) -> int | None:
    if isinstance(age, bool) or age is None:
        return None
    if isinstance(age, int):
        return age
    if isinstance(age, str) and age.strip().isdigit():
        return int(age.strip())
    return None


def _alias_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    aliases: list[str] = []
    for item in value:
        text = display_name(str(item))
        if text:
            aliases.append(text)
    return tuple(aliases)


def _unique_id(base: str, used: set[str]) -> str:
    candidate = base[:64]
    number = 2
    while candidate in used or not _ID.fullmatch(candidate):
        suffix = f"-{number}"
        candidate = base[: 64 - len(suffix)] + suffix
        number += 1
        if number > 10000:
            raise PlotweaverError("could not assign a speaker id")
    used.add(candidate)
    return candidate


def _one_line(text: str) -> str:
    cleaned = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    kept = []
    for char in cleaned:
        category = unicodedata.category(char)
        if char in {"\n", "\t"} or category in {"Cc", "Cf"}:
            kept.append(" ")
        else:
            kept.append(char)
    return " ".join("".join(kept).split())


def _sanitize_prose(text: str, language: str, *, strip: bool = True) -> str:
    flattened = re.sub(r"[^\S\n]*\n[^\S\n]*", " ", text.replace("\r\n", "\n").replace("\r", "\n"))
    if language == "ru":
        flattened = restore_yo(flattened)
    flattened = _keep_legal_marks(flattened, language)
    kept: list[str] = []
    for char in flattened:
        if char in {"\u00a0", "\u2009"}:
            kept.append(char)
            continue
        if char == "\t":
            kept.append(" ")
            continue
        if unicodedata.category(char) in {"Cc", "Cf"}:
            continue
        kept.append(char)
    cleaned = unicodedata.normalize("NFC", "".join(kept))
    return cleaned.strip() if strip else cleaned


def _keep_legal_marks(text: str, language: str) -> str:
    kept: list[str] = []
    marks = 0
    in_word = False
    for char in text:
        if char == "\u0301":
            previous = kept[-1] if kept else ""
            if previous in _VOWELS and marks == 0:
                kept.append(char)
                marks += 1
            continue
        if unicodedata.category(char).startswith("M"):
            if language != "ru":
                kept.append(char)
            continue
        if char.isalpha():
            if not in_word:
                in_word = True
                marks = 0
            kept.append(char)
            continue
        in_word = False
        marks = 0
        kept.append(char)
    return "".join(kept)


def _escape_text(text: str, *, leading: bool) -> str:
    pieces: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            pieces.append("\\\\")
        elif char in {"<", "`", "["}:
            pieces.append("\\" + char)
        elif char == "&" and _ENTITY.match(text, index):
            pieces.append("\\&")
        else:
            pieces.append(char)
        index += 1
    line = "".join(pieces)
    if not leading or not line:
        return line
    ordered = re.match(r"^(\d{1,9})([.)]) ", line)
    if ordered is not None:
        return f"{ordered.group(1)}\\{ordered.group(2)}{line[ordered.end(2) :]}"
    if _needs_leading_escape(line):
        return "\\" + line
    return line


def _needs_leading_escape(line: str) -> bool:
    if line.startswith(("    ", ">", "`", "~")):
        return True
    if line.startswith(("# ", "## ", "### ", "#### ", "##### ", "###### ")):
        return True
    if re.match(r"^[-+*] ", line):
        return True
    compact = line.replace(" ", "")
    return bool(re.fullmatch(r"([-*_])\1{2,}", compact)) and not line.strip(" -*_")


def _render_inline(block: VxBlock, language: str) -> str:
    if not block.parts:
        return _escape_text(_sanitize_prose(block.text, language), leading=True)
    chunks: list[str] = []
    for index, part in enumerate(block.parts):
        inner = _escape_text(
            _sanitize_prose(part.text, language, strip=False),
            leading=index == 0 and part.speaker_id is None,
        )
        if part.speaker_id and any(char.isalpha() for char in inner):
            attrs = f'data-vx-speaker="{part.speaker_id}"'
            if part.src in {"auto", "user"}:
                attrs += f' data-vx-src="{part.src}"'
            chunks.append(f"<span {attrs}>{inner}</span>")
        else:
            chunks.append(inner)
    return "".join(chunks)


def _directive(block: VxBlock) -> str:
    pieces = [f'id="{block.speaker_id}"']
    if block.src in {"auto", "user"}:
        pieces.append(f'src="{block.src}"')
    if block.conf and _CONF.fullmatch(block.conf):
        pieces.append(f'conf="{block.conf}"')
    return f"<!-- vx:speaker {' '.join(pieces)} -->"


def _render_block(block: VxBlock, language: str) -> str:
    match block.kind:
        case BlockKind.SCENE:
            return "* * *"
        case BlockKind.SUBHEAD:
            return f"## {_one_line(block.text) or 'Section'}"
        case BlockKind.PARAGRAPH | BlockKind.QUOTE:
            body = _render_inline(block, language)
            if not body:
                return ""
            line = f"> {body}" if block.kind is BlockKind.QUOTE else body
            if block.speaker_id and block.speaker_id != "narrator":
                return _directive(block) + "\n" + line
            return line
        case _ as unreachable:
            assert_never(unreachable)


def _prepare_chapters(chapters: Sequence[VxChapter]) -> list[VxChapter]:
    source = list(chapters) or [VxChapter("ch01", "Chapter")]
    used: set[str] = set()
    prepared: list[VxChapter] = []
    for index, chapter in enumerate(source, start=1):
        fallback = f"ch{index:02d}"
        raw = chapter.id.strip().lower()
        base = raw if _ID.fullmatch(raw) else speaker_slug(chapter.id) or fallback
        prepared.append(
            VxChapter(
                id=_unique_id(base, used),
                title=_one_line(chapter.title) or "Chapter",
                blocks=list(chapter.blocks),
            )
        )
    return prepared


def _ensure_narrator(speakers: Sequence[VxSpeaker]) -> list[VxSpeaker]:
    people = list(speakers)
    if not any(speaker.id == "narrator" for speaker in people):
        people.insert(0, narrator_speaker())
    return people


def _render_book(
    chapters: Sequence[VxChapter], language: str
) -> tuple[str, list[tuple[str, str, int]]]:
    pieces: list[str] = []
    meta: list[tuple[str, str, int]] = []
    for chapter in chapters:
        if pieces:
            pieces.append("\n\n")
        offset = sum(len(piece.encode("utf-8")) for piece in pieces)
        pieces.append(f'<!-- vx:chapter id="{chapter.id}" -->\n# {chapter.title}')
        meta.append((chapter.id, chapter.title, offset))
        for block in chapter.blocks:
            rendered = _render_block(block, language).rstrip()
            if not rendered:
                continue
            pieces.append("\n\n")
            pieces.append(rendered)
    return "".join(pieces) + "\n", meta


def _speaker_dict(speaker: VxSpeaker) -> dict[str, object]:
    payload: dict[str, object] = {"id": speaker.id, "role": speaker.role}
    if speaker.name:
        payload["name"] = speaker.name
    if speaker.aliases:
        payload["aliases"] = list(speaker.aliases)
    payload["gender"] = speaker.gender if speaker.gender in _GENDERS else "unspecified"
    payload["age_group"] = speaker.age_group if speaker.age_group in _AGES else "unspecified"
    if speaker.voice_hints:
        payload["voice_hints"] = speaker.voice_hints
    return payload


def _render_speakers(speakers: Sequence[VxSpeaker]) -> bytes:
    payload = {"format_version": _FORMAT, "speakers": [_speaker_dict(item) for item in speakers]}
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _render_note(synopsis: str) -> bytes | None:
    text = synopsis.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    kept: list[str] = []
    for char in text:
        if char == "\n" or char in {"\u00a0", "\u2009"}:
            kept.append(char)
        elif unicodedata.category(char) in {"Cc", "Cf"}:
            continue
        else:
            kept.append(char)
    cleaned = unicodedata.normalize("NFC", "".join(kept)).strip()
    if not cleaned:
        return None
    return (cleaned + "\n").encode("utf-8")


def _order_members(members: Sequence[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    skipped = {"mimetype", "manifest.json"}
    kept = [item for item in members if item[0] not in skipped]
    return sorted(kept, key=_rank)


def _rank(item: tuple[str, bytes]) -> tuple[int, str]:
    name = item[0]
    if name == "book.md":
        return (2, name)
    if name == "speakers.json":
        return (3, name)
    if name == "cast.json":
        return (4, name)
    if name == "sound.json":
        return (5, name)
    if name == "sound-cast.json":
        return (6, name)
    if name in {"cover.avif", "cover.jpg"}:
        return (7, name)
    if name.startswith("notes/"):
        return (8, name)
    if name == "narration.json":
        return (10, name)
    return (9, name)


def _zip_stamp(created: str) -> tuple[int, int, int, int, int, int]:
    match = _CREATED.fullmatch(created.strip())
    if match is None:
        return _EPOCH
    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    second -= second % 2
    return (year, month, day, hour, minute, second)


def _zip_info(name: str, stamp: tuple[int, int, int, int, int, int]) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(filename=name, date_time=stamp)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 0
    info.create_version = 20
    info.extract_version = 20
    info.external_attr = 0o644 << 16
    info.extra = b""
    return info


def _entry_cap(name: str) -> int:
    if name == "book.md":
        return _MAX_BOOK
    if name in {"cover.avif", "cover.jpg"}:
        return _MAX_COVER
    if name.startswith("notes/") and name.endswith(".md"):
        return _MAX_NOTE
    if name.endswith(".json"):
        return _MAX_JSON
    return _MAX_BOOK


def _name_problem(name: str) -> str | None:
    if not name or name.startswith("/") or "\\" in name or "\x00" in name:
        return f"unsafe entry name {name!r}"
    if re.search(r"[\x00-\x1f]", name) or re.match(r"^[A-Za-z]:", name):
        return f"unsafe entry name {name!r}"
    body = name[:-1] if name.endswith("/") else name
    if any(part in {"", ".", ".."} for part in body.split("/")):
        return f"unsafe entry name {name!r}"
    return None


def _special_file(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    special = {stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK, stat.S_IFCHR, stat.S_IFBLK}
    return stat.S_IFMT(mode) in special


def _read_members(
    archive: zipfile.ZipFile, infos: Sequence[zipfile.ZipInfo]
) -> tuple[dict[str, bytes], list[VxbookIssue], int]:
    issues: list[VxbookIssue] = []
    members: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    for info in infos:
        folded = info.filename.casefold()
        if folded in seen:
            issues.append(_err(f"duplicate entry name {info.filename}"))
            continue
        seen.add(folded)
        problem = _name_problem(info.filename)
        if problem is not None:
            issues.append(_err(problem))
            continue
        if info.flag_bits & 0x1:
            issues.append(_err(f"encrypted entry {info.filename}"))
            continue
        if info.compress_type not in {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}:
            issues.append(_err(f"compression method {info.compress_type} is not allowed"))
            continue
        if _special_file(info):
            issues.append(_err(f"special file {info.filename}"))
            continue
        if info.is_dir():
            continue
        data, problem = _read_capped(archive, info)
        if problem is not None:
            issues.append(_err(problem))
            return members, issues, total
        total += len(data)
        if total > _MAX_TOTAL:
            issues.append(_err("uncompressed size exceeds 512 MiB"))
            return members, issues, total
        members[info.filename] = data
    return members, issues, total


def _read_capped(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[bytes, str | None]:
    cap = _entry_cap(info.filename)
    allowed = cap
    if info.compress_type == zipfile.ZIP_DEFLATED:
        allowed = min(cap, max(info.compress_size, 1) * _MAX_RATIO)
    chunks: list[bytes] = []
    size = 0
    with archive.open(info, "r") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > allowed or size > cap:
                return b"", f"{info.filename} exceeds the size or compression-ratio limit"
            chunks.append(chunk)
    if info.compress_type == zipfile.ZIP_DEFLATED and info.compress_size == 0 and size:
        return b"", f"{info.filename} exceeds the compression-ratio limit"
    return b"".join(chunks), None


def _check_listed(members: Mapping[str, bytes], issues: list[VxbookIssue]) -> None:
    raw = members.get("manifest.json")
    if raw is None:
        return
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except UnicodeError, json.JSONDecodeError:
        return
    if not isinstance(manifest, dict):
        return
    files = manifest.get("files")
    listed = files if isinstance(files, dict) else {}
    for name, data in members.items():
        if name in {"mimetype", "manifest.json"}:
            if name in listed:
                issues.append(_err(f"{name} must not be listed in files"))
            continue
        record = listed.get(name)
        if not isinstance(record, dict):
            issues.append(_err(f"{name} is missing from files"))
            continue
        digest = record.get("sha256")
        size = record.get("size")
        if digest != hashlib.sha256(data).hexdigest() or size != len(data):
            issues.append(_err(f"files entry for {name} does not match the bytes"))
    for name in listed:
        if name not in members:
            issues.append(_err(f"files lists missing entry {name}"))


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key}")
        result[key] = value
    return result


def _load_json(data: bytes, label: str, issues: list[VxbookIssue]) -> object | None:
    if data.startswith(b"\xef\xbb\xbf"):
        issues.append(_err(f"{label} has a BOM"))
        return None
    if len(data) > _MAX_JSON:
        issues.append(_err(f"{label} exceeds 4 MiB"))
        return None
    try:
        text = data.decode("utf-8")
        parsed: object = json.loads(text, object_pairs_hook=_object_pairs)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        issues.append(_err(f"{label} is not UTF-8 JSON: {exc}"))
        return None
    if _json_depth(parsed) > 32:
        issues.append(_err(f"{label} is nested deeper than 32 levels"))
        return None
    return parsed


def _json_depth(value: object, level: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return level + 1
        return max(_json_depth(item, level + 1) for item in value.values())
    if isinstance(value, list):
        if not value:
            return level + 1
        return max(_json_depth(item, level + 1) for item in value)
    return level


def _version_pair(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = _VERSION.fullmatch(value)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _check_manifest_shape(
    manifest: Mapping[str, object], members: Mapping[str, bytes], issues: list[VxbookIssue]
) -> None:
    title = manifest.get("title")
    author = manifest.get("author")
    language = manifest.get("language")
    if not isinstance(title, str) or unicodedata.normalize("NFC", title) != title:
        issues.append(_err("title must be an NFC string"))
    if not isinstance(author, str):
        issues.append(_err("author must be a string"))
    if not isinstance(language, str) or not _BCP47.fullmatch(language):
        issues.append(_err("language must be a BCP 47 tag"))
    for key in ("created_by", "generator"):
        block = manifest.get(key)
        if key == "generator" and block is None:
            continue
        app = block.get("app") if isinstance(block, dict) else None
        version = block.get("version") if isinstance(block, dict) else None
        if not isinstance(app, str) or not isinstance(version, str):
            issues.append(_err(f"{key} must be an object with app and version"))
    if manifest.get("book") != "book.md" or manifest.get("speakers") != "speakers.json":
        issues.append(_err("book must be book.md and speakers must be speakers.json"))
    created = manifest.get("created")
    if created is None:
        issues.append(_warn("created is missing"))
    elif not isinstance(created, str) or _CREATED.fullmatch(created) is None:
        issues.append(_warn("created is not an ISO-8601 UTC timestamp"))
    source = manifest.get("source")
    if source is not None:
        if not isinstance(source, dict) or source.get("format") not in _SOURCE_FORMATS:
            issues.append(_err("source.format is not one of the listed values"))
        filename = source.get("filename") if isinstance(source, dict) else None
        path_like = not isinstance(filename, str) or "/" in filename or "\\" in filename
        if filename is not None and path_like:
            issues.append(_err("source.filename must be a name with no path"))
    chapters = manifest.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        issues.append(_err("chapters must list at least one chapter"))
    cover_name = _cover_name(members)
    cover = manifest.get("cover")
    if cover_name and cover != cover_name:
        issues.append(_err("manifest.cover must name the cover entry"))
    if isinstance(cover, str) and cover not in members:
        issues.append(_err("manifest.cover does not match an entry"))
    notes = manifest.get("notes")
    note_entries = {name for name in members if name.startswith("notes/") and name.endswith(".md")}
    listed = {str(item) for item in notes} if isinstance(notes, list) else set()
    if notes is None and note_entries:
        issues.append(_err("notes entries must be listed in manifest.notes"))
    elif notes is not None and listed != note_entries:
        issues.append(_err("manifest.notes must list the notes entries"))


def _cover_name(members: Mapping[str, bytes]) -> str:
    found = [name for name in ("cover.avif", "cover.jpg") if name in members]
    if len(found) > 1:
        return ""
    return found[0] if found else ""


def _check_speakers(
    document: Mapping[str, object], issues: list[VxbookIssue]
) -> dict[str, dict[str, object]]:
    rows = document.get("speakers")
    if not isinstance(rows, list):
        issues.append(_err("speakers must be an array"))
        return {}
    people = _people(rows)
    narrators = [
        item
        for item in people.values()
        if item.get("id") == "narrator" or item.get("role") == "narrator"
    ]
    if len(narrators) != 1 or people.get("narrator", {}).get("role") != "narrator":
        issues.append(_err("speakers.json needs exactly one narrator entry"))
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            issues.append(_err("each speaker must be an object"))
            continue
        sid = row.get("id")
        if not isinstance(sid, str) or not _ID.fullmatch(sid):
            issues.append(_err("speaker id does not match the grammar"))
            continue
        if sid in seen:
            issues.append(_err(f"duplicate speaker id {sid}"))
        seen.add(sid)
        if row.get("role") not in {"narrator", "character"}:
            issues.append(_err(f"speaker {sid} role must be narrator or character"))
        if row.get("gender") not in _GENDERS:
            issues.append(_err(f"speaker {sid} gender must be male, female, or unspecified"))
        if row.get("age_group") not in _AGES:
            issues.append(_err(f"speaker {sid} age_group is not a known value"))
        _check_hints(sid, row.get("voice_hints"), issues)
    return people


def _people(rows: object) -> dict[str, dict[str, object]]:
    people: dict[str, dict[str, object]] = {}
    if not isinstance(rows, list):
        return people
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("id"), str):
            people[str(row["id"])] = row
    return people


def _check_hints(sid: str, value: object, issues: list[VxbookIssue]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(_err(f"speaker {sid} voice_hints must be an object"))
        return
    pitch = value.get("pitch")
    pace = value.get("pace")
    if pitch is not None and pitch not in _PITCH:
        issues.append(_err(f"speaker {sid} pitch is not low, medium, or high"))
    if pace is not None and pace not in _PACE:
        issues.append(_err(f"speaker {sid} pace is not slow, normal, or fast"))


def _decode_text(
    data: bytes, label: str, issues: list[VxbookIssue], *, exact_newline: bool
) -> str | None:
    if data.startswith(b"\xef\xbb\xbf"):
        issues.append(_err(f"{label} has a BOM"))
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        issues.append(_err(f"{label} is not UTF-8"))
        return None
    if "\r" in text:
        issues.append(_err(f"{label} must use LF line endings"))
    if exact_newline and (not text.endswith("\n") or text.endswith("\n\n")):
        issues.append(_err(f"{label} must end with exactly one newline"))
    elif not exact_newline and not text.endswith("\n"):
        issues.append(_err(f"{label} must end with a newline"))
    if unicodedata.normalize("NFC", text) != text:
        issues.append(_err(f"{label} is not NFC"))
    for char in text:
        if char == "\n" or char in {"\u00a0", "\u2009"}:
            continue
        if unicodedata.category(char) in {"Cc", "Cf"}:
            issues.append(_err(f"{label} contains a forbidden character"))
            break
    return text


def _stress_issues(text: str, language: str, label: str) -> list[VxbookIssue]:
    marks = 0
    in_word = False
    previous = ""
    for char in text:
        if char == "\u0301":
            if previous not in _VOWELS or marks >= 1:
                return [_err(f"{label} has a stress mark that is not on one allowed vowel")]
            marks += 1
            previous = char
            continue
        if unicodedata.category(char).startswith("M"):
            if language == "ru":
                return [_err(f"{label} has a combining mark other than U+0301")]
            previous = char
            continue
        if char.isalpha():
            if not in_word:
                in_word = True
                marks = 0
            previous = char
            continue
        in_word = False
        marks = 0
        previous = char
    return []


def read_archive(path: Path) -> tuple[dict[str, object], dict[str, bytes]]:
    """Read a .vxbook into memory. Raises when the archive itself is unsafe."""
    if not path.is_file():
        raise PlotweaverError(f"not a file: {path}")
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise PlotweaverError(f"ZIP does not open: {exc}") from exc
    with archive:
        members, issues, _total = _read_members(archive, archive.infolist())
    errors = [issue.message for issue in issues if issue.severity == "error"]
    if errors:
        raise PlotweaverError(errors[0])
    raw = members.get("manifest.json")
    if raw is None:
        raise PlotweaverError("manifest.json is missing")
    loaded: list[VxbookIssue] = []
    manifest = _load_json(raw, "manifest.json", loaded)
    if not isinstance(manifest, dict):
        message = loaded[0].message if loaded else "manifest.json is invalid"
        raise PlotweaverError(message)
    return manifest, members


def paragraph_map(text: str) -> list[VxParagraph]:
    """Counted paragraphs, including v1.1 stacked directives."""
    parsed = _parse_book(text, [], stacked=True)
    return [
        VxParagraph(
            index,
            paragraph.chapter,
            paragraph.raw_line,
            paragraph.plain,
            paragraph.scene_start,
            tuple(paragraph.mirrors),
        )
        for index, paragraph in enumerate(parsed.paragraphs, start=1)
    ]


def _check_extensions(
    manifest: Mapping[str, object], stacked: bool, issues: list[VxbookIssue]
) -> None:
    extensions = manifest.get("extensions")
    if extensions is None:
        return
    if not stacked:
        issues.append(_err("extensions require format_version 1.1"))
    if not isinstance(extensions, list) or any(not isinstance(item, str) for item in extensions):
        issues.append(_err("extensions must be an array of strings"))


def _sound_issues(
    manifest: Mapping[str, object], members: Mapping[str, bytes], parsed: _ParsedBook
) -> list[VxbookIssue]:
    rows: list[dict[str, object]] = []
    for index, paragraph in enumerate(parsed.paragraphs, start=1):
        rows.append(
            {
                "index": index,
                "chapter": paragraph.chapter,
                "raw_line": paragraph.raw_line,
                "plain": paragraph.plain,
                "scene_start": paragraph.scene_start,
                "mirrors": list(paragraph.mirrors),
            }
        )
    found = check_sound(manifest, members, rows)
    issues: list[VxbookIssue] = []
    for item in found:
        if item.severity == "error":
            issues.append(_err(item.message))
        else:
            issues.append(_warn(item.message))
    return issues


def _parse_book(text: str, issues: list[VxbookIssue], *, stacked: bool = False) -> _ParsedBook:
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    offsets: list[int] = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line.encode("utf-8")) + 1
    parsed = _ParsedBook([], [], [])
    place = _Cursor()
    index = 0
    while index < len(lines):
        if lines[index] == "":
            issues.append(_err("book.md has a blank line in the wrong place"))
            index += 1
            continue
        start = index
        while index < len(lines) and lines[index] != "":
            if lines[index].endswith(" ") or lines[index].endswith("\t"):
                issues.append(_err("book.md line has trailing spaces"))
            index += 1
        block_offset = offsets[start] if start < len(offsets) else 0
        _interpret_block(lines[start:index], block_offset, parsed, issues, place, stacked=stacked)
        if index < len(lines):
            index += 1
            while index < len(lines) and lines[index] == "":
                issues.append(_err("book.md has more than one blank line between blocks"))
                index += 1
    if not parsed.chapters:
        issues.append(_err("book.md must start with a vx:chapter directive"))
    return parsed


def _interpret_block(
    lines: list[str],
    offset: int,
    parsed: _ParsedBook,
    issues: list[VxbookIssue],
    place: _Cursor,
    *,
    stacked: bool,
) -> None:
    directives: list[tuple[str, dict[str, str]]] = []
    index = 0
    while index < len(lines):
        found = _parse_directive(lines[index])
        if found is None:
            break
        directives.append(found)
        index += 1
    body = lines[index:]
    if not directives:
        if lines and lines[0].startswith("<!--"):
            issues.append(_err("malformed directive"))
            return
        if len(lines) != 1:
            issues.append(_err("a block must be one line, or a directive plus one line"))
            return
        line = lines[0]
        if line == "* * *":
            place.scene_pending = True
            parsed.plain_blocks.append(line)
            return
        if line.startswith("## ") and not line.startswith("###"):
            parsed.plain_blocks.append(line)
            return
        _add_paragraph(line, None, {}, parsed, issues, place, [])
        return
    if not stacked and len(directives) > 1:
        issues.append(_err("stacked directives require format_version 1.1"))
    if len(body) != 1:
        issues.append(_err("a block must be one line, or a directive plus one line"))
        return
    content = body[0]
    if content.startswith("<!--"):
        issues.append(_err("malformed directive"))
        return
    mirrors: list[str] = []
    for name, attrs in directives[:-1]:
        _leading_directive(name, attrs, mirrors, issues)
    last_name, last_attrs = directives[-1]
    heading = content.startswith("# ") and not content.startswith("##")
    if last_name == "chapter" and heading:
        _add_chapter(last_attrs, content[2:], offset, parsed, issues, place)
        return
    if last_name == "chapter":
        issues.append(_err("vx:chapter is not attached to the following block"))
        return
    if last_name == "speaker":
        speaker_id = last_attrs.get("id", "")
        if not _ID.fullmatch(speaker_id):
            issues.append(_err("vx:speaker id does not match the grammar"))
        _add_paragraph(content, speaker_id or None, last_attrs, parsed, issues, place, mirrors)
        return
    if last_name == "sound":
        _leading_directive("sound", last_attrs, mirrors, issues)
    elif last_name not in {"speaker", "chapter"}:
        issues.append(_warn(f"ignored unknown directive vx:{last_name}"))
    _add_paragraph(content, None, {}, parsed, issues, place, mirrors)


def _leading_directive(
    name: str, attrs: dict[str, str], mirrors: list[str], issues: list[VxbookIssue]
) -> None:
    if name == "sound":
        cue = attrs.get("cue", "")
        if _ID.fullmatch(cue):
            mirrors.append(cue)
        else:
            issues.append(_warn("vx:sound cue does not match the grammar"))
        return
    if name == "speaker":
        issues.append(_err("vx:speaker must be the last directive before a paragraph"))
        return
    if name == "chapter":
        issues.append(_err("vx:chapter must be the last directive before a heading"))
        return
    issues.append(_warn(f"ignored unknown directive vx:{name}"))


def _add_chapter(
    attrs: dict[str, str],
    title: str,
    offset: int,
    parsed: _ParsedBook,
    issues: list[VxbookIssue],
    place: _Cursor,
) -> None:
    chapter_id = attrs.get("id", "")
    if not _ID.fullmatch(chapter_id):
        issues.append(_err("vx:chapter id does not match the grammar"))
    if any(item[0] == chapter_id for item in parsed.chapters):
        issues.append(_err(f"duplicate chapter id {chapter_id}"))
    if not title.strip():
        issues.append(_err("chapter heading is empty"))
    parsed.chapters.append((chapter_id, title, offset))
    parsed.plain_blocks.append(f"# {title}")
    place.chapter = chapter_id
    place.scene_pending = True


def _add_paragraph(
    line: str,
    speaker_id: str | None,
    attrs: dict[str, str],
    parsed: _ParsedBook,
    issues: list[VxbookIssue],
    place: _Cursor,
    mirrors: list[str],
) -> None:
    if not line.strip():
        issues.append(_err("empty paragraph"))
        return
    if len(line) > _MAX_PARAGRAPH:
        issues.append(_err("paragraph exceeds 20000 characters"))
    reason = _forbidden_line(line)
    if reason is not None:
        issues.append(_err(f"book.md contains {reason}"))
    _check_attrs(attrs, issues)
    spans = _scan_spans(line, issues)
    plain = _SPAN_STRIP.sub("", line)
    if plain.startswith("> "):
        plain = plain[2:]
    if not plain.strip():
        issues.append(_err("empty paragraph"))
        return
    parsed.paragraphs.append(
        _ParsedParagraph(
            speaker_id,
            spans,
            raw_line=line,
            plain=_at_text_plain(line),
            chapter=place.chapter,
            scene_start=place.scene_pending,
            mirrors=list(mirrors),
        )
    )
    place.scene_pending = False
    parsed.plain_blocks.append(plain)


def _at_text_plain(line: str) -> str:
    """Paragraph text the way an at_text snippet is matched."""
    text = line[2:] if line.startswith("> ") else line
    text = _SPAN_STRIP.sub("", text)
    chars: list[str] = []
    index = 0
    while index < len(text):
        if text[index] == "\\" and index + 1 < len(text):
            chars.append(text[index + 1])
            index += 2
            continue
        if text[index] != "*":
            chars.append(text[index])
        index += 1
    return "".join(chars).replace("\u0301", "")


def _forbidden_line(line: str) -> str | None:
    if line.startswith("\\") or line.startswith("> ") or line.startswith("<span "):
        return None
    if line.startswith("###"):
        return "a heading above level 2"
    if line.startswith(("```", "~~~")) or line.startswith("    "):
        return "a code block"
    if re.match(r"^[-+*] ", line) or re.match(r"^\d{1,9}[.)] ", line):
        return "a list"
    if line.startswith("#"):
        return "a heading that is not attached to vx:chapter"
    compact = line.replace(" ", "")
    if re.fullmatch(r"([-*_])\1{2,}", compact):
        return "a thematic break other than * * *"
    return None


def _check_attrs(attrs: Mapping[str, str], issues: list[VxbookIssue]) -> None:
    src = attrs.get("src")
    conf = attrs.get("conf")
    if src is not None and src not in {"auto", "user"}:
        issues.append(_err('src must be "auto" or "user"'))
    if conf is not None and _CONF.fullmatch(conf) is None:
        issues.append(_err("conf must be from 0 to 1 with at most two decimals"))
    for key, value in attrs.items():
        if key not in {"id", "src", "conf"}:
            issues.append(_warn(f"ignored unknown directive key {key}"))
        if "--" in value:
            issues.append(_err("a directive value contains --"))


def _parse_directive(line: str) -> tuple[str, dict[str, str]] | None:
    match = _DIRECTIVE.fullmatch(line)
    if match is None:
        return None
    attrs: dict[str, str] = {}
    for key, value in _ATTR.findall(match.group(2)):
        attrs[key] = value
    return match.group(1), attrs


def _scan_spans(line: str, issues: list[VxbookIssue]) -> list[tuple[str, int]]:
    spans: list[tuple[str, int]] = []
    index = 0
    depth = 0
    inner_at = 0
    speaker = ""
    while index < len(line):
        if line.startswith("\\", index) and index + 1 < len(line):
            index += 2
            continue
        if line.startswith("</span>", index):
            if depth != 1:
                issues.append(_err("span is not well-formed"))
                return spans
            inner = line[inner_at:index]
            if not any(char.isalpha() for char in inner):
                issues.append(_err("span must contain a letter"))
            spans.append((speaker, len(inner)))
            depth = 0
            index += len("</span>")
            continue
        if line.startswith("<span", index):
            if depth:
                issues.append(_err("spans must not nest"))
                return spans
            end = line.find(">", index)
            if end < 0:
                issues.append(_err("span is not well-formed"))
                return spans
            opened = _open_span(line[index : end + 1], issues)
            if opened is None:
                return spans
            speaker = opened
            depth = 1
            inner_at = end + 1
            index = end + 1
            continue
        if line[index] == "<":
            issues.append(_err("HTML other than a speaker span is not allowed"))
            return spans
        if line[index] == "&" and _ENTITY.match(line, index):
            issues.append(_err("entity references are not allowed"))
        if line[index] in {"`", "["}:
            issues.append(_err("code spans and links are not allowed"))
        index += 1
    if depth:
        issues.append(_err("span is not closed"))
    return spans


def _open_span(tag: str, issues: list[VxbookIssue]) -> str | None:
    match = re.fullmatch(r'<span((?: data-vx-[a-z]+="[^"]*")*)>', tag)
    if match is None:
        issues.append(_err("span is not well-formed"))
        return None
    attrs = re.findall(r' (data-vx-[a-z]+)="([^"]*)"', match.group(1))
    if not attrs or attrs[0][0] != "data-vx-speaker":
        issues.append(_err("span must start with data-vx-speaker"))
        return None
    speaker = str(attrs[0][1])
    if not _ID.fullmatch(speaker):
        issues.append(_err("span speaker id does not match the grammar"))
    for key, value in attrs[1:]:
        if key == "data-vx-src" and value not in {"auto", "user"}:
            issues.append(_err('span src must be "auto" or "user"'))
        elif key == "data-vx-conf" and _CONF.fullmatch(value) is None:
            issues.append(_err("span conf must be from 0 to 1 with at most two decimals"))
        elif key not in {"data-vx-src", "data-vx-conf"}:
            issues.append(_warn(f"ignored unknown span attribute {key}"))
    return speaker


def _check_chapters(
    manifest: Mapping[str, object], parsed: _ParsedBook, issues: list[VxbookIssue]
) -> None:
    rows = manifest.get("chapters")
    if not isinstance(rows, list):
        return
    if len(rows) != len(parsed.chapters):
        issues.append(_err("manifest chapters do not match book.md"))
    for expected, found in zip(rows, parsed.chapters, strict=False):
        if not isinstance(expected, dict):
            issues.append(_err("each chapter must be an object"))
            continue
        chapter_id, title, offset = found
        if expected.get("id") != chapter_id or expected.get("anchor") != chapter_id:
            issues.append(_err(f"chapter {chapter_id} does not match its manifest id and anchor"))
        if expected.get("title") != title:
            issues.append(_err(f"chapter {chapter_id} title does not match the heading"))
        stated = expected.get("offset")
        if not isinstance(stated, int) or isinstance(stated, bool):
            issues.append(_warn(f"chapter {chapter_id} offset is missing"))
        elif stated != offset:
            issues.append(
                _warn(f"chapter {chapter_id} offset {stated} does not match byte {offset}")
            )


def _check_spans_and_ids(
    parsed: _ParsedBook, people: Mapping[str, Mapping[str, object]], issues: list[VxbookIssue]
) -> None:
    known = set(people)
    for paragraph in parsed.paragraphs:
        if paragraph.speaker_id is not None and paragraph.speaker_id not in known:
            issues.append(_err(f"speaker {paragraph.speaker_id} is not listed"))
        for sid, _count in paragraph.spans:
            if sid not in known:
                issues.append(_err(f"speaker {sid} is not listed"))


def _check_cover_notes_cast(
    manifest: Mapping[str, object],
    members: Mapping[str, bytes],
    people: Mapping[str, Mapping[str, object]],
    language: str,
    issues: list[VxbookIssue],
) -> None:
    covers = [name for name in ("cover.avif", "cover.jpg") if name in members]
    if len(covers) > 1:
        issues.append(_err("a book has at most one cover"))
    for name in covers:
        status, detail = inspect_cover(members[name])
        match status:
            case CoverStatus.OK:
                width, height = (int(part) for part in detail.split("x"))
                if max(width, height) < 1400 or max(width, height) > 3000:
                    issues.append(_warn("cover long side should be between 1400 and 3000 px"))
            case CoverStatus.UNREADABLE:
                issues.append(_warn(f"cover did not decode: {detail}"))
            case CoverStatus.TOO_LARGE:
                issues.append(_err(detail))
            case _ as unreachable:
                assert_never(unreachable)
    for name, data in members.items():
        if name.startswith("notes/") and name.endswith(".md"):
            _decode_text(data, name, issues, exact_newline=False)
            text = data.decode("utf-8", errors="replace")
            issues.extend(_stress_issues(text, language, name))
    names = [info_name for info_name in members if info_name == "narration.json"]
    if names:
        ordered = list(members)
        if ordered[-1] != "narration.json":
            issues.append(_err("narration.json must be the last entry"))
    cast_raw = members.get("cast.json")
    if cast_raw is None:
        return
    document = _load_json(cast_raw, "cast.json", issues)
    if not isinstance(document, dict):
        return
    cast = document.get("cast")
    if not isinstance(cast, dict):
        issues.append(_err("cast.json needs a cast object"))
        return
    for key, value in cast.items():
        if key not in people:
            issues.append(_err(f"cast key {key} is not a speaker id"))
            continue
        if not isinstance(value, dict) or value.get("library") != "voxprint":
            issues.append(_err(f"cast entry {key} must use library voxprint"))


def _section7(
    parsed: _ParsedBook, people: Mapping[str, Mapping[str, object]]
) -> tuple[str, str, list[str]]:
    marks: list[str] = []
    warnings: list[str] = []
    for index, paragraph in enumerate(parsed.paragraphs, start=1):
        sid = paragraph.speaker_id
        if sid is None and paragraph.spans:
            sid = _dominant(paragraph.spans)
        if not sid:
            sid = "narrator"
        mark, warning = _mark_for(sid, people)
        if warning:
            warnings.append(warning)
        marks.append(f"{index}. {mark}")
    plain = "\n\n".join(parsed.plain_blocks) + ("\n" if parsed.plain_blocks else "")
    marks_text = ("\n".join(marks) + "\n") if marks else ""
    return plain, marks_text, warnings


def _dominant(spans: Sequence[tuple[str, int]]) -> str:
    best_id = spans[0][0]
    best_count = spans[0][1]
    for sid, count in spans[1:]:
        if count > best_count:
            best_id = sid
            best_count = count
    return best_id


def _mark_for(sid: str, people: Mapping[str, Mapping[str, object]]) -> tuple[str, str]:
    if sid == "narrator":
        return "NARRATOR", ""
    person = people.get(sid, {})
    gender = str(person.get("gender") or "unspecified")
    name = str(person.get("name") or "").strip()
    if gender == "male":
        return ("MALE: " + name) if name else "MALE", ""
    if gender == "female":
        return ("FEMALE: " + name) if name else "FEMALE", ""
    return "NARRATOR", f"speaker {sid} has gender unspecified; the mark is NARRATOR"
