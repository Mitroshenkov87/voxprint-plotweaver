# Audiobook Builder export

Plotweaver writes a bundle the suite Audiobook Builder can import.

`audiobook/book.md` uses a Markdown heading per chapter (`#` plus the title). Paragraphs are separated by a blank line. Headings are not paragraphs.

`audiobook/speaker-marks.txt` has one line per paragraph, in the same order. A line is `NARRATOR`, `MALE: Name`, or `FEMALE: Name`. A named speaker with no gender becomes `NARRATOR`.

Yo (ё) is restored from a short unambiguous dictionary. The word все is not rewritten to всё. Stress is the combining acute U+0301 taken from the story bible `pronunciation` field, longer surfaces first. A word that already carries the acute is left alone. The full yo and stress normaliser belongs to Audiobook Builder; this pass is only so the import is not bare.

EPUB 3 (`book.epub`) is always written beside `audiobook/`, with a navigation document and the suite cover. FictionBook 2.1 (`--fb2`, `book.fb2`), DOCX (`--docx`), and Markdown (`--markdown`, `book.md`) are optional. The window has the same three checkboxes. `overlap-report.json` is written with every export. A suite-native `.vxbook` package is not in this build.
