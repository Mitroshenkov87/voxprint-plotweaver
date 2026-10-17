"""Plotweaver's preset document and the one settings state behind it.

Chips and the expert panel read the same keys. Readers is who the book is
for. It is not a safety control, and no key here names a minors gate.
"""

from __future__ import annotations

from pathlib import Path

from voxprint_common.mdl.catalog import ModelTier as VramTier
from voxprint_common.mdl.catalog import load_manifest
from voxprint_common.ui.presets import PresetFile, load_presets
from voxprint_common.ui.settings import Choice, Settings, SettingSpec, SettingType

from plotweaver.length import SAFETY_CHAPTER_CEILING, STRUCTURAL_MAX_PAGES

_PRESET_FILE = Path(__file__).resolve().parents[1] / "data" / "presets" / "book.json"
# A page of fiction, read aloud or silently. The estimate under the length chips uses this.
READING_WORDS_PER_MINUTE = 250
# Above this page count the window shows a plain note. The book still runs.
# Prose past about 550 pages has not been checked on a real model.
LONG_BOOK_NOTE_PAGES = 600
# Expert scenes is a requested minimum. The planner raises it. An automatic
# plan for a 2,000-page book stays under this.
MAX_SCENES_PER_CHAPTER = 16
_MANIFEST = Path(__file__).resolve().parents[1] / "data" / "mdl.json"


def reading_estimate(pages: int, words_per_page: int) -> tuple[int, int, int]:
    """Return pages, words, and reading minutes for the length line.

    Minutes use :data:`READING_WORDS_PER_MINUTE`. Zero words is zero minutes.
    """
    words = max(0, pages) * max(0, words_per_page)
    if words <= 0:
        return max(0, pages), 0, 0
    return max(0, pages), words, max(1, round(words / READING_WORDS_PER_MINUTE))


def grouped_number(value: int) -> str:
    """Group thousands with a space: 62500 becomes ``62 500``."""
    return f"{value:,}".replace(",", " ")


def preset_path() -> Path:
    """Return the ``voxprint-presets/1`` document for the book form."""
    return _PRESET_FILE


def book_settings() -> Settings:
    """Return the descriptors the chips and the expert panel share.

    Expert rows are the page numbers, the prompt, the model tier, VRAM, the
    abliterated download, and the resolved model id. The other rows exist so
    a preset can write a typed value. They stay off the expert panel.
    """
    return Settings(
        (
            _int("book.pages", "setting.book.pages", 250, 1, STRUCTURAL_MAX_PAGES, expert=True),
            _int("book.words_per_page", "setting.book.words", 250, 100, 600, expert=True),
            _int("book.scenes", "setting.book.scenes", 2, 1, MAX_SCENES_PER_CHAPTER, expert=True),
            _int(
                "book.chapters",
                "setting.book.chapters",
                0,
                0,
                SAFETY_CHAPTER_CEILING,
                expert=True,
            ),
            _text("book.prompt", "setting.book.prompt", expert=True),
            SettingSpec(
                "book.tier",
                "setting.book.tier",
                "setting.book.tier.help",
                SettingType.ENUM,
                "standard",
                expert=True,
                group="book",
                choices=(
                    Choice("standard", "setting.book.tier.standard"),
                    Choice("least-censored", "setting.book.tier.least"),
                ),
            ),
            SettingSpec(
                "book.vram",
                "setting.book.vram",
                "setting.book.vram.help",
                SettingType.ENUM,
                "auto",
                expert=True,
                group="book",
                choices=(
                    Choice("auto", "setting.book.vram.auto"),
                    Choice("16gb", "setting.book.vram.16"),
                    Choice("24gb", "setting.book.vram.24"),
                ),
            ),
            SettingSpec(
                "book.abliterated",
                "setting.book.abliterated",
                "setting.book.abliterated.help",
                SettingType.BOOL,
                False,
                expert=True,
                group="book",
            ),
            _text("book.model", "setting.book.model", expert=True),
            SettingSpec(
                "book.language",
                "book.language",
                "setting.book.language.help",
                SettingType.ENUM,
                "ru",
                choices=(Choice("ru", "book.language.ru"), Choice("en", "book.language.en")),
            ),
            SettingSpec(
                "book.pov",
                "book.pov",
                "setting.book.pov.help",
                SettingType.ENUM,
                "third-person limited",
                choices=(
                    Choice("third-person limited", "book.pov.limited"),
                    Choice("first person", "book.pov.first"),
                    Choice("third-person omniscient", "book.pov.omniscient"),
                ),
            ),
            SettingSpec(
                "book.tense",
                "book.tense",
                "setting.book.tense.help",
                SettingType.ENUM,
                "past",
                choices=(
                    Choice("past", "book.tense.past"),
                    Choice("present", "book.tense.present"),
                ),
            ),
            SettingSpec(
                "book.readers",
                "book.readers",
                "setting.book.readers.help",
                SettingType.ENUM,
                "adult",
                choices=(
                    Choice("adult", "book.readers.adults"),
                    Choice("teen", "book.readers.teenagers"),
                    Choice("child", "book.readers.children"),
                ),
            ),
            SettingSpec(
                "book.ending",
                "book.ending",
                "setting.book.ending.help",
                SettingType.ENUM,
                "closed",
                choices=(
                    Choice("closed", "book.ending.closed"),
                    Choice("open", "book.ending.open"),
                    Choice("bittersweet", "book.ending.bittersweet"),
                    Choice("twist", "book.ending.twist"),
                    Choice("tragic", "book.ending.tragic"),
                ),
            ),
            SettingSpec(
                "book.mode",
                "book.stops",
                "setting.book.mode.help",
                SettingType.ENUM,
                "autopilot",
                choices=(
                    Choice("autopilot", "book.stops.plan"),
                    Choice("copilot", "book.stops.chapter"),
                    Choice("manual", "book.stops.scene"),
                ),
            ),
            SettingSpec(
                "book.dark",
                "book.themes",
                "setting.book.dark.help",
                SettingType.BOOL,
                False,
            ),
            _flag("book.export.fb2"),
            _flag("book.export.docx"),
            _flag("book.export.markdown"),
            _flag("book.export.marks"),
            SettingSpec(
                "book.sound",
                "book.sound",
                "setting.book.sound.help",
                SettingType.BOOL,
                False,
            ),
        )
    )


def book_presets(settings: Settings) -> PresetFile:
    """Load and validate the book preset document against ``settings``."""
    return load_presets(preset_path(), settings)


def resolved_model_id(*, vram: str, tier: str, detected: str) -> str:
    """Return the registry model id for this VRAM tier and model tier.

    The id comes from ``mdl.json``. Nothing in the window lists model ids of
    its own. An empty string means the manifest has no available row.

    Args:
        vram: ``auto``, ``16gb``, or ``24gb``.
        tier: ``standard`` or ``least-censored``.
        detected: The card's tier when ``vram`` is ``auto``.
    """
    selected = detected if vram == "auto" else vram
    if selected not in {item.value for item in VramTier}:
        selected = VramTier.GB16.value
    manifest = load_manifest(_MANIFEST)
    rows = [
        model for model in manifest.models if not model.unavailable and model.tier.value == selected
    ]
    if tier == "least-censored":
        optional = [model for model in rows if model.optional]
        rows = optional or rows
    else:
        stock = [model for model in rows if not model.optional]
        rows = stock or rows
    if not rows:
        return ""
    return rows[0].id


def _int(
    setting_id: str,
    label_key: str,
    default: int,
    minimum: int,
    maximum: int,
    *,
    expert: bool,
) -> SettingSpec:
    return SettingSpec(
        setting_id,
        label_key,
        f"{label_key}.help",
        SettingType.INT,
        default,
        expert=expert,
        group="book" if expert else "",
        minimum=minimum,
        maximum=maximum,
    )


def _text(setting_id: str, label_key: str, *, expert: bool) -> SettingSpec:
    return SettingSpec(
        setting_id,
        label_key,
        f"{label_key}.help",
        SettingType.TEXT,
        "",
        expert=expert,
        group="book" if expert else "",
    )


def _flag(setting_id: str) -> SettingSpec:
    return SettingSpec(
        setting_id,
        "book.also",
        "setting.book.export.help",
        SettingType.BOOL,
        False,
    )
