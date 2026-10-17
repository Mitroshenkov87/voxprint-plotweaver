# Plotweaver feature map

The simple shell is the same product. Every control that was on the old window, and every `plotweaver` command and flag, still has a place. A row marked **proposed removal, needs Aleksandr OK** is still reachable. Nothing in that state was deleted.

## Proposed removal

| Old feature | Where it still is | Status |
| --- | --- | --- |
| Mock model (no GPU) checkbox | Expert panel, and the Tools wizard mock checkbox. `gui --mock` and every command's `--mock` are unchanged. | proposed removal, needs Aleksandr OK |

The shell spec had taken this checkbox off the window and left it on the command line. The suite rule keeps it on the window until Aleksandr agrees it can go.

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
| Pages, words per page, scenes, chapters | Length chips and the Expert numbers. Target words on the form follow pages × words per page. | moved |
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
| `run --mock` | Expert mock checkbox. See the proposed-removal row. | proposed removal, needs Aleksandr OK |
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
| `gui` `--mock` `--selftest` | This window. Mock starts checked when the flag is set. Window self-test is on the Tools menu. | kept |
| `vxbook validate FILE` `--json` `--dry-run` | Tools → Check a Voxprint Book | kept |
| `models list` `--registry` `--json` `--dry-run` | Tools → List models | kept |
| `sound add SRC -o` `--mock` `--mirror` `--json` `--dry-run` | Tools → Add sound to a file. The result button is the same markup for the book just written. | kept |
| `brief draft` `--idea` `--language` `--mock` `--json` `--dry-run` | Help me write the brief, and Tools → the brief action | kept |
| `provision` | Tools → Provision models. The dialog asks before it copies the runtime. | kept |
| `mdl-progress` `--quiet` `--installer` | Tools → Model install. Overflow → Manage models opens the shared model window. | kept |
| `release-shared` | Tools → Release shared files. The dialog asks before it drops Plotweaver from the manifest. | kept |
| `plotweaver` as the program name | Still prints the deprecation line and asks for `voxprint-plotweaver-cli`. Command line only. | kept |

Simple mode does not hide a command behind a missing control. Expert mode, the Tools wizard, and the overflow are part of the simple window.
