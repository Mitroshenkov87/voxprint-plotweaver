"""Reference books: local text in, a measured style card, and an overlap report.

M1 overlap is lexical (lemmatised shingles, a 12-word run, MinHash, a name blocklist).
Sentence-embedding cosine against bge-m3 is not in this build; the report says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import pymorphy3
from datasketch import MinHash
from docx import Document
from ebooklib import ITEM_DOCUMENT, epub

from plotweaver.errors import PlotweaverError
from plotweaver.textio import read_text

_MORPH = pymorphy3.MorphAnalyzer()
_WORD = re.compile(r"[A-Za-zА-Яа-яЁё0-9]+", re.UNICODE)
_STOP = {
    "this",
    "that",
    "with",
    "from",
    "they",
    "them",
    "have",
    "were",
    "это",
    "этот",
    "эта",
    "как",
    "его",
    "её",
    "она",
    "они",
    "если",
    "когда",
    "только",
    "после",
    "перед",
    "chapter",
    "глава",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def read_reference(path: Path) -> str:
    """Plain text from txt, md, docx, or epub. The file stays on this machine."""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return read_text(path)
    if suffix == ".docx":
        document = Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)
    if suffix == ".epub":
        book = epub.read_epub(str(path))
        chunks: list[str] = []
        for item in book.get_items_of_type(ITEM_DOCUMENT):
            parser = _TextExtractor()
            parser.feed(item.get_content().decode("utf-8", errors="replace"))
            chunks.append(" ".join(parser.parts))
        return "\n".join(chunks)
    raise PlotweaverError(f"unsupported reference type: {path.suffix}")


def lemma(word: str) -> str:
    if re.search(r"[А-Яа-яЁё]", word):
        parsed = _MORPH.parse(word)
        if parsed:
            return str(parsed[0].normal_form)
    return word.lower()


def tokens(text: str) -> list[str]:
    return _WORD.findall(text)


def lemmas(text: str) -> list[str]:
    return [lemma(word) for word in tokens(text)]


def measure_style(text: str) -> dict[str, float | int]:
    words = tokens(text)
    sentences = [part for part in re.split(r"[.!?]+", text) if part.strip()]
    dialogue = 0
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("—", "-", "–", '"', "«")):
            dialogue += 1
    average = (len(words) / len(sentences)) if sentences else 0.0
    return {
        "words": len(words),
        "sentences": len(sentences),
        "avg_sentence_words": round(average, 1),
        "dialogue_lines": dialogue,
    }


def _shingles(words: list[str], size: int) -> set[tuple[str, ...]]:
    if len(words) < size:
        return set()
    return {tuple(words[index : index + size]) for index in range(len(words) - size + 1)}


def _minhash(shingles: set[tuple[str, ...]]) -> MinHash:
    sketch = MinHash(num_perm=64)
    for shingle in shingles:
        sketch.update(" ".join(shingle).encode("utf-8"))
    return sketch


def _name_blocklist(text: str) -> set[str]:
    counts: dict[str, int] = {}
    for match in re.finditer(r"\b[А-ЯA-Z][а-яa-z]{3,}\b", text):
        word = match.group(0)
        if word.lower() in _STOP:
            continue
        counts[word] = counts.get(word, 0) + 1
    return {word for word, count in counts.items() if count >= 2}


@dataclass
class OverlapHit:
    kind: str
    excerpt: str
    score: float = 0.0


@dataclass
class OverlapReport:
    attached: bool
    flagged: bool = False
    max_jaccard: float = 0.0
    hits: list[OverlapHit] = field(default_factory=list)
    note: str = "Lexical overlap only. Embedding cosine is not run in this build."

    def to_json(self) -> dict[str, object]:
        return {
            "attached": self.attached,
            "flagged": self.flagged,
            "max_jaccard": round(self.max_jaccard, 4),
            "note": self.note,
            "hits": [
                {"kind": hit.kind, "excerpt": hit.excerpt, "score": hit.score} for hit in self.hits
            ],
        }


def compare_texts(generated: str, reference: str, *, jaccard_limit: float = 0.02) -> OverlapReport:
    """Flag a 12-word shared run, an 8-gram Jaccard above the limit, or a blocked name."""
    report = OverlapReport(attached=True)
    gen_lemmas = lemmas(generated)
    ref_lemmas = lemmas(reference)
    gen_words = tokens(generated)
    eight_g = _shingles(gen_lemmas, 8)
    eight_r = _shingles(ref_lemmas, 8)
    if eight_g and eight_r:
        exact = len(eight_g & eight_r) / len(eight_g | eight_r)
        estimate = _minhash(eight_g).jaccard(_minhash(eight_r))
        score = max(exact, float(estimate))
        report.max_jaccard = max(report.max_jaccard, score)
        if score > jaccard_limit:
            report.flagged = True
            report.hits.append(OverlapHit("jaccard-8", f"8-gram Jaccard {score:.3f}", score))
    twelve_r = _shingles(ref_lemmas, 12)
    if twelve_r and len(gen_lemmas) >= 12:
        for index in range(len(gen_lemmas) - 11):
            window = tuple(gen_lemmas[index : index + 12])
            if window in twelve_r:
                excerpt = " ".join(gen_words[index : index + 12])
                report.flagged = True
                report.hits.append(OverlapHit("run-12", excerpt, 1.0))
                break
    blocked = _name_blocklist(reference)
    generated_words = set(tokens(generated))
    for name in sorted(blocked):
        if name in generated_words:
            report.flagged = True
            report.hits.append(OverlapHit("name", name, 1.0))
    return report
