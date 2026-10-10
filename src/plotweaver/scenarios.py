"""Fixed scenarios shipped with the repo. The Mars run is the 4090 end-to-end sample."""

from __future__ import annotations

from pathlib import Path

from plotweaver.domain import BookMode, BookRequest, Language, ModelTier
from plotweaver.paths import repo_root

MARS_TITLE = "Пыль над Аресом"
MARS_TARGET_WORDS = 6000
MARS_CHAPTERS = 6


def mars_synopsis_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "scenarios" / "mars-e2e" / "synopsis.md"


def mars_outline_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / "scenarios" / "mars-e2e" / "outline.md"


def mars_request(root: Path | None = None) -> BookRequest:
    """Short Russian science-fiction book: invented crew, SpaceX as the company."""
    synopsis = mars_synopsis_path(root).read_text(encoding="utf-8").strip()
    return BookRequest(
        title=MARS_TITLE,
        language=Language.RU,
        synopsis=synopsis,
        genre="science fiction",
        target_words=MARS_TARGET_WORDS,
        chapter_count=MARS_CHAPTERS,
        scenes_per_chapter=2,
        pov="third-person limited",
        tense="past",
        dark_themes=False,
        tier=ModelTier.STANDARD,
        mode=BookMode.AUTOPILOT,
    )
