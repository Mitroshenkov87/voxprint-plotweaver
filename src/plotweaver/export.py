"""Markdown, DOCX, EPUB, and the Audiobook Builder package."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from docx import Document
from ebooklib import epub

from plotweaver.domain import Gender
from plotweaver.errors import assert_never


@dataclass
class RenderedParagraph:
    text: str
    speaker: str
    gender: Gender


@dataclass
class RenderedChapter:
    title: str
    paragraphs: list[RenderedParagraph]


def speaker_mark(speaker: str, gender: Gender) -> str:
    """One Audiobook Builder mark: NARRATOR, MALE: Name, or FEMALE: Name."""
    if not speaker or speaker.upper() == "NARRATOR":
        return "NARRATOR"
    match gender:
        case Gender.MALE:
            return f"MALE: {speaker}"
        case Gender.FEMALE:
            return f"FEMALE: {speaker}"
        case Gender.UNSPECIFIED:
            return "NARRATOR"
        case _ as unreachable:
            assert_never(unreachable)


def render_markdown(chapters: list[RenderedChapter]) -> tuple[str, str]:
    """Return (book.md, speaker-marks.txt). Marks line up with paragraph blocks, not headings."""
    blocks: list[str] = []
    marks: list[str] = []
    for chapter in chapters:
        title = chapter.title.strip() or "Chapter"
        blocks.append(f"# {title}")
        for paragraph in chapter.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            blocks.append(text)
            marks.append(speaker_mark(paragraph.speaker, paragraph.gender))
    markdown = "\n\n".join(blocks) + "\n"
    marks_text = ("\n".join(marks) + "\n") if marks else ""
    return markdown, marks_text


def write_docx(path: Path, chapters: list[RenderedChapter]) -> None:
    document = Document()
    for chapter in chapters:
        document.add_heading(chapter.title.strip() or "Chapter", level=1)
        for paragraph in chapter.paragraphs:
            text = paragraph.text.strip()
            if text:
                document.add_paragraph(text)
    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))


def write_epub(path: Path, title: str, language: str, chapters: list[RenderedChapter]) -> None:
    book = epub.EpubBook()
    book.set_identifier(f"plotweaver-{title}")
    book.set_title(title)
    book.set_language(language)
    book.add_author("Voxprint AI Plotweaver")
    items: list[epub.EpubHtml] = []
    for index, chapter in enumerate(chapters, start=1):
        body = [f"<h1>{escape(chapter.title)}</h1>"]
        for paragraph in chapter.paragraphs:
            text = paragraph.text.strip()
            if text:
                body.append(f"<p>{escape(text)}</p>")
        item = epub.EpubHtml(title=chapter.title, file_name=f"ch{index:02d}.xhtml", lang=language)
        item.content = "".join(body)
        book.add_item(item)
        items.append(item)
    book.toc = tuple(items)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", *items]
    path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(path), book)


def write_bundle(
    directory: Path,
    title: str,
    language: str,
    chapters: list[RenderedChapter],
    overlap: dict[str, object],
) -> tuple[str, str]:
    """Write every export next to each other. Returns the markdown and the marks."""
    directory.mkdir(parents=True, exist_ok=True)
    markdown, marks = render_markdown(chapters)
    (directory / "book.md").write_text(markdown, encoding="utf-8", newline="\n")
    audio = directory / "audiobook"
    audio.mkdir(exist_ok=True)
    (audio / "book.md").write_text(markdown, encoding="utf-8", newline="\n")
    (audio / "speaker-marks.txt").write_text(marks, encoding="utf-8", newline="\n")
    write_docx(directory / "book.docx", chapters)
    write_epub(directory / "book.epub", title, language, chapters)
    payload = json.dumps(overlap, ensure_ascii=False, indent=2) + "\n"
    (directory / "overlap-report.json").write_text(payload, encoding="utf-8", newline="\n")
    return markdown, marks


def publish_exports(source: Path, dest: Path) -> None:
    """Copy the export bundle to the folder the user asked for."""
    if source.resolve() == dest.resolve():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("book.md", "book.docx", "book.epub", "overlap-report.json"):
        item = source / name
        if item.is_file():
            shutil.copy2(item, dest / name)
    audio = source / "audiobook"
    if audio.is_dir():
        target = dest / "audiobook"
        target.mkdir(exist_ok=True)
        for item in audio.iterdir():
            if item.is_file():
                shutil.copy2(item, target / item.name)
