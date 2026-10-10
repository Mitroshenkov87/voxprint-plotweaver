# Architecture

Plotweaver turns a synopsis into a book on one machine. Version 0.1.0 (Bereshit) is the engine, the bake-off harness, and a desktop shell. Cloud writing APIs are not called.

## Pipeline

The project folder holds `project.json`, a SQLite canon, and one checkpoint per finished step. A crash resumes from the next missing step.

1. Story bible: logline, characters, pronunciations.
2. Outline: chapters with a purpose and a point of view.
3. For each chapter: beats, then scene drafts, then one lightweight check and at most one rewrite, then a canon extraction.
4. Proofread while the model that should own the voice is loaded.
5. Optional reference overlap, one rewrite if the lexical check flags the book.
6. Export `book.vxbook` and EPUB 3, plus FictionBook 2.1, DOCX, Markdown, or legacy speaker marks when asked. Optional sound markup writes a second file, `book.sound.vxbook`.

Without `--yes`, autopilot stops after the bible and after the outline. Copilot also stops after each chapter. Manual also stops after each scene. The window has a checkbox for the bible and outline stop. It does not edit beats.

## One model in memory

`llama-server` from llama.cpp b11476 (MIT, Vulkan build, not vendored) serves an OpenAI-compatible completion on localhost. The binary and the GGUF files live under the shared suite folder `<models>/llm`, so a file Audiobook Builder already downloaded (Gemma 4 12B Q4_K_M) is not fetched again. `<models>/.users.json` records `plotweaver` next to the other suite apps. The VRAM budget is free memory minus the larger of 2 GB and 8 percent of the card. If the weights do not fit, layers move to RAM; a mixture-of-experts model uses `--n-cpu-moe` instead. A spill halves context (floor 4096) and the batch. The KV cache is q8_0 only when the leftover after weights is above 3 GB and nothing spilled.

The suite lock `%TEMP%/voxprint-gpu.lock` is JSON `{owner, pid, job, started, eta}` in UTC. Owner is `plotweaver`. The same process may re-enter. The lock is stale when the pid is gone or the eta is more than two hours in the past. It is held for the whole book and released when the run returns, including a run that is waiting at a gate.

## Dark themes

The toggle is chosen when the book is created.

Off: the main model does every step. A refusal is kept as a narrator paragraph and counted. There is no swap.

On: pass 1 drafts the book. A scene beat marked dark, or a refusal on a dark scene, becomes a placeholder (beats, point of view, emotional goal, links to the neighbouring scenes). Pass 2 loads the least-censored model once, fills every placeholder from the neighbouring text, and proofreads the book before unloading. There is no second verification model and no rollback loop. Least censored means the most permissive model that fits the card. It is not necessarily an abliterated tune.

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
