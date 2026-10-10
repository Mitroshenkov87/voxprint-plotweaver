# Audiobook Builder export

Plotweaver writes a bundle the suite Audiobook Builder can import.

`audiobook/book.md` uses a Markdown heading per chapter (`#` plus the title). Paragraphs are separated by a blank line. Headings are not paragraphs.

`audiobook/speaker-marks.txt` has one line per paragraph, in the same order. A line is `NARRATOR`, `MALE: Name`, or `FEMALE: Name`. A named speaker with no gender becomes `NARRATOR`.

Yo (ё) is restored from a short unambiguous dictionary. The word все is not rewritten to всё. Stress is the combining acute U+0301 taken from the story bible `pronunciation` field, longer surfaces first. A word that already carries the acute is left alone. The full yo and stress normaliser belongs to Audiobook Builder; this pass is only so the import is not bare.

The same folder also receives `book.md`, `book.docx`, `book.epub`, and `overlap-report.json` one level up, next to `audiobook/`.
