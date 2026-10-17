# Architecture

Plotweaver turns a synopsis into a book on one machine. Version 0.2.0 RC, codename Shti, is the engine, the bake-off harness, and a desktop shell. The label and the build number come from `BUILD.json`. Cloud writing APIs are not called. Model files are downloaded by VOXPrint MDL. `docs/vm-test.md` is the short RTX 4090 check.

## Pipeline

The project folder holds `project.json`, a SQLite canon, and one checkpoint per finished step. A crash resumes from the next missing step.

1. Story bible: logline, characters, pronunciations. One call, capped at 2,048 tokens.
2. Outline: parts first, then chapters in batches that fit a 2,048-token reply. A missing chapter gets one repair call, and any index still missing is filled so the list has no holes. Chapter ids stay `chNN` (three digits when the book has more than 99 chapters). When the brief leaves the chapter count empty, a short book stays at 8 chapters and a longer one uses about 2,500 to 4,000 words per chapter. Scene count rises so each scene's requested words fit a 4,096-token draft, including Russian tokenisation. An oversize beat is split before it is drafted.
3. For each chapter: beats, then scene drafts, then one lightweight check and at most one rewrite, then a canon extraction. Scene prompts carry a compact bible digest (no secrets) and a rolling story summary capped to a fixed size, plus the tail of the previous scene when it fits. That keeps the prompt and the completion inside 4,096 tokens, the spilled context on both the 16 GB and 24 GB tiers.
4. Proofread while the model that should own the voice is loaded.
5. Optional reference overlap, one rewrite if the lexical check flags the book.
6. Export `book.vxbook` and EPUB 3, plus FictionBook 2.1, DOCX, Markdown, or legacy speaker marks when asked. Optional sound markup writes a second file, `book.sound.vxbook`.

2,000 pages at 250 words per page is structurally within budget (mock-tested): about 156 chapters, with each scene and each outline batch inside the token caps. That is not a proven-quality length. Russian scenes of about 377 words and the 700-character rolling summary have not been checked for prose quality on a real model; real-model validation is pending. A longer target still runs, up to a safety ceiling of 400 chapters, but the same fixed summary is then spread over more story than it can hold. The desktop form's chapter hint is unchanged until the shell migration lands; generation uses this planner.

Without `--yes`, autopilot stops after the bible and after the outline. Copilot also stops after each chapter. Manual also stops after each scene. The window has a checkbox for the bible and outline stop. It does not edit beats.

## One model in memory

`llama-server` from llama.cpp b11476 (MIT, not vendored in git) serves an OpenAI-compatible completion on localhost. The installer prefers the CUDA build when the driver is new enough (Linux 570.117, Windows 551.61) and otherwise uses the Vulkan build Audiobook Builder pins. Both trees live in `<shared>/runtime`. The full installer also ships the Vulkan tree beside the app and copies it into the shared folder when that copy is missing. GGUF weights live in `<shared>/models/llm`. A file already stored under the older `<home>/models/llm` path, including Gemma 4 12B Q4_K_M, is hard-linked when its size and SHA-256 match and is not fetched again. `shared/manifest.json` records which apps use each resource. `<home>/models/.users.json` still records `plotweaver` next to the other suite apps. See `docs/shared.md`. The VRAM budget is free memory minus the larger of 2 GB and 8 percent of the card. `PLOTWEAVER_VRAM_BUDGET_CAP_GB` lowers that budget further, which is how the VM test emulates a 16 GB card on a 24 GB GPU. `PLOTWEAVER_METRICS`, when set to a file path, appends one JSON line per llama-server completion. If the weights do not fit, layers move to RAM; a mixture-of-experts model uses `--n-cpu-moe` instead. A spill halves context (floor 4096) and the batch. The KV cache is q8_0 only when the leftover after weights is above 3 GB and nothing spilled.

The suite lock `%TEMP%/voxprint-gpu.lock` is JSON `{app, stage, pid, started, eta}` in UTC. `app` is `plotweaver`. Older files that say `owner` and `job` are still accepted. The same process may re-enter. The lock is stale when the pid is gone or the eta is more than two hours in the past. It is held for the whole book and released when the run returns, including a run that is waiting at a gate.

## Dark themes

The toggle is chosen when the book is created.

Off: the main model does every step. A refusal is kept as a narrator paragraph and counted. There is no swap.

On: pass 1 drafts the book with the stock model. A scene beat marked dark, or a refusal on a dark scene, becomes a placeholder (beats, point of view, emotional goal, links to the neighbouring scenes). Pass 2 loads one least-censored model, fills every placeholder from the neighbouring text, and proofreads the book before unloading. There is no second verification model and no rollback loop. Least-censored models come from Model Forge. A Russian book uses the forge abliterated T-lite when that file is installed and the tier allows it. Otherwise pass 2 uses the largest installed forge model for the tier. When none is installed, pass 2 uses the stock drafter (T-pro on 24 GB, Gemma 4 12B on 16 GB). The book form's Standard / Least censored choice is separate from the VRAM tier. Settings offers the forge download when a published file fits the card. Plotweaver downloads finished GGUF files pinned by revision and SHA-256. It does not abliterate, quantize, or fit weights.

VOXPrint MDL downloads the stock set from `voxprint-app-models.json` and `mdl.json`. The window opens only when `ready('plotweaver')` reports each required file present at its expected size. Manage models runs `voxprint-mdl --gui --app plotweaver`. If that command fails, Plotweaver draws the JSON events from `voxprint-mdl download --app plotweaver --json`. Launch repair is `voxprint-mdl verify --repair --app plotweaver`.

## VRAM-aware model tiers

The registry rows carry `tier` (`16gb` or `24gb`) and `min_vram_gb`. The installer and each launch read the GPU. Under 24 GB they select the 16 GB tier and keep 2 GB free. At 24 GB or more they select the 24 GB tier and keep 3 GB free. A model from a higher tier is hidden. A model whose `min_vram_gb` exceeds the usable memory is hidden. A 24 GB card can still run 16 GB models. Settings has an advanced override (Auto, 16 GB, 24 GB). The 24 GB choice is disabled when the card cannot run a published 24 GB model. The bake-off still compares every enabled candidate that fits free VRAM.

If the tier is least censored and no separate file is set, both passes are the same model and nothing is swapped.

## References

Reference books are read for structure and style only. The anti-copy check is lexical: lemmatised 8-gram Jaccard, a shared run of 12 lemmas, a MinHash estimate, and a capitalised name that appears at least twice in the reference and once in the draft. An overlap report is written next to the export. Embedding cosine (bge-m3) is not in this build.

## What is intentionally absent

Visual bible and outline editors, LoRA training, cloud APIs, and a fiction content filter. Prompts frame the work as fiction, refuse real-world harm instructions, and refuse named living people as characters. They are not jailbreaks.

Ideas, not code, came from public notes on Dramatron, Re3, DOC, novel-studio, and show-me-the-story. Those trees were not copied.

## GPU and heat

A real run requires an NVIDIA GPU whose name contains RTX and whose compute capability is at least 8.9 (RTX 40 series or newer). `PLOTWEAVER_FAKE_GPU` exists for tests. The thermal rule matches the suite note, not an older instantaneous 87 °C check: full speed for 2.5 hours, then pause while the 5-minute median stays at or above 83 °C, or while a thermal or power throttle bit has been set for more than 60 seconds. Resume at or below 75 °C with the throttle clear. A missing sensor never pauses the job.

## Updates

The window may GET `repos/Mitroshenkov87/voxprint-plotweaver/releases/latest` with a fixed User-Agent and no client id. Set `PLOTWEAVER_NO_UPDATE_CHECK=1` to skip it. Nothing else is sent.
