# Plotweaver feature map

The simple shell is the same product. Every control that was on the old window, and every `plotweaver` command and flag, still has a place. The mock checkbox is the one control Aleksandr approved taking off the window. The command line still has `--mock`.

## Removed from the window

| Old feature | Where it went | Status |
| --- | --- | --- |
| Mock model (no GPU) checkbox | Not on the Expert panel and not in the Tools wizard. `gui --mock` and every command's `--mock` still select the mock backend. | removed from GUI, approved by Aleksandr 2026-10-17 12:39 MSK; CLI --mock stays |

## Window

| Old feature | New place | Status |
| --- | --- | --- |
| Home: title, version, subtitle, GPU note | Title, subtitle, and the GPU note stay on the book form. The build line stays in Help → About (Справка → О программе) and the overflow. It is not on the book form. | moved |
| Update check line | Same note under the GPU line, when a newer build exists | kept |
| Six-click easter egg | The title on the book form | kept |
| New book | Tools menu and the overflow menu. The window opens on the book form. | moved |
| Settings | Expert mode, from the overflow, the Expert toggle, or Tools → Back to leave it | moved |
| About | Overflow, and the Help menu is still first on the menu bar | moved |
| How to write a brief | Help menu and the overflow | kept |
| Back | Tools → Back turns Expert mode off. A tool dialog has Close. | moved |
| Title, Author | Book form | kept |
| Language combo | Language chips, and the language combo on the form. They write the same value. | moved |
| Synopsis | Idea box beside Write | moved |
| Notes, Help me write the brief, Copy prompt, Paste brief | Book form | kept |
| Open a synopsis file (`run --synopsis`) | Open synopsis file | kept |
| Open a brief file (`run --brief`) | Open brief file | kept |
| Pages, words per page, scenes, chapters | Length chips: story 25 pages, novella 80, novel 250 (the default), long novel 550. Simple mode’s “Your own length, pages” is the only page editor and accepts 1 to 2,000. Expert shows that same page count as a read-only live value. Above 600 pages a note says very long books are written as short scenes and quality is still being checked. A count none of the chips own shows Custom. The line under the chips is pages, words (pages × words per page), and reading time at 250 words per minute. The chapter line uses the same planner as generation. Expert words per page, scenes, and chapters stay editable on the same settings state. Chapters left at 0 follow the planner, up to 400. | moved |
| Target words (`--target-words`) | Expert “Target words (0 = pages)” | kept |
| Genre | Genre chips on the main screen: Drama, Detective, Fantasy, Science fiction, Romance, Thriller, and Other. The brief field stays editable and writes the same value. Other, or any text that is not a chip, is Custom. | moved |
| Tone | Tone chips on the main screen: Light, Serious, Dark, and With humour. The brief field stays editable. Other, or typed text, is Custom. | moved |
| Subgenre, setting | Book form | kept |
| Point of view, audience, ending | Chips on the main screen. Stored values are unchanged. Ending chips use plain words. Guessed marks stay on the form. | moved |
| Tense | More settings. The brief combo stays in sync. | moved |
| Characters, plot points, style references, prompt preview | Book form | kept |
| Reference books | Book form | kept |
| Dark/mature themes | More settings. Off is one model. On is the two-pass swap. | moved |
| Model tier | Expert model tier, also written by the dark-themes chip | moved |
| Mode (autopilot / copilot / manual) | More settings → Stops: At the plan / After each chapter / After each scene | moved |
| Stop for bible and outline approval | Stops → At the plan. Expert “Skip approval stops” is the old unchecked box and `--yes`. | moved |
| EPUB (always on) | “EPUB is always saved.” It is not a chip. | kept |
| FictionBook, DOCX, Markdown, speaker marks | More settings → Also save, one pair per format | moved |
| Sound markup on the request | More settings → Sound marks | moved |
| Prepare for audiobook | Result button. The words are «Подготовить для аудиокниги», “Prepare for audiobook”, and “Für Hörbuch vorbereiten”. Tools uses the same words on its sound checkbox. Tools → Add sound to a file is the file action. | kept |
| Write the book | Shell Write button (`simple.action.write`) | moved |
| Progress log, bar, Approve and continue | Busy page. Cancel is on that page and on the status row. | kept |
| Result path, Open folder, Save, Save as, Save a copy | Document view and the action bar. Save stays a button. Save as and Save a copy are in the ▾ menu beside Save. | kept |
| VRAM tier, abliterated download, Manage models, Save | Expert panel | moved |
| Resolved model id | Expert “Resolved model”, from `mdl.json`, shown in full. The window does not list model ids of its own. The Expert values are a full-height side panel. | kept |
| Acrylic on Windows | Unchanged | kept |
| `gui --selftest` | Tools → Window self-test | kept |
| Choose project folder, export folder | Expert | kept |
| Main GGUF, least-censored GGUF, model ids | Expert | kept |
| Dry run, JSON report | Expert, and the same checkboxes in Tools | kept |

Readers is a plain preset (Adults / Teenagers / Children). It is who the book is for. It is not a filter, and the shell gate does not read it.

## Command line

The commands themselves are unchanged. Each one also opens from Tools, except `gui`, which is this window.

| Command or flag | New place | Status |
| --- | --- | --- |
| `--version` | About, and Tools → Version | kept |
| `--selftest` (suite report, optional `--json`) | Tools → Suite self-test. JSON uses Show JSON. | kept |
| `version` | Tools → Version | kept |
| `doctor` `--mock` | Tools → GPU check | kept |
| `run --project` | Expert project folder. The window's own folder is `PLOTWEAVER_UI_PROJECT` or `out/ui-book`. | kept |
| `run --synopsis` | Idea box, and Open synopsis file | kept |
| `run --brief` | Open brief file, and Paste brief | kept |
| `run --title` `--author` `--genre` | Book form | kept |
| `run --language` | Language chips and the language combo | kept |
| `run --target-words` | Expert target words. 0 uses pages × words per page. | kept |
| `run --chapters` `--scenes-per-chapter` | Expert numbers and the length chips | kept |
| `run --dark-themes` / `--no-dark-themes` | Dark/mature themes chips | kept |
| `run --tier` | Expert model tier | kept |
| `run --mode` | Stops chips | kept |
| `run --reference` | Reference books | kept |
| `run --mock` | Command line only. The window has no mock checkbox. | removed from GUI, approved by Aleksandr 2026-10-17 12:39 MSK; CLI --mock stays |
| `run --yes` | Expert “Skip approval stops” | kept |
| `run --approve` | Approve and continue | kept |
| `run --export-dir` | Expert export folder | kept |
| `run --main-gguf` `--least-censored-gguf` | Expert GGUF fields | kept |
| `run --main-model-id` `--least-censored-model-id` | Expert model id fields | kept |
| `run --fb2` `--docx` `--markdown` `--speaker-marks` | Also save chips | kept |
| `run --sound` | Sound marks chip | kept |
| `run --json` `--dry-run` | Expert Show JSON and Dry run | kept |
| `export` and its flags (`--project`, `--export-dir`, `--mock`, formats, `--sound`, `--author`, `--json`, `--dry-run`, model paths) | Tools → Export a project | kept |
| `scenario-mars` and its flags | Tools → Mars scenario | kept |
| `bakeoff` `--results` `--mock` `--limit` `--allow-other-license` | Tools → Bake-off | kept |
| `gui` `--mock` `--selftest` | This window. `--mock` runs the book on the mock backend. There is no checkbox. Window self-test is on the Tools menu and forces the mock backend for that run only. | kept |
| `vxbook validate FILE` `--json` `--dry-run` | Tools → Check a Voxprint Book | kept |
| `models list` `--registry` `--json` `--dry-run` | Tools → List models | kept |
| `sound add SRC -o` `--mock` `--mirror` `--json` `--dry-run` | Tools → Add sound to a file. The result button is the same markup for the book just written. | kept |
| `brief draft` `--idea` `--language` `--mock` `--json` `--dry-run` | Help me write the brief, and Tools → the brief action | kept |
| `provision` | Tools → Provision models. The dialog asks before it copies the runtime. | kept |
| `mdl-progress` `--quiet` `--installer` | Tools → Model install. Overflow → Manage models opens the shared model window. | kept |
| `release-shared` | Tools → Release shared files. The dialog asks before it drops Plotweaver from the manifest. | kept |
| `plotweaver` as the program name | Still prints the deprecation line and asks for `voxprint-plotweaver-cli`. Command line only. | kept |

Simple mode does not hide a command behind a missing control. Expert mode, the Tools wizard, and the overflow are part of the simple window.

The main preset rows, top to bottom, are Genre, Tone, Length (with the page field and the reading line), Point of view, Readers, Ending, and Language. At 1200×900 those rows sit on screen without a vertical scroll. Tense, Stops, Dark/mature themes, Also save, and Sound marks are under More settings («Ещё настройки»). That expander is still simple mode.

The strip under the book form is the result and progress area. Before a book exists it says “The book text will appear here” («Здесь появится текст книги», “Hier erscheint der Text des Buches”). A run shows the progress text there, and a finished export shows the result path.

## Length limits

The length chips and the free field set `book.pages`. Words are pages × words per page (Expert, 100–600, default 250). The reading line uses 250 words per minute (`READING_WORDS_PER_MINUTE` in `src/plotweaver/ui/presets.py`). A novel of 250 pages is 62,500 words and about 4 hours, not a measured run time.

The free field accepts 1 to 2,000 (`STRUCTURAL_MAX_PAGES`). Expert shows the same number and does not edit it. The long-novel chip writes 550 and is on. Above 600 pages (`LONG_BOOK_NOTE_PAGES`) the window shows a plain note and does not block: very long books are written as short scenes, and quality is still being checked. 550 and 600 do not show that note.

Empty chapters follow `chapter_count_for` in `src/plotweaver/length.py`: at least 8 chapters, about 3,200 words a chapter, kept between 2,500 and 4,000. Scene count starts at 2 and rises so each scene fits a 4,096-token draft. English scenes stay near 750 words. Russian scenes stay near 377 words. An explicit chapter count is kept, up to the safety ceiling of 400. An explicit scene count is a minimum; the planner still adds scenes. Outlines are written in batches that fit a 2,048-token reply. The chapter line on the book form uses this same split.

2,000 pages at 250 words a page is structurally within budget (mock-tested): about 156 chapters, with each scene and each outline batch inside the token caps. That is not a proven-quality length. Russian scenes of about 377 words and the 700-character rolling summary have not been checked on a real model. The same numbers are in [Writing a brief](../WRITING-A-BRIEF.md).

| Pages | Words at 250 per page | Chapters if left at 0 | English scenes × words | Russian scenes × words |
| --- | --- | --- | --- | --- |
| 25 | 6,250 | 8 | 2 × 390 | 3 × 260 |
| 80 | 20,000 | 8 | 4 × 625 | 7 × 357 |
| 250 | 62,500 | 20 | 5 × 625 | 9 × 347 |
| 550 | 137,500 | 43 | 5 × 639 | 9 × 355 |
| 2,000 | 500,000 | 156 | 5 × 641 | 9 × 356 |
