# Voxprint AI Plotweaver

Voxprint AI Plotweaver writes a whole novel from a synopsis of about five pages. It is a local desktop app in the Voxprint AI Media Suite. Version 0.1.0 (Bereshit) plans the book, drafts it, and exports it with local models only. No cloud writing API is called.

The engine is a command-line pipeline with checkpoints. The window is a native PySide6 shell for a new book, progress, and the result. A rented Linux GPU machine can run the model bake-off and the Mars end-to-end story with one command each.

## Status

This build runs the pipeline on a deterministic mock model, which is what CI uses, and on `llama-server` from llama.cpp b11476 (the Vulkan build Audiobook Builder pins) when an NVIDIA RTX 40-series GPU (or newer) is present. Python 3.14 is the required interpreter. The libraries this app imports publish 3.14 wheels (PySide6, httpx, python-docx, ebooklib, datasketch, pymorphy3, Pillow), so the line was not lowered.

Not in this build, on purpose:

- Visual editors for the story bible, the outline, or scene beats. Copilot and manual modes stop at those gates; they do not open an editor.
- Embedding cosine (bge-m3). The anti-copy check is lexical and writes an overlap report.
- LoRA training and any cloud model API.
- The full yo and stress normaliser. Audiobook Builder owns that. Plotweaver applies a short unambiguous yo dictionary and stress marks taken from the story bible, and writes those marks into `.vxbook`.

## Platforms

Windows 11 24H2 or newer, and Linux distributions from 2025 onward. A real book requires an NVIDIA GPU whose name contains RTX and whose compute capability is at least 8.9. Older cards, including RTX 30-series, are refused. Tests and CI pass `--mock` or `PLOTWEAVER_MOCK=1` and do not need a GPU.

One large model is loaded at a time. The VRAM budget is free memory minus the larger of 2 GB and 8 percent of the card. The suite GPU lock is `%TEMP%/voxprint-gpu.lock`. After 2.5 hours at full speed the job pauses while the 5-minute median temperature stays at or above 83 °C, or while thermal throttling lasts more than 60 seconds, and resumes at or below 75 °C.

Telemetry is off. The window may check GitHub releases of `Mitroshenkov87/voxprint-plotweaver` and sends no client id. Set `PLOTWEAVER_NO_UPDATE_CHECK=1` to skip that request.

## Quick start

From this checkout, with Python 3.14:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/plotweaver doctor --mock
.venv/bin/plotweaver gui --mock --selftest
```

Write a one-chapter book without a GPU:

```bash
.venv/bin/plotweaver run --mock --yes --project out/demo --synopsis scenarios/mars-e2e/synopsis.md --chapters 1 --target-words 800
```

A real book needs a GGUF and a supported GPU. The first real run reads VRAM, picks the 16 GB or 24 GB tier, and downloads the stock models that fit into the shared suite folder `~/.local/share/voxprint/models/llm`. A card under 24 GB keeps 2 GB free and installs Gemma 4 12B plus T-lite-it-2.1 Q4_K_M and Q5_K_M. A 24 GB card keeps 3 GB free and also installs T-pro and Mistral Small 3.2. Mistral Small needs 15 GB, so it is not installed on a 16 GB card. Abliterated models are not in the stock set. Settings offers that separate download when the GPU has at least 20 GB of VRAM, and an advanced override for the VRAM tier. A dark-theme book uses an installed abliterated model when one fits, and otherwise the stock model the tier can run. Pass any other Apache-2.0 or MIT file with `--main-gguf`. Other licences are refused unless you add `--allow-other-license`. An empty licence tag is refused either way. Plotweaver does not abliterate or quantize weights. Those files come from Model Forge.

```bash
plotweaver run --yes --project out/my-book --synopsis my-synopsis.md --main-gguf /path/to/model.gguf
```

`--yes` skips the bible and outline gates. Omit it, read `bible.json` and `outline.json` in the project folder, then continue with `--approve`.

The finished book is `book.vxbook` (the Audiobook Builder hand-off) and EPUB 3 (`book.epub`), with a navigation document and the suite cover. Add `--speaker-marks` for the legacy numbered `audiobook/speaker-marks.txt` pair, `--fb2` for FictionBook 2.1, `--docx` for Word, or `--markdown` for a Markdown file. `--sound`, or Add sound markup in the window, writes a second file `book.sound.vxbook` and leaves `book.vxbook` unchanged. The window has the same checkboxes. `--author` sets the name stored in the book manifest, the EPUB, and FictionBook title-info. `plotweaver vxbook validate FILE` runs the format checklist. `plotweaver sound add FILE -o OUT` adds sound markup to an existing book.

## Bake-off (RTX 4090 Linux VM)

```bash
bash scripts/bakeoff.sh
```

The script installs dependencies if needed, downloads every finished candidate that fits free VRAM (stock and abliterated), runs all ten Russian synopses for three chapters on each solo model, then runs the two-pass dark-theme path. It also records a refusal rate for each candidate. The app's default install stays stock-only and follows the VRAM tier. Results land in `out/bakeoff/`, including `bakeoff-results.tar.gz` and a blind reading packet. The rubric is `bakeoff/RUBRIC.md`. Exact paths and the skip-if-completed rule are in `docs/bakeoff.md`.

CI runs the same harness without a GPU:

```bash
PLOTWEAVER_MOCK=1 bash scripts/bakeoff.sh --limit 1
```

## Mars end-to-end story

`scenarios/mars-e2e/synopsis.md` is a short Russian science-fiction synopsis (about 6,000 words, six chapters) about a SpaceX crewed mission to Mars. The crew and mission control are invented. SpaceX is the company on the hardware and the contract. `outline.md` is a human scene list and is not sent to the model.

On the GPU VM, after the weights are on disk:

```bash
bash scripts/e2e_mars.sh --main-gguf "$HOME/.local/share/voxprint/models/llm/T-pro-it-2.1-Q4_K_M.gguf"
```

Output defaults to `./out/mars-e2e/`. The Audiobook Builder import is `book.vxbook`. The same run also writes `book.sound.vxbook` (VXBOOK v1.1 + sound extension v1) beside it. `--speaker-marks` also writes the legacy numbered pair under `audiobook/`. Override the folder with `PLOTWEAVER_MARS_OUT`.

Without a GPU:

```bash
PLOTWEAVER_MOCK=1 bash scripts/e2e_mars.sh
```

## Layout

`docs/architecture.md` describes the pipeline, the single resident model, and the dark-theme toggle. `docs/audiobook-export.md` describes the export. `LICENSE` is Apache-2.0. `NOTICE` names llama.cpp (MIT, not vendored) and the model-weight licences, which stay with the files.

The Windows installer is a small online Inno Setup package (Start menu folder Voxprint, minimum Windows 11 24H2). The Linux package is a tarball and a `.deb` with the sources, a desktop file, and the icon. CI builds both.
## ☕ Support the Project

If you find this project useful and would like to support its development, you can buy me a coffee!

- **Network:** TRON (TRC-20)
- **Accepted:** USDT or TRX
- **Address:** `TYveZBXaSpM4FEHa6iGrc7A6zuLfS4z3x6`

> ⚠️ **Important:** Please ensure you are sending funds **only** via the TRON (TRC-20) network. 
> Sending assets from other networks (such as Ethereum ERC-20, BSC BEP-20, etc.) to this address will result in **permanent loss of funds**.
