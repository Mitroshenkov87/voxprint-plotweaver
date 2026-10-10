# Audiobook Builder export

Plotweaver writes `book.vxbook`, the Voxprint Book package Audiobook Builder imports. The manifest records `generator` and `created_by` as `plotweaver` plus the app version, and `source.format` as `plotweaver`. Each non-narrator paragraph carries a `vx:speaker` directive with `src="auto"` when the canon store inferred the speaker. `speakers.json` lists gender, age group, and voice hints from the story bible. A cover, when the suite mark decodes, is `cover.avif`. Yo (ё) is restored from a short unambiguous dictionary. The word все is not rewritten to всё. Stress is the combining acute U+0301 taken from the story bible `pronunciation` field, longer surfaces first. A word that already carries the acute is left alone.

`plotweaver vxbook validate FILE` runs the format checklist. Offset mismatches are warnings. A major version this build does not know is refused.

`--speaker-marks` also writes the legacy pair from that `.vxbook`. `audiobook/book.md` keeps chapter headings and paragraphs. `audiobook/speaker-marks.txt` has one numbered line per paragraph (`1. NARRATOR`, `2. MALE: Name`, `3. FEMALE: Name`). A character with no gender becomes `NARRATOR`.

EPUB 3 (`book.epub`) is always written beside `book.vxbook`, with a navigation document and the suite cover. FictionBook 2.1 (`--fb2`, `book.fb2`), DOCX (`--docx`), and Markdown (`--markdown`, `book.md`) are optional. The window has the same checkboxes. `overlap-report.json` is written with every export.
