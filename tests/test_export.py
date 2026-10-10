"""EPUB 3, FictionBook 2.1, and the optional export flags."""

from __future__ import annotations

import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from lxml import etree

from plotweaver.cli import main
from plotweaver.domain import Gender, normalize_formats
from plotweaver.export import (
    RenderedChapter,
    RenderedParagraph,
    fb2_genre,
    fb2_schema_dir,
    write_bundle,
    write_epub,
    write_fb2,
)

_NS = {
    "f": "http://www.gribuser.ru/xml/fictionbook/2.0",
    "l": "http://www.w3.org/1999/xlink",
}


def _chapters() -> list[RenderedChapter]:
    return [
        RenderedChapter(
            "Глава 1",
            [
                RenderedParagraph("Корабль стоял в пыли.", "NARRATOR", Gender.UNSPECIFIED),
                RenderedParagraph("Илья смотрел на горизонт.", "Илья Воронов", Gender.MALE),
            ],
        ),
        RenderedChapter("Пустая", []),
    ]


def test_genre_codes_follow_the_schema() -> None:
    assert fb2_genre("science fiction", "ru") == "sf"
    assert fb2_genre("sf_space", "en") == "sf_space"
    assert fb2_genre("fantasy", "ru") == "russian_fantasy"
    assert fb2_genre("fantasy", "en") == "foreign_fantasy"
    assert fb2_genre("prose", "en") == "narrative"
    assert fb2_genre("", "ru") == "narrative"


def test_normalize_formats_keeps_epub() -> None:
    assert normalize_formats(None) == ["epub"]
    assert normalize_formats(["docx", "fb2", "nope"]) == ["epub", "docx", "fb2"]


def test_fb2_validates_against_the_vendored_schema(tmp_path: Path) -> None:
    schema_dir = fb2_schema_dir()
    assert (schema_dir / "LICENSE.md").is_file()
    assert (schema_dir / "FictionBook.xsd").is_file()
    path = tmp_path / "book.fb2"
    write_fb2(
        path,
        title="Пыль над Аресом",
        language="ru",
        author="Илья Воронов",
        genre="science fiction",
        synopsis="# Заголовок\n\nКороткий синопсис про Марс.\n\nВторая фраза.",
        chapters=_chapters(),
    )
    schema = etree.XMLSchema(etree.parse(str(schema_dir / "FictionBook.xsd")))
    document = etree.parse(str(path))
    schema.assertValid(document)
    title = document.xpath("/f:FictionBook/f:description/f:title-info", namespaces=_NS)[0]
    assert title.xpath("f:genre/text()", namespaces=_NS) == ["sf"]
    assert title.xpath("f:book-title/text()", namespaces=_NS) == ["Пыль над Аресом"]
    assert title.xpath("f:lang/text()", namespaces=_NS) == ["ru"]
    assert title.xpath("f:author/f:first-name/text()", namespaces=_NS) == ["Илья"]
    assert title.xpath("f:author/f:last-name/text()", namespaces=_NS) == ["Воронов"]
    annotation = " ".join(title.xpath("f:annotation/f:p/text()", namespaces=_NS))
    assert "Заголовок" in annotation
    assert "Короткий синопсис про Марс." in annotation
    assert "Вторая фраза." in annotation
    assert title.xpath("f:coverpage/f:image/@l:href", namespaces=_NS) == ["#cover.png"]
    sections = document.xpath("/f:FictionBook/f:body/f:section/f:title/f:p/text()", namespaces=_NS)
    assert sections == ["Глава 1", "Пустая"]
    assert document.xpath("/f:FictionBook/f:binary/@id", namespaces=_NS) == ["cover.png"]
    assert document.xpath("/f:FictionBook/f:binary/@content-type", namespaces=_NS) == ["image/png"]
    assert document.xpath("string(/f:FictionBook/f:binary)", namespaces=_NS).strip()


def test_blank_author_is_a_nickname(tmp_path: Path) -> None:
    path = tmp_path / "book.fb2"
    write_fb2(
        path,
        title="Untitled",
        language="en",
        author="",
        genre="",
        synopsis="",
        chapters=[
            RenderedChapter("One", [RenderedParagraph("Hello.", "NARRATOR", Gender.UNSPECIFIED)])
        ],
    )
    schema = etree.XMLSchema(etree.parse(str(fb2_schema_dir() / "FictionBook.xsd")))
    document = etree.parse(str(path))
    schema.assertValid(document)
    assert document.xpath(
        "/f:FictionBook/f:description/f:title-info/f:author/f:nickname/text()",
        namespaces=_NS,
    ) == ["Plotweaver"]
    assert (
        document.xpath("/f:FictionBook/f:description/f:title-info/f:annotation", namespaces=_NS)
        == []
    )


def test_epub3_has_nav_and_cover(tmp_path: Path) -> None:
    path = tmp_path / "book.epub"
    write_epub(path, "Пыль над Аресом", "ru", _chapters(), author="Марина Лебедева")
    with zipfile.ZipFile(path) as package:
        names = package.namelist()
        assert names[0] == "mimetype"
        assert package.read("mimetype") == b"application/epub+zip"
        opf = package.read("EPUB/content.opf").decode("utf-8")
        nav = package.read("EPUB/nav.xhtml").decode("utf-8")
        assert 'version="3.0"' in opf
        assert 'properties="nav"' in opf or "properties='nav'" in opf
        assert "cover-image" in opf
        assert "EPUB/nav.xhtml" in names
        assert "EPUB/cover.png" in names
        assert "ch01.xhtml" in "".join(names)
    assert "epub:type" in nav and "toc" in nav
    assert 'role="doc-toc"' not in nav
    assert "epub:prefix" not in package_text(path)
    assert "Глава 1" in nav


def package_text(path: Path) -> str:
    with zipfile.ZipFile(path) as package:
        return "\n".join(
            package.read(name).decode("utf-8")
            for name in package.namelist()
            if name.endswith((".xhtml", ".opf", ".html"))
        )


def test_bundle_writes_epub_and_optional_formats(tmp_path: Path) -> None:
    write_bundle(tmp_path, "Title", "en", _chapters(), {}, author="Ada Lovelace")
    assert (tmp_path / "book.epub").is_file()
    assert (tmp_path / "audiobook" / "book.md").is_file()
    assert (tmp_path / "audiobook" / "speaker-marks.txt").is_file()
    assert not (tmp_path / "book.fb2").is_file()
    assert not (tmp_path / "book.docx").is_file()
    assert not (tmp_path / "book.md").is_file()
    extra = tmp_path / "extra"
    write_bundle(
        extra,
        "Title",
        "en",
        _chapters(),
        {"hits": []},
        formats=["fb2", "docx", "markdown"],
        synopsis="A blurb.",
    )
    assert (extra / "book.fb2").is_file()
    assert (extra / "book.docx").is_file()
    assert (extra / "book.md").is_file()
    assert (extra / "book.epub").is_file()


def test_cli_optional_formats(tmp_path: Path) -> None:
    synopsis = tmp_path / "synopsis.md"
    synopsis.write_text("Короткий синопсис.\n\nЕщё одна фраза.", encoding="utf-8")
    export = tmp_path / "out"
    code = main(
        [
            "run",
            "--mock",
            "--yes",
            "--project",
            str(tmp_path / "project"),
            "--synopsis",
            str(synopsis),
            "--title",
            "Проверка",
            "--author",
            "Илья Воронов",
            "--genre",
            "science fiction",
            "--chapters",
            "1",
            "--target-words",
            "800",
            "--fb2",
            "--docx",
            "--markdown",
            "--export-dir",
            str(export),
        ]
    )
    assert code == 0
    assert (export / "book.epub").is_file()
    assert (export / "book.fb2").is_file()
    assert (export / "book.docx").is_file()
    assert (export / "book.md").is_file()
    assert (export / "audiobook" / "speaker-marks.txt").is_file()
    schema = etree.XMLSchema(etree.parse(str(fb2_schema_dir() / "FictionBook.xsd")))
    schema.assertValid(etree.parse(str(export / "book.fb2")))


def test_epubcheck_when_configured(tmp_path: Path) -> None:
    jar = os.environ.get("EPUBCHECK", "")
    if not jar:
        pytest.skip("EPUBCHECK is not set")
    path = tmp_path / "book.epub"
    write_epub(path, "Пыль над Аресом", "ru", _chapters(), author="Илья Воронов")
    completed = subprocess.run(
        ["java", "-jar", jar, str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
