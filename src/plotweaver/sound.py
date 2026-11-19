"""VXBOOK v1.1 + sound extension v1 (`sound/1`).

Schema, checks, and the Add sound markup writer live here so a later
minor tweak stays in one module. Plotweaver never generates audio.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from plotweaver.appinfo import APP_VERSION
from plotweaver.errors import PlotweaverError
from plotweaver.gpu_lock import gpu_job

if TYPE_CHECKING:
    from plotweaver.llm import LLMBackend

EXTENSION = "sound/1"
SOUND_VERSION = "1.0"
FORMAT_VERSION = "1.1"
_APP = "plotweaver"
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_VERSION = re.compile(r"^(\d+)\.(\d+)$")
_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
_MOODS = frozenset(
    {
        "neutral",
        "calm",
        "warm",
        "joyful",
        "playful",
        "romantic",
        "melancholic",
        "mysterious",
        "tense",
        "ominous",
        "horror",
        "action",
        "triumphant",
    }
)
_KINDS = frozenset({"bed", "accent", "transition", "sfx"})
_LAYERS = frozenset({"music", "ambience"})
_POSITIONS = frozenset({"before", "after", "at_text"})
_BREAKS = frozenset({"chapter_start", "scene_break", "chapter_end"})
_TEMPO = frozenset({"slow", "medium", "fast"})
_KIND_ORDER = {"bed": 0, "transition": 1, "accent": 2, "sfx": 3}
DEFAULTS: dict[str, int] = {
    "bed_gain_db": -22,
    "accent_gain_db": -18,
    "sfx_gain_db": -16,
    "transition_gain_db": -16,
    "duck_db": 8,
}
_GAIN_KEY = {
    "bed": "bed_gain_db",
    "accent": "accent_gain_db",
    "sfx": "sfx_gain_db",
    "transition": "transition_gain_db",
}

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class SoundIssue:
    """One sound-markup problem, as an error or a warning."""

    severity: Severity
    message: str


def check_sound(
    manifest: Mapping[str, object],
    members: Mapping[str, bytes],
    paragraphs: Sequence[Mapping[str, object]],
) -> list[SoundIssue]:
    """Validation checklist for sound extension v1. Empty when the book has none."""
    issues: list[SoundIssue] = []
    has_sound = "sound.json" in members
    extensions = manifest.get("extensions")
    declared = isinstance(extensions, list) and EXTENSION in extensions
    if not has_sound and not declared and "sound-cast.json" not in members:
        return []
    version = _version_pair(manifest.get("format_version"))
    if version is None or version < (1, 1):
        issues.append(_issue("error", "sound extension v1 requires format_version 1.1"))
    if isinstance(extensions, list) and extensions.count(EXTENSION) > 1:
        issues.append(_issue("error", "extensions lists sound/1 more than once"))
    if declared != has_sound:
        issues.append(_issue("error", "extensions lists sound/1 exactly when sound.json exists"))
    if "sound-cast.json" in members and not has_sound:
        issues.append(_issue("error", "sound-cast.json requires sound.json"))
    if not has_sound:
        return issues
    document = _load_object(members["sound.json"], "sound.json", issues)
    if document is None:
        return issues
    if document.get("extension") != EXTENSION:
        issues.append(_issue("error", 'sound.json extension must be "sound/1"'))
    sound_version = _version_pair(document.get("version"))
    if sound_version is None or sound_version[0] != 1:
        issues.append(_issue("error", "sound.json version is not supported"))
        return issues
    _check_defaults(document.get("defaults"), issues)
    _scene_rows(document.get("scenes"), paragraphs, issues)
    cues = _cue_rows(document.get("cues"), paragraphs, issues)
    _check_layers(cues, paragraphs, issues)
    _check_mirrors(paragraphs, cues, issues)
    if "sound-cast.json" in members:
        _check_cast(members["sound-cast.json"], {str(cue["id"]) for cue in cues}, issues)
    return issues


def sound_prompt(paragraphs: Sequence[Mapping[str, object]], locked: Mapping[str, object]) -> str:
    """English instructions for one sound-markup completion."""
    data = {
        "paragraphs": [
            {
                "index": _as_int(row.get("index")),
                "chapter": _as_str(row.get("chapter")),
                "scene_start": row.get("scene_start") is True,
                "plain": _as_str(row.get("plain")),
            }
            for row in paragraphs
        ],
        "locked_scenes": locked.get("scenes", []),
        "locked_cues": locked.get("cues", []),
    }
    rules = (
        "Return one JSON object with keys scenes and cues. This is sound extension v1: "
        "every cue is generated from its English prompt. Do not emit an asset or library id. "
        "Cover every paragraph with contiguous scenes that never cross a chapter. "
        "Start a new scene at each scene_start paragraph. "
        "Each scene needs id, chapter, start_paragraph, end_paragraph, mood, intensity, "
        "src, and conf. mood is one of: "
        + ", ".join(sorted(_MOODS))
        + ". intensity and conf are 0 to 1. "
        "Give every scene a music bed (layer music) and put a transition at each chapter "
        "start and scene break after the first paragraph. Accents mark important beats. "
        "sfx is best effort and must not carry story meaning; prefer a bed or an accent. "
        "Say no vocals in every prompt, and no music on sfx. Do not name copyrighted works "
        "or real artists. at_text is optional and only a sentence-level hint. "
        "Bed length is a hint: the reader loops a 30-60 second segment. "
        "Copy locked_scenes and locked_cues unchanged, including their ids and src user. "
        "Do not invent inline directives."
    )
    return "TASK: sound\nDATA: " + json.dumps(data, ensure_ascii=False) + "\n\n" + rules


def resolve_vxbook(path: Path) -> Path:
    """A .vxbook file, a project folder, or a directory that already holds the book."""
    if path.is_file():
        return path
    for candidate in (path / "book.vxbook", path / "export" / "book.vxbook"):
        if candidate.is_file():
            return candidate
    raise PlotweaverError(f"no .vxbook found at {path}")


def add_sound(
    source: Path,
    dest: Path,
    backend: LLMBackend,
    *,
    mirror: bool = False,
) -> list[str]:
    """Write a new .vxbook with sound extension v1. The source file is not modified."""
    # vxbook imports check_sound from here, and this function imports the model caller.
    from plotweaver.llm import ChatMessage, complete_json
    from plotweaver.vxbook import pack_vxbook, paragraph_map, read_archive, validate_vxbook

    src = resolve_vxbook(source)
    if src.resolve() == dest.resolve():
        raise PlotweaverError("sound markup writes a new file and leaves the original in place")
    original = src.read_bytes()
    with gpu_job("sound-markup", eta_s=30 * 60):
        manifest, members = read_archive(src)
        book = members.get("book.md")
        if book is None:
            raise PlotweaverError("vxbook is missing book.md")
        text = book.decode("utf-8")
        paragraphs = paragraph_map(text)
        rows = [
            {
                "index": item.index,
                "chapter": item.chapter,
                "raw_line": item.raw_line,
                "plain": item.plain,
                "scene_start": item.scene_start,
                "mirrors": list(item.mirrors),
            }
            for item in paragraphs
        ]
        previous = _optional_json(members.get("sound.json"))
        locked = _locked(previous)
        proposed = complete_json(
            backend,
            [ChatMessage("user", sound_prompt(rows, locked))],
            temperature=0.2,
            max_tokens=4096,
        )
        document, warnings = assemble(rows, proposed, previous)
        if mirror:
            text = _with_mirrors(text, document["cues"])
            book = text.encode("utf-8")
        packed = _pack_members(manifest, members, book, document, original, src.name, warnings)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pack_vxbook(dest, packed[0], packed[1])
    if src.read_bytes() != original:
        dest.unlink(missing_ok=True)
        raise PlotweaverError("sound markup must leave the original file unchanged")
    problems = [issue.message for issue in validate_vxbook(dest) if issue.severity == "error"]
    if problems:
        dest.unlink(missing_ok=True)
        raise PlotweaverError("sound markup failed validation:\n" + "\n".join(problems))
    warnings.extend(issue.message for issue in validate_vxbook(dest) if issue.severity == "warning")
    return warnings


def assemble(
    paragraphs: Sequence[Mapping[str, object]],
    proposed: Mapping[str, object],
    previous: Mapping[str, object] | None,
) -> tuple[dict[str, object], list[str]]:
    """Merge model markup with src=user scenes and cues. User items stay byte-stable."""
    locked_scenes = _locked_rows(previous, "scenes")
    locked_cues = _locked_rows(previous, "cues")
    scenes = _merge_scenes(paragraphs, _mapping_list(proposed.get("scenes")), locked_scenes)
    cues = _merge_cues(paragraphs, scenes, _mapping_list(proposed.get("cues")), locked_cues)
    _ensure_beds(paragraphs, scenes, cues)
    _ensure_transitions(paragraphs, scenes, cues)
    cues.sort(key=_cue_sort)
    warnings: list[str] = []
    return (
        {
            "extension": EXTENSION,
            "version": SOUND_VERSION,
            "defaults": dict(DEFAULTS),
            "scenes": scenes,
            "cues": cues,
        },
        warnings,
    )


def _issue(severity: Severity, message: str) -> SoundIssue:
    return SoundIssue(severity, message)


def _version_pair(value: object) -> tuple[int, int] | None:
    if not isinstance(value, str):
        return None
    match = _VERSION.fullmatch(value)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _load_object(data: bytes, label: str, issues: list[SoundIssue]) -> dict[str, object] | None:
    if data.startswith(b"\xef\xbb\xbf"):
        issues.append(_issue("error", f"{label} has a BOM"))
        return None
    try:
        parsed: object = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        issues.append(_issue("error", f"{label} is not UTF-8 JSON: {exc}"))
        return None
    if not isinstance(parsed, dict):
        issues.append(_issue("error", f"{label} must be an object"))
        return None
    if _depth(parsed) > 32:
        issues.append(_issue("error", f"{label} is nested deeper than 32 levels"))
        return None
    return parsed


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key {key}")
        result[key] = value
    return result


def _depth(value: object, level: int = 0) -> int:
    if isinstance(value, dict):
        if not value:
            return level + 1
        return max(_depth(item, level + 1) for item in value.values())
    if isinstance(value, list):
        if not value:
            return level + 1
        return max(_depth(item, level + 1) for item in value)
    return level


def _check_defaults(value: object, issues: list[SoundIssue]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        issues.append(_issue("error", "defaults must be an object"))
        return
    for key, low, high in (
        ("bed_gain_db", -60, 0),
        ("accent_gain_db", -60, 0),
        ("sfx_gain_db", -60, 0),
        ("transition_gain_db", -60, 0),
        ("duck_db", 0, 30),
    ):
        if key in value and not _in_range(value[key], low, high):
            issues.append(_issue("error", f"defaults.{key} is outside {low}..{high}"))


def _scene_rows(
    value: object, paragraphs: Sequence[Mapping[str, object]], issues: list[SoundIssue]
) -> list[dict[str, object]]:
    if not isinstance(value, list) or not value:
        issues.append(_issue("error", "scenes must cover the book"))
        return []
    scenes: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            issues.append(_issue("error", "each scene must be an object"))
            continue
        sid = item.get("id")
        if not isinstance(sid, str) or not _ID.fullmatch(sid) or sid in seen:
            issues.append(_issue("error", "scene id is missing, duplicate, or not the grammar"))
            continue
        seen.add(sid)
        _check_mood(item.get("mood"), f"scene {sid}", issues, required=True)
        _check_unit(item.get("intensity"), f"scene {sid} intensity", issues, required=True)
        _check_provenance(item, f"scene {sid}", issues)
        hint = item.get("hint")
        if hint is not None and (not isinstance(hint, str) or len(hint) > 200):
            issues.append(_issue("error", f"scene {sid} hint must be at most 200 characters"))
        start = _as_int(item.get("start_paragraph"))
        end = _as_int(item.get("end_paragraph"))
        if start < 1 or end < start or end > len(paragraphs):
            issues.append(_issue("error", f"scene {sid} range is outside the book"))
            continue
        chapters = {
            _as_str(paragraphs[index - 1].get("chapter")) for index in range(start, end + 1)
        }
        stated = item.get("chapter")
        if len(chapters) != 1 or (isinstance(stated, str) and stated not in chapters):
            issues.append(_issue("error", f"scene {sid} must stay inside one chapter"))
        scenes.append(item)
    _check_coverage(scenes, paragraphs, issues)
    return scenes


def _check_coverage(
    scenes: Sequence[Mapping[str, object]],
    paragraphs: Sequence[Mapping[str, object]],
    issues: list[SoundIssue],
) -> None:
    ordered = sorted(scenes, key=lambda item: _as_int(item.get("start_paragraph")))
    expect = 1
    starts = {_as_int(item.get("start_paragraph")) for item in ordered}
    for item in ordered:
        start = _as_int(item.get("start_paragraph"))
        end = _as_int(item.get("end_paragraph"))
        if start != expect:
            issues.append(_issue("error", "scenes must be contiguous and non-overlapping"))
            return
        expect = end + 1
    if expect != len(paragraphs) + 1:
        issues.append(_issue("error", "scenes must cover every paragraph"))
    for row in paragraphs:
        index = _as_int(row.get("index"))
        if row.get("scene_start") is True and index not in starts:
            issues.append(_issue("error", f"a scene must start at paragraph {index}"))


def _cue_rows(
    value: object,
    paragraphs: Sequence[Mapping[str, object]],
    issues: list[SoundIssue],
) -> list[dict[str, object]]:
    if not isinstance(value, list):
        issues.append(_issue("error", "cues must be an array"))
        return []
    cues: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            issues.append(_issue("error", "each cue must be an object"))
            continue
        cid = item.get("id")
        kind = item.get("kind")
        if not isinstance(cid, str) or not _ID.fullmatch(cid) or cid in seen:
            issues.append(_issue("error", "cue id is missing, duplicate, or not the grammar"))
            continue
        seen.add(cid)
        if kind not in _KINDS:
            issues.append(_issue("error", f"cue {cid} kind is not known"))
            continue
        prompt = item.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 300:
            issues.append(
                _issue("error", f"cue {cid} needs an English prompt of at most 300 characters")
            )
        elif _CYRILLIC.search(prompt):
            issues.append(_issue("error", f"cue {cid} prompt must be English"))
        _check_mood(item.get("mood"), f"cue {cid}", issues, required=False)
        _check_unit(item.get("intensity"), f"cue {cid} intensity", issues, required=False)
        _check_unit(item.get("conf"), f"cue {cid} conf", issues, required=False)
        _check_provenance(item, f"cue {cid}", issues)
        start = _as_int(item.get("start_paragraph"))
        if start < 1 or start > len(paragraphs):
            issues.append(_issue("error", f"cue {cid} start_paragraph is outside the book"))
            continue
        if kind == "bed":
            _check_bed(item, cid, start, paragraphs, issues)
        else:
            _check_oneshot(item, cid, paragraphs[start - 1], issues)
        _check_anchor(item, cid, paragraphs[start - 1], issues)
        cues.append(item)
    return cues


def _check_bed(
    item: Mapping[str, object],
    cid: str,
    start: int,
    paragraphs: Sequence[Mapping[str, object]],
    issues: list[SoundIssue],
) -> None:
    if item.get("layer") not in _LAYERS:
        issues.append(_issue("error", f"cue {cid} layer must be music or ambience"))
    end = _as_int(item.get("end_paragraph"))
    if end < start or end > len(paragraphs):
        issues.append(_issue("error", f"cue {cid} end_paragraph is outside the bed"))
        return
    start_chapter = _as_str(paragraphs[start - 1].get("chapter"))
    end_chapter = _as_str(paragraphs[end - 1].get("chapter"))
    if start_chapter != end_chapter:
        issues.append(_issue("error", f"cue {cid} must stay inside one chapter"))
    end_fp = item.get("end_para_fp")
    expected = _fingerprint(_as_str(paragraphs[end - 1].get("raw_line")))
    if isinstance(end_fp, str) and end_fp != expected:
        issues.append(_issue("warning", f"cue {cid} end_para_fp does not match paragraph {end}"))
    _check_span_numbers(item, cid, issues)


def _check_oneshot(
    item: Mapping[str, object],
    cid: str,
    paragraph: Mapping[str, object],
    issues: list[SoundIssue],
) -> None:
    position = item.get("position")
    if position not in _POSITIONS:
        issues.append(_issue("error", f"cue {cid} position must be before, after, or at_text"))
        return
    snippet = item.get("at_text")
    if position == "at_text":
        plain = _as_str(paragraph.get("plain"))
        if not isinstance(snippet, str) or not 3 <= len(snippet) <= 60 or snippet not in plain:
            issues.append(_issue("error", f"cue {cid} at_text is not in the paragraph"))
    if item.get("kind") == "transition" and item.get("at") not in _BREAKS:
        issues.append(
            _issue("error", f"cue {cid} at must be chapter_start, scene_break, or chapter_end")
        )


def _check_span_numbers(item: Mapping[str, object], cid: str, issues: list[SoundIssue]) -> None:
    for key, low, high in (
        ("gain_db", -60, 0),
        ("duck_db", 0, 30),
        ("fade_in_ms", 0, 600_000),
        ("fade_out_ms", 0, 600_000),
        ("crossfade_ms", 0, 600_000),
    ):
        if key in item and not _in_range(item[key], low, high):
            issues.append(_issue("error", f"cue {cid} {key} is outside {low}..{high}"))
    if "loop" in item and not isinstance(item.get("loop"), bool):
        issues.append(_issue("error", f"cue {cid} loop must be true or false"))
    music = item.get("music")
    if music is None:
        return
    if not isinstance(music, dict):
        issues.append(_issue("error", f"cue {cid} music must be an object"))
        return
    tempo = music.get("tempo")
    if tempo is not None and tempo not in _TEMPO:
        issues.append(_issue("error", f"cue {cid} tempo must be slow, medium, or fast"))


def _check_anchor(
    item: Mapping[str, object],
    cid: str,
    paragraph: Mapping[str, object],
    issues: list[SoundIssue],
) -> None:
    stated = item.get("chapter")
    chapter = _as_str(paragraph.get("chapter"))
    if isinstance(stated, str) and stated != chapter:
        issues.append(_issue("warning", f"cue {cid} chapter does not match paragraph"))
    fingerprint = item.get("para_fp")
    expected = _fingerprint(_as_str(paragraph.get("raw_line")))
    if isinstance(fingerprint, str) and fingerprint != expected:
        issues.append(_issue("warning", f"cue {cid} para_fp does not match the paragraph"))
    if "gain_db" in item and not _in_range(item.get("gain_db"), -60, 0):
        issues.append(_issue("error", f"cue {cid} gain_db must be from -60 to 0"))


def _check_layers(
    cues: Sequence[Mapping[str, object]],
    paragraphs: Sequence[Mapping[str, object]],
    issues: list[SoundIssue],
) -> None:
    count = len(paragraphs)
    if len(cues) > 5000:
        issues.append(_issue("error", "a book has at most 5000 cues"))
    per_chapter: dict[str, int] = {}
    transitions: set[tuple[str, int]] = set()
    for cue in cues:
        start = _as_int(cue.get("start_paragraph"))
        if 1 <= start <= count:
            chapter = _as_str(paragraphs[start - 1].get("chapter"))
            per_chapter[chapter] = per_chapter.get(chapter, 0) + 1
    for index in range(1, count + 1):
        music = 0
        ambience = 0
        shots: list[str] = []
        for cue in cues:
            start = _as_int(cue.get("start_paragraph"))
            kind = cue.get("kind")
            if kind == "bed":
                end = _as_int(cue.get("end_paragraph"))
                if start <= index <= end:
                    if cue.get("layer") == "music":
                        music += 1
                    elif cue.get("layer") == "ambience":
                        ambience += 1
            elif start == index and isinstance(cue.get("position"), str):
                shots.append(str(cue["position"]))
        if music > 1 or ambience > 1:
            issues.append(_issue("error", f"paragraph {index} has more than one bed on a layer"))
            return
        if len(shots) > 2 or len(shots) != len(set(shots)):
            issues.append(_issue("error", f"paragraph {index} has too many one-shots"))
            return
    for cue in cues:
        if cue.get("kind") != "transition":
            continue
        key = (_as_str(cue.get("at")), _as_int(cue.get("start_paragraph")))
        if key in transitions:
            issues.append(_issue("error", "a break has more than one transition"))
            return
        transitions.add(key)
    if any(total > 200 for total in per_chapter.values()):
        issues.append(_issue("error", "a chapter has more than 200 cues"))


def _check_mirrors(
    paragraphs: Sequence[Mapping[str, object]],
    cues: Sequence[Mapping[str, object]],
    issues: list[SoundIssue],
) -> None:
    by_id = {str(cue.get("id")): cue for cue in cues}
    for row in paragraphs:
        mirrors = row.get("mirrors")
        if not isinstance(mirrors, list):
            continue
        index = _as_int(row.get("index"))
        for cue_id in mirrors:
            cue = by_id.get(str(cue_id))
            if cue is None or _as_int(cue.get("start_paragraph")) != index:
                issues.append(
                    _issue(
                        "warning",
                        f"vx:sound {cue_id} does not match a cue at paragraph {index}",
                    )
                )


def _check_cast(data: bytes, cue_ids: set[str], issues: list[SoundIssue]) -> None:
    document = _load_object(data, "sound-cast.json", issues)
    if document is None:
        return
    version = _version_pair(document.get("version"))
    if version is None or version[0] != 1:
        issues.append(_issue("error", "sound-cast.json version is not supported"))
    if "enabled" in document and not isinstance(document.get("enabled"), bool):
        issues.append(_issue("error", "sound-cast enabled must be true or false"))
    if "master_gain_db" in document and not _in_range(document.get("master_gain_db"), -60, 6):
        issues.append(_issue("error", "sound-cast master_gain_db must be from -60 to 6"))
    cues = document.get("cues")
    if not isinstance(cues, dict):
        issues.append(_issue("error", "sound-cast cues must be an object"))
        return
    for key, value in cues.items():
        if key not in cue_ids:
            issues.append(_issue("error", f"sound-cast key {key} is not a cue id"))
            continue
        if not isinstance(value, dict):
            issues.append(_issue("error", f"sound-cast entry {key} must be an object"))
            continue
        if "gain_db" in value and not _in_range(value.get("gain_db"), -60, 6):
            issues.append(_issue("error", f"sound-cast {key} gain_db must be from -60 to 6"))
        if "disabled" in value and not isinstance(value.get("disabled"), bool):
            issues.append(_issue("error", f"sound-cast {key} disabled must be true or false"))
        prompt = value.get("prompt")
        if prompt is not None and (not isinstance(prompt, str) or len(prompt) > 300):
            issues.append(
                _issue("error", f"sound-cast {key} prompt must be at most 300 characters")
            )


def _check_mood(value: object, label: str, issues: list[SoundIssue], *, required: bool) -> None:
    if value is None and not required:
        return
    if value not in _MOODS:
        issues.append(_issue("error", f"{label} mood is not in the sound/1 vocabulary"))


def _check_unit(value: object, label: str, issues: list[SoundIssue], *, required: bool) -> None:
    if value is None and not required:
        return
    if not _in_unit(value):
        issues.append(_issue("error", f"{label} must be from 0 to 1 with at most two decimals"))


def _check_provenance(item: Mapping[str, object], label: str, issues: list[SoundIssue]) -> None:
    src = item.get("src")
    if src is not None and src not in {"auto", "user"}:
        issues.append(_issue("error", f"{label} src must be auto or user"))
    if "conf" in item:
        _check_unit(item.get("conf"), f"{label} conf", issues, required=True)


def _fingerprint(raw_line: str) -> str:
    return hashlib.sha256(raw_line.encode("utf-8")).hexdigest()[:12]


def _in_unit(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    if value < 0 or value > 1:
        return False
    scaled = float(value) * 100
    return abs(scaled - round(scaled)) < 1e-6


def _in_range(value: object, low: float, high: float) -> bool:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return False
    return low <= float(value) <= high


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return value


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _optional_json(data: bytes | None) -> dict[str, object] | None:
    if data is None:
        return None
    try:
        parsed: object = json.loads(data.decode("utf-8"))
    except UnicodeError, json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _locked(previous: Mapping[str, object] | None) -> dict[str, object]:
    return {"scenes": _locked_rows(previous, "scenes"), "cues": _locked_rows(previous, "cues")}


def _locked_rows(previous: Mapping[str, object] | None, key: str) -> list[dict[str, object]]:
    if previous is None:
        return []
    rows = previous.get(key)
    if not isinstance(rows, list):
        return []
    locked: list[dict[str, object]] = []
    for item in rows:
        if isinstance(item, dict) and item.get("src") == "user":
            locked.append(copy.deepcopy(item))
    return locked


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _merge_scenes(
    paragraphs: Sequence[Mapping[str, object]],
    proposed: Sequence[Mapping[str, object]],
    locked: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    occupied: set[int] = set()
    scenes: list[dict[str, object]] = []
    used = {str(item.get("id")) for item in locked}
    for item in locked:
        scenes.append(dict(item))
        start = _as_int(item.get("start_paragraph"))
        end = _as_int(item.get("end_paragraph"))
        for index in range(start, end + 1):
            occupied.add(index)
    for item in proposed:
        if str(item.get("id")) in used:
            continue
        start = _as_int(item.get("start_paragraph"))
        end = _as_int(item.get("end_paragraph"))
        if not _range_free(paragraphs, occupied, start, end):
            continue
        scene = _normalize_scene(item, paragraphs, used)
        if scene is None:
            continue
        scenes.append(scene)
        used.add(str(scene["id"]))
        for index in range(start, end + 1):
            occupied.add(index)
    for start, end in _gaps(paragraphs, occupied):
        scene = _fresh_scene(start, end, paragraphs, used)
        scenes.append(scene)
        used.add(str(scene["id"]))
    scenes.sort(key=lambda item: _as_int(item.get("start_paragraph")))
    return scenes


def _range_free(
    paragraphs: Sequence[Mapping[str, object]], occupied: set[int], start: int, end: int
) -> bool:
    if start < 1 or end < start or end > len(paragraphs):
        return False
    if any(index in occupied for index in range(start, end + 1)):
        return False
    if any(
        _as_int(paragraphs[index - 1].get("index")) > start
        and paragraphs[index - 1].get("scene_start") is True
        and start < _as_int(paragraphs[index - 1].get("index")) <= end
        for index in range(start, end + 1)
    ):
        return False
    chapters = {_as_str(paragraphs[index - 1].get("chapter")) for index in range(start, end + 1)}
    return len(chapters) == 1


def _normalize_scene(
    item: Mapping[str, object],
    paragraphs: Sequence[Mapping[str, object]],
    used: set[str],
) -> dict[str, object] | None:
    start = _as_int(item.get("start_paragraph"))
    end = _as_int(item.get("end_paragraph"))
    if not _range_free(paragraphs, set(), start, end):
        return None
    chapter = _as_str(paragraphs[start - 1].get("chapter"))
    mood = item.get("mood")
    intensity = item.get("intensity")
    scene: dict[str, object] = {
        "id": _fresh_id(_as_str(item.get("id")), "s", used),
        "chapter": chapter,
        "start_paragraph": start,
        "end_paragraph": end,
        "mood": mood if mood in _MOODS else "neutral",
        "intensity": intensity if _in_unit(intensity) else 0.4,
        "src": "auto",
        "conf": item.get("conf") if _in_unit(item.get("conf")) else 0.75,
    }
    hint = item.get("hint")
    if isinstance(hint, str) and hint.strip():
        scene["hint"] = hint.strip()[:200]
    return scene


def _fresh_scene(
    start: int, end: int, paragraphs: Sequence[Mapping[str, object]], used: set[str]
) -> dict[str, object]:
    return {
        "id": _fresh_id("", "s", used),
        "chapter": _as_str(paragraphs[start - 1].get("chapter")),
        "start_paragraph": start,
        "end_paragraph": end,
        "mood": "neutral",
        "intensity": 0.3,
        "src": "auto",
        "conf": 0.5,
    }


def _gaps(paragraphs: Sequence[Mapping[str, object]], occupied: set[int]) -> list[tuple[int, int]]:
    gaps: list[tuple[int, int]] = []
    start: int | None = None
    for row in paragraphs:
        index = _as_int(row.get("index"))
        if index in occupied:
            if start is not None:
                gaps.append((start, index - 1))
                start = None
            continue
        if start is None or row.get("scene_start") is True:
            if start is not None:
                gaps.append((start, index - 1))
            start = index
    if start is not None and paragraphs:
        gaps.append((start, _as_int(paragraphs[-1].get("index"))))
    return gaps


def _merge_cues(
    paragraphs: Sequence[Mapping[str, object]],
    scenes: Sequence[Mapping[str, object]],
    proposed: Sequence[Mapping[str, object]],
    locked: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    del scenes
    cues: list[dict[str, object]] = [dict(item) for item in locked]
    used = {str(item.get("id")) for item in cues}
    ordered = sorted(proposed, key=lambda item: (-_conf(item), str(item.get("id"))))
    for item in ordered:
        if str(item.get("id")) in used or item.get("src") == "user":
            continue
        cue = _normalize_cue(item, paragraphs, used)
        if cue is None or not _fits(cues + [cue], paragraphs):
            continue
        cues.append(cue)
        used.add(str(cue["id"]))
    return cues


def _normalize_cue(
    item: Mapping[str, object],
    paragraphs: Sequence[Mapping[str, object]],
    used: set[str],
) -> dict[str, object] | None:
    kind = item.get("kind")
    if kind not in _KINDS:
        return None
    start = _as_int(item.get("start_paragraph"))
    if start < 1 or start > len(paragraphs):
        return None
    prompt = item.get("prompt")
    if not isinstance(prompt, str) or _CYRILLIC.search(prompt):
        return None
    extra = "no music" if kind == "sfx" else "no vocals"
    text = _fit_prompt(prompt, extra)
    if not text:
        return None
    paragraph = paragraphs[start - 1]
    cue: dict[str, object] = {
        "id": _fresh_id(_as_str(item.get("id")), "c", used),
        "kind": kind,
        "prompt": text,
        "start_paragraph": start,
        "chapter": _as_str(paragraph.get("chapter")),
        "para_fp": _fingerprint(_as_str(paragraph.get("raw_line"))),
        "src": "auto",
        "conf": item.get("conf") if _in_unit(item.get("conf")) else 0.75,
    }
    mood = item.get("mood")
    if mood in _MOODS:
        cue["mood"] = mood
    intensity = item.get("intensity")
    if _in_unit(intensity):
        cue["intensity"] = intensity
    if _in_range(item.get("gain_db"), -60, 0):
        cue["gain_db"] = item.get("gain_db")
    else:
        cue["gain_db"] = DEFAULTS[_GAIN_KEY[str(kind)]]
    if kind == "bed":
        end = _as_int(item.get("end_paragraph"))
        if end < start or end > len(paragraphs):
            return None
        if _as_str(paragraphs[end - 1].get("chapter")) != cue["chapter"]:
            return None
        layer = item.get("layer")
        cue["layer"] = layer if layer in _LAYERS else "music"
        cue["end_paragraph"] = end
        cue["end_para_fp"] = _fingerprint(_as_str(paragraphs[end - 1].get("raw_line")))
        cue["loop"] = True
        duck = item.get("duck_db")
        cue["duck_db"] = duck if _in_range(duck, 0, 30) else DEFAULTS["duck_db"]
        cue["fade_in_ms"] = 2000
        cue["fade_out_ms"] = 3000
        cue["crossfade_ms"] = 2000
        return cue
    position = item.get("position")
    cue["position"] = position if position in _POSITIONS else "before"
    if kind == "transition":
        at = item.get("at")
        cue["at"] = at if at in _BREAKS else "scene_break"
    if cue["position"] == "at_text":
        snippet = item.get("at_text")
        plain = _as_str(paragraph.get("plain"))
        if not isinstance(snippet, str) or not 3 <= len(snippet) <= 60 or snippet not in plain:
            cue["position"] = "before"
            cue.pop("at_text", None)
        else:
            cue["at_text"] = snippet
    return cue


def _fit_prompt(text: str, extra: str) -> str:
    cleaned = " ".join(text.split())
    if extra not in cleaned.lower():
        joined = f"{cleaned}, {extra}"
        cleaned = joined if len(joined) <= 300 else cleaned
    return cleaned[:300].strip()


def _ensure_beds(
    paragraphs: Sequence[Mapping[str, object]],
    scenes: Sequence[Mapping[str, object]],
    cues: list[dict[str, object]],
) -> None:
    used = {str(cue.get("id")) for cue in cues}
    for scene in scenes:
        start = _as_int(scene.get("start_paragraph"))
        end = _as_int(scene.get("end_paragraph"))
        run: int | None = None
        for index in range(start, end + 1):
            covered = _bed_covers(cues, index, "music")
            if not covered and run is None:
                run = index
            elif covered and run is not None:
                _add_bed(cues, used, paragraphs, scene, run, index - 1)
                run = None
        if run is not None:
            _add_bed(cues, used, paragraphs, scene, run, end)


def _add_bed(
    cues: list[dict[str, object]],
    used: set[str],
    paragraphs: Sequence[Mapping[str, object]],
    scene: Mapping[str, object],
    start: int,
    end: int,
) -> None:
    mood = scene.get("mood") if scene.get("mood") in _MOODS else "neutral"
    cue = _normalize_cue(
        {
            "id": f"bed-{start}",
            "kind": "bed",
            "layer": "music",
            "prompt": f"soft {mood} ambient music bed, no percussion, no vocals",
            "mood": mood,
            "intensity": scene.get("intensity", 0.3),
            "start_paragraph": start,
            "end_paragraph": end,
            "src": "auto",
            "conf": 0.55,
        },
        paragraphs,
        used,
    )
    if cue is not None and _fits(cues + [cue], paragraphs):
        cues.append(cue)
        used.add(str(cue["id"]))


def _ensure_transitions(
    paragraphs: Sequence[Mapping[str, object]],
    scenes: Sequence[Mapping[str, object]],
    cues: list[dict[str, object]],
) -> None:
    used = {str(cue.get("id")) for cue in cues}
    firsts: dict[str, int] = {}
    for row in paragraphs:
        chapter = _as_str(row.get("chapter"))
        index = _as_int(row.get("index"))
        firsts.setdefault(chapter, index)
    for scene in scenes:
        start = _as_int(scene.get("start_paragraph"))
        if start <= 1:
            continue
        chapter = _as_str(scene.get("chapter"))
        at = "chapter_start" if firsts.get(chapter) == start else "scene_break"
        if any(
            cue.get("kind") == "transition" and _as_int(cue.get("start_paragraph")) == start
            for cue in cues
        ):
            continue
        cue = _normalize_cue(
            {
                "id": f"tr-{start}",
                "kind": "transition",
                "at": at,
                "prompt": "short warm musical cadence for a scene change, no vocals",
                "mood": scene.get("mood", "neutral"),
                "intensity": 0.3,
                "start_paragraph": start,
                "position": "before",
                "src": "auto",
                "conf": 0.6,
            },
            paragraphs,
            used,
        )
        if cue is not None and _fits(cues + [cue], paragraphs):
            cues.append(cue)
            used.add(str(cue["id"]))


def _bed_covers(cues: Sequence[Mapping[str, object]], index: int, layer: str) -> bool:
    for cue in cues:
        if cue.get("kind") != "bed" or cue.get("layer") != layer:
            continue
        if _as_int(cue.get("start_paragraph")) <= index <= _as_int(cue.get("end_paragraph")):
            return True
    return False


def _fits(cues: Sequence[Mapping[str, object]], paragraphs: Sequence[Mapping[str, object]]) -> bool:
    issues: list[SoundIssue] = []
    _check_layers(cues, paragraphs, issues)
    return not any(item.severity == "error" for item in issues)


def _conf(item: Mapping[str, object]) -> float:
    value = item.get("conf")
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _cue_sort(item: Mapping[str, object]) -> tuple[int, int, str]:
    kind = str(item.get("kind") or "")
    return (_as_int(item.get("start_paragraph")), _KIND_ORDER.get(kind, 9), str(item.get("id")))


def _fresh_id(preferred: str, prefix: str, used: set[str]) -> str:
    if preferred and _ID.fullmatch(preferred) and preferred not in used:
        return preferred
    number = 1
    while True:
        candidate = f"{prefix}{number}"
        if candidate not in used:
            return candidate
        number += 1


def _with_mirrors(text: str, cues: object) -> str:
    wanted: dict[int, list[str]] = {}
    if isinstance(cues, list):
        for cue in cues:
            if not isinstance(cue, dict):
                continue
            start = _as_int(cue.get("start_paragraph"))
            cue_id = _as_str(cue.get("id"))
            if start and cue_id:
                wanted.setdefault(start, []).append(cue_id)
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        if line == "":
            if current:
                blocks.append(current)
                current = []
            continue
        current.append(line)
    if current:
        blocks.append(current)
    paragraph = 0
    rebuilt: list[str] = []
    for block in blocks:
        split = 0
        while split < len(block) and block[split].startswith("<!-- vx:"):
            split += 1
        body = block[split:]
        directives = block[:split]
        heading = any(line.startswith("<!-- vx:chapter ") for line in directives)
        if heading or body == ["* * *"] or (body and body[0].startswith("## ") and not directives):
            rebuilt.append("\n".join(block))
            continue
        if not body:
            rebuilt.append("\n".join(block))
            continue
        paragraph += 1
        sound = [line for line in directives if line.startswith("<!-- vx:sound ")]
        other = [line for line in directives if not line.startswith("<!-- vx:sound ")]
        for cue_id in wanted.get(paragraph, []):
            line = f'<!-- vx:sound cue="{cue_id}" -->'
            if line not in sound:
                sound.append(line)
        rebuilt.append("\n".join([*sound, *other, *body]))
    return "\n\n".join(rebuilt) + "\n"


def _pack_members(
    manifest: Mapping[str, object],
    members: Mapping[str, bytes],
    book: bytes,
    document: Mapping[str, object],
    original: bytes,
    filename: str,
    warnings: list[str],
) -> tuple[dict[str, object], list[tuple[str, bytes]]]:
    speakers = _bump_speakers(members.get("speakers.json", b""))
    sound = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    cue_ids = {str(item.get("id")) for item in _mapping_list(document.get("cues"))}
    cast_bytes, dropped = _prune_cast(members.get("sound-cast.json"), cue_ids)
    warnings.extend(dropped)
    chapters = manifest.get("chapters")
    chapter_rows: list[dict[str, object]] = []
    if isinstance(chapters, list):
        chapter_rows = [dict(item) for item in chapters if isinstance(item, dict)]
    if book != members.get("book.md"):
        text = book.decode("utf-8")
        for chapter in chapter_rows:
            needle = f'<!-- vx:chapter id="{chapter.get("id")}" -->'
            at = text.find(needle)
            if at >= 0:
                chapter["offset"] = len(text[:at].encode("utf-8"))
    extensions = manifest.get("extensions")
    names: list[str] = []
    if isinstance(extensions, list):
        names = [item for item in extensions if isinstance(item, str)]
    if EXTENSION not in names:
        names.append(EXTENSION)
    deduped: list[str] = []
    for name in names:
        if name not in deduped:
            deduped.append(name)
    created_by = manifest.get("created_by")
    if not isinstance(created_by, dict):
        created_by = {"app": _APP, "version": APP_VERSION}
    updated: dict[str, object] = {
        "format_version": FORMAT_VERSION,
        "title": _as_str(manifest.get("title")) or "Untitled",
        "author": _as_str(manifest.get("author")),
        "language": _as_str(manifest.get("language")) or "ru",
        "created_by": created_by,
        "generator": {"app": _APP, "version": APP_VERSION},
        "created": _as_str(manifest.get("created")),
        "source": {
            "format": "vxbook",
            "filename": Path(filename).name,
            "sha256": hashlib.sha256(original).hexdigest(),
        },
        "extensions": deduped,
        "book": "book.md",
        "speakers": "speakers.json",
        "chapters": chapter_rows,
    }
    notes = manifest.get("notes")
    if isinstance(notes, list):
        updated["notes"] = notes
    cover = manifest.get("cover")
    if isinstance(cover, str):
        updated["cover"] = cover
    packed: list[tuple[str, bytes]] = []
    skip = {
        "mimetype",
        "manifest.json",
        "sound.json",
        "sound-cast.json",
        "speakers.json",
        "book.md",
    }
    packed.append(("book.md", book))
    packed.append(("speakers.json", speakers))
    for name, data in members.items():
        if name not in skip:
            packed.append((name, data))
    packed.append(("sound.json", sound))
    if cast_bytes is not None:
        packed.append(("sound-cast.json", cast_bytes))
    return updated, packed


def _bump_speakers(data: bytes) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeError:
        return data
    updated, count = re.subn(
        r'("format_version"\s*:\s*")\d+\.\d+"',
        rf'\g<1>{FORMAT_VERSION}"',
        text,
        count=1,
    )
    if count != 1:
        return data
    return updated.encode("utf-8")


def _prune_cast(data: bytes | None, cue_ids: set[str]) -> tuple[bytes | None, list[str]]:
    if data is None:
        return None, []
    try:
        parsed: object = json.loads(data.decode("utf-8"))
    except UnicodeError, json.JSONDecodeError:
        return data, ["sound-cast.json was not JSON and was left unchanged"]
    if not isinstance(parsed, dict):
        return data, []
    cues = parsed.get("cues")
    if not isinstance(cues, dict):
        return data, []
    warnings: list[str] = []
    kept: dict[str, object] = {}
    for key, value in cues.items():
        if key in cue_ids:
            kept[key] = value
        else:
            warnings.append(f"dropped sound-cast override for missing cue {key}")
    if not warnings:
        return data, []
    parsed["cues"] = kept
    return (json.dumps(parsed, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), warnings
