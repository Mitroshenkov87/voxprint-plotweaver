# Plotweaver feature map

The simple shell is the same product. Every control that was on the old window, and every `plotweaver` command and flag, still has a place. The mock checkbox is the one control Aleksandr approved taking off the window. The command line still has `--mock`.

## Removed from the window

| Old feature | Where it went | Status |
| --- | --- | --- |
| Mock model (no GPU) checkbox | Not on the Expert panel and not in the Tools wizard. `gui --mock` and every command's `--mock` still select the mock backend. | removed from GUI, approved by Aleksandr 2026-10-17 12:39 MSK; CLI --mock stays |

## Window

| Old feature | New place | Status |
| --- | --- | --- |
| Home: title, version, subtitle, GPU note | Top of the book form, and About | moved |
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
| Pages, words per page, scenes, chapters | Length chips: story 25 pages, novella 80, novel 250 (the default). The long-novel chip (~500–600 pages) stays on the row and is switched off until long books are reworked. Simple mode has “Your own length, pages” and Expert has Pages; both stop at 250. A count none of the chips own shows Custom. The line under the chips is pages, words (pages × words per page), and reading time at 250 words per minute. Expert words per page stay on the same settings state. | moved |
| Target words (`--target-words`) | Expert “Target words (0 = pages)” | kept |
| Genre, subgenre, tone, setting | Book form | kept |
| Point of view, tense, audience, ending | Chips. Stored values are unchanged. Ending chips use plain words. Guessed marks stay on the form. | moved |
| Characters, plot points, style references, prompt preview | Book form | kept |
| Reference books | Book form | kept |
| Dark/mature themes | Dark/mature themes chips. Off is one model. On is the two-pass swap. | moved |
| Model tier | Expert model tier, also written by the dark-themes chip | moved |
| Mode (autopilot / copilot / manual) | Stops chips: At the plan / After each chapter / After each scene | moved |
| Stop for bible and outline approval | Stops → At the plan. Expert “Skip approval stops” is the old unchecked box and `--yes`. | moved |
| EPUB (always on) | “EPUB is always saved.” It is not a chip. | kept |
| FictionBook, DOCX, Markdown, speaker marks | Also save chips, one pair per format | moved |
| Sound markup on the request | Sound marks chips | moved |
| Add sound markup on the result | Result action, and Tools → Add sound to a file | kept |
| Write the book | Shell Write button (`simple.action.write`) | moved |
| Progress log, bar, Approve and continue | Busy page. Cancel is on that page and on the status row. | kept |
| Result path, Open folder, Save as, Save a copy | Document view and the action bar | kept |
| VRAM tier, abliterated download, Manage models, Save | Expert panel | moved |
| Resolved model id | Expert “Resolved model”, from `mdl.json`. The window does not list model ids of its own. | kept |
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

## Length limits

The length chips and the free field set `book.pages`. Words are pages × words per page (Expert, 100–600, default 250). The reading line uses 250 words per minute (`READING_WORDS_PER_MINUTE` in `src/plotweaver/ui/presets.py`). A novel of 250 pages is 62,500 words and about 4 hours, not a measured run time.

The window stops at 250 pages (`MAX_RELIABLE_PAGES`). That is the largest page count that still fits the current generator at the default 250 words a page and 2 scenes a chapter. 250 pages is 62,500 words and 25 chapters. An indented outline of 25 chapters, one Russian sentence of purpose each, is about 1,900 tokens and fits in the 2,048-token outline call. 26 chapters leave almost no room once the model indents the JSON. Each scene call budgets 3 tokens a word and stops at 4,096 (`runner._max_tokens`). 25 chapters × 2 scenes ask for 1,250 words, which is 3,750 tokens and still fits.

A 550-page book does not fit those calls. It is 137,500 words. Empty chapters use `min(40, max(8, round(words / 2500)))`, so the chapter count stops at 40 instead of 55, and each scene is asked for about 1,718 words. The runner would budget 5,154 tokens and then stop at 4,096, so the scene is cut off. A 40-chapter outline is about 2,400 tokens even when each purpose is one short sentence, so the 2,048-token outline call is cut off too. The long-novel chip stays visible and is switched off, with the note that very long books arrive in the next update. The free field and Expert pages show the same plain hint when they are already at 250. Raising words per page, or setting scenes per chapter to 1, makes a 250-page book longer than this budget. Expert “Target words (0 = pages)” can still ask for more words; the generator caps below still apply. The command line is not limited to 250 pages.

| Pages | Words at 250 per page | Chapters if left at 0 | Words asked per scene | Window |
| --- | --- | --- | --- | --- |
| 25 | 6,250 | 8 (floor; the uncapped round is 2) | 400 (floor). 16 scenes × 400 is 6,400 words, a little over the target. | offered |
| 80 | 20,000 | 8 | 1,250 | offered |
| 250 | 62,500 | 25 | 1,250 (3,750 tokens, inside 4,096) | offered, and the ceiling |
| 550 | 137,500 | 40 (ceiling; the uncapped round is 55) | 1,718 (the 4,096-token scene call clips a 5,154-token budget) | chip shown, switched off |

Empty chapters use `min(40, max(8, round(words / 2500)))`. Scenes per chapter default to 2 (Expert 1–8). Words per scene are `max(400, words // (chapters × scenes))`. Expert chapters stop at 40. A scene prompt carries the bible, that chapter, that scene, and the last 1,500 characters of the previous scene. It does not carry the whole book. When VRAM is tight the model context is halved and does not go below 4,096. The same numbers are in [Writing a brief](../WRITING-A-BRIEF.md).
