# Bake-off and the Mars run

Both scripts pick an interpreter that can already `import plotweaver`. If none can, they install `uv`, create `.venv` on Python 3.14, and install this checkout. `PLOTWEAVER_PYTHON` overrides the picker.

## RTX 4090 bake-off

Use a Linux VM with an RTX 4090 (or another RTX 40-series card) and the NVIDIA driver. The script downloads llama.cpp `llama-server` b11476, the Vulkan build Audiobook Builder pins, into `~/.local/share/voxprint/models/llm/llama.cpp-b11476`. GGUF weights land in `~/.local/share/voxprint/models/llm` (the shared suite folder) and are checked by revision, size, and SHA-256. Plotweaver only downloads finished files. It does not abliterate, quantize, or fit models. A model whose `min_vram_gb` exceeds free VRAM is skipped. A model that needs 20 GB of VRAM or more is an optional download: it is fetched when Settings has saved that choice, or, when nothing is saved, when the GPU has at least 20 GB. A disabled registry row is a placeholder for a file Voxprint Model Forge has not published yet, and it is never downloaded. A licence other than Apache-2.0 or MIT is refused unless you pass `--allow-other-license`. An empty licence tag is refused either way. Heretic is not part of this run.

```bash
bash scripts/bakeoff.sh
```

That command:

1. Installs Python dependencies if this checkout is not importable yet.
2. Downloads the enabled GGUF files in `bakeoff/models.toml` into `~/.local/share/voxprint/models/llm`. T-pro is the 24 GB standard drafter and is optional because it needs 20 GB of VRAM. Gemma 4 12B Q4_K_M is the 16 GB standard drafter and the same file Audiobook Builder uses. T-lite-it-2.1 Q4_K_M is the stock 16 GB Russian candidate. The least-censored passes are the most permissive model that fits: Mistral Small 3.2 Q4_K_M is the 16 GB default. An abliterated Mistral Small row is present and disabled until Voxprint Model Forge publishes the file. The Qwen 27B and Gemma 31B abliterated quants are finished files; Gemma 31B is optional because it needs 20 GB. Each downloaded manifest records the quant licence and the confirmed base licence (Apache-2.0).
3. Downloads llama.cpp b11476 Vulkan `llama-server` on first real use, into the shared `llm/llama.cpp-b11476` tree. An existing Audiobook Builder copy is reused.
4. Writes every synopsis in `bakeoff/synopses/` as three chapters with dark themes off, one candidate at a time.
5. Writes them again with dark themes on: T-pro drafts, then each least-censored model fills placeholders in one swap and proofreads. The judge scores every export, including the Russian prose from those dark-scene passes.
6. Scores the exports with the main model and builds a blind packet.

| Id | Card | Role | Weights | Base |
|---|---|---|---|---|
| t-pro-it-2.1-q4 | 24 GB, optional | standard | Apache-2.0 | t-tech/T-pro-it-2.1, Apache-2.0 |
| gemma-4-12b-it-q4 | 16 GB | standard | Apache-2.0 | google/gemma-4-12b-it, Apache-2.0 |
| t-lite-it-2.1-q4 | 16 GB | standard | Apache-2.0 | t-tech/T-lite-it-2.1, Apache-2.0 |
| mistral-small-3.2-24b-q4 | 16 GB | least censored (default) | Apache-2.0 | mistralai/Mistral-Small-3.2-24B-Instruct-2506, Apache-2.0 |
| mistral-small-3.2-24b-abliterated-q4 | 16 GB | least censored, disabled | unpublished | mistralai/Mistral-Small-3.2-24B-Instruct-2506, Apache-2.0 |
| qwen3.6-27b-abliterated-q4 | 24 GB | least censored | Apache-2.0 | huihui-ai/Huihui-Qwen3.6-27B-abliterated, Apache-2.0 |
| gemma-4-31b-abliterated-q4 | 24 GB, optional | least censored | Apache-2.0 | google/gemma-4-31b-it, Apache-2.0 |

Least censored is the most permissive model that fits, not necessarily an abliterated tune. On a 16 GB card the default is Mistral Small 3.2. TheDrummer tunes are omitted because their cards have no licence tag.

Results:

- `out/bakeoff/solo/<model-id>/<synopsis-id>/`
- `out/bakeoff/two-pass/<main>__<low>/<synopsis-id>/`
- `out/bakeoff/judge/scores.json`
- `out/bakeoff/blind-packet/reader/` without model names
- `out/bakeoff/assignment-key.json` beside that folder
- `out/bakeoff/bakeoff-results.tar.gz`

A finished `metrics.json` with `"status": "completed"` is skipped, so a crashed VM can be re-run. The human rubric is `bakeoff/RUBRIC.md`. Read the blind packet before the assignment key.

Mock slice, no GPU, used in CI:

```bash
PLOTWEAVER_MOCK=1 bash scripts/bakeoff.sh --limit 1
```

`--limit 1` still requires all ten synopsis files on disk. It writes only the first.

## Mars story

Fiction only. SpaceX may be named as the company. The crew and mission control in `scenarios/mars-e2e/synopsis.md` are invented. `outline.md` is a human scene list and is not sent to the model.

On the GPU VM, after the bake-off has downloaded T-pro, the script uses that shared file when you do not pass another GGUF:

```bash
bash scripts/e2e_mars.sh
```

Equivalent:

```bash
bash scripts/e2e_mars.sh --main-gguf "$HOME/.local/share/voxprint/models/llm/T-pro-it-2.1-Q4_K_M.gguf"
```

The 16 GB drafter, shared with Audiobook Builder, is `~/.local/share/voxprint/models/llm/gemma-4-12b-it-Q4_K_M.gguf`.

Default output is `./out/mars-e2e/`. Override with `PLOTWEAVER_MARS_OUT`. The script runs autopilot with `--yes` (no bible gate), six chapters, about 6,000 words as the target. The Audiobook Builder file is:

- `out/mars-e2e/book.vxbook` — Voxprint Book hand-off
- `out/mars-e2e/book.sound.vxbook` — the same book plus sound extension v1

`--speaker-marks` also writes numbered `audiobook/speaker-marks.txt` lines (`1. NARRATOR`) from that file.

Mock path, no GPU:

```bash
PLOTWEAVER_MOCK=1 bash scripts/e2e_mars.sh
```

The mock checks the pipeline and the export shape. It does not write 6,000 words of model prose.
