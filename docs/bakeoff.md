# Bake-off and the Mars run

Both scripts pick an interpreter that can already `import plotweaver`. If none can, they install `uv`, create `.venv` on Python 3.14, and install this checkout. `PLOTWEAVER_PYTHON` overrides the picker.

## RTX 4090 bake-off

Use a Linux VM with an RTX 4090 (or another RTX 40-series card) and the NVIDIA driver. The script downloads llama.cpp `llama-server` b11476, the Vulkan build Audiobook Builder pins, into `~/.local/share/voxprint/models/llm/llama.cpp-b11476`. GGUF weights land in `~/.local/share/voxprint/models/llm` (the shared suite folder) and are checked by revision, size, and SHA-256. The app's first run only downloads finished files. `scripts/abliterate.sh` is the separate VM job that can derive an abliterated Mistral Small, T-lite, or T-pro with Apache-2.0 and MIT tools. The bake-off downloads every enabled candidate that fits free VRAM, stock and abliterated, and writes `refusal-rates.json` for those probes. The app's own first run does not: that set is stock models only, and abliterated models are a separate Settings download offered on a GPU with at least 20 GB of VRAM. A model whose `min_vram_gb` exceeds free VRAM is skipped. A licence other than Apache-2.0 or MIT is refused unless you pass `--allow-other-license`. An empty licence tag is refused either way. Heretic is not part of this run.

```bash
bash scripts/bakeoff.sh
```

That command:

1. Installs Python dependencies if this checkout is not importable yet.
2. Downloads every enabled GGUF in `bakeoff/models.toml` that fits free VRAM, including the abliterated candidates, into `~/.local/share/voxprint/models/llm`. T-pro is the 24 GB stock drafter. Gemma 4 12B Q4_K_M is the 16 GB stock drafter and the same file Audiobook Builder uses. T-lite-it-2.1 Q4_K_M (5.03 GB) and Q5_K_M (5.85 GB) are the stock 16 GB Russian candidates. Both official GGUFs are Apache-2.0. Third-party abliterated T-lite files with no licence tag are not used. Mistral Small 3.2 Q4_K_M is the stock least-censored default. The abliterated Mistral Small, Qwen 27B, and Gemma 31B files are optional in the app and still part of this bake-off. Each manifest records the quant licence and the confirmed base licence (Apache-2.0).
3. Downloads llama.cpp b11476 Vulkan `llama-server` on first real use, into the shared `llm/llama.cpp-b11476` tree. An existing Audiobook Builder copy is reused.
4. Writes every synopsis in `bakeoff/synopses/` as three chapters with dark themes off, one candidate at a time.
5. Writes them again with dark themes on: T-pro drafts, then each least-censored model fills placeholders in one swap and proofreads. The judge scores every export, including the Russian prose from those dark-scene passes.
6. Scores the exports with the main model and builds a blind packet. It also writes `refusal-rates.json`: each candidate completes the dark-fiction probes, and the file groups stock models against abliterated ones.

| Id | Card | Role | Weights | Base |
|---|---|---|---|---|
| t-pro-it-2.1-q4 | 24 GB | stock standard | Apache-2.0 | t-tech/T-pro-it-2.1, Apache-2.0 |
| gemma-4-12b-it-q4 | 16 GB | stock standard | Apache-2.0 | google/gemma-4-12b-it, Apache-2.0 |
| t-lite-it-2.1-q4 | 16 GB | stock standard | Apache-2.0 | t-tech/T-lite-it-2.1, Apache-2.0 |
| t-lite-it-2.1-q5 | 16 GB | stock standard | Apache-2.0 | t-tech/T-lite-it-2.1, Apache-2.0 |
| mistral-small-3.2-24b-q4 | 16 GB | stock least censored (default) | Apache-2.0 | mistralai/Mistral-Small-3.2-24B-Instruct-2506, Apache-2.0 |
| mistral-small-3.2-24b-abliterated-q4 | optional | abliterated | Apache-2.0 | huihui-ai/Huihui-Mistral-Small-3.2-24B-Instruct-2506-abliterated, Apache-2.0 |
| mistral-small-3.2-24b-plotweaver-abliterated-q4 | optional, disabled until produced | abliterated | Apache-2.0 | mistralai/Mistral-Small-3.2-24B-Instruct-2506, Apache-2.0 |
| qwen3.6-27b-abliterated-q4 | optional | abliterated | Apache-2.0 | huihui-ai/Huihui-Qwen3.6-27B-abliterated, Apache-2.0 |
| gemma-4-31b-abliterated-q4 | optional | abliterated | Apache-2.0 | google/gemma-4-31b-it, Apache-2.0 |

Least censored is the most permissive model that fits, not necessarily an abliterated tune. On a 16 GB card the default is Mistral Small 3.2. TheDrummer tunes are omitted because their cards have no licence tag.

Results:

- `out/bakeoff/solo/<model-id>/<synopsis-id>/`
- `out/bakeoff/two-pass/<main>__<low>/<synopsis-id>/`
- `out/bakeoff/refusal-rates.json`
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

## Producing an abliterated model

```bash
bash scripts/abliterate.sh mistral --bakeoff
bash scripts/abliterate.sh t-lite
bash scripts/abliterate.sh t-pro
```

`mistral`, `t-lite`, and `t-pro` are the official Apache-2.0 bases. An Apache-2.0 abliterated Mistral Small quant already exists (the Huihui row above) and stays the optional download. Each Plotweaver derivation stays disabled in the registry until the run writes its SHA-256. The model card is Apache-2.0, states that the weights were modified, and for the T-Bank models credits T-Bank and Qwen. YandexGPT is not a target: its licence forbids modification and redistribution. Third-party abliterated T-lite GGUFs with no licence tag are not used.

The derivation uses PyTorch, Transformers, and llama.cpp `b11476`. Heretic is not vendored, imported, or invoked. The direction is the difference of means between original dark-fiction prompts and ordinary prose, in English and Russian, then the output projections are orthogonalised. T-lite Q4_K_M is about 5.03 GB and fits a 16 GB card. T-pro Q4_K_M is about 19.8 GB and does not. Mistral Small Q4_K_M is 14,333,922,848 bytes and fits (`min_vram_gb` 15). Settings still offers abliterated downloads only when the GPU has at least 20 GB.

The loader caps the GPU at 20 GB and spills the rest to CPU RAM and an `offload/` directory. A 24B bf16 base is about 48 GB; T-pro is larger. Plan on 64 GB of system RAM and about 120 GB of free disk. `llama-quantize` comes from the pinned b11476 Vulkan archive. `convert_hf_to_gguf.py` is the Python converter from that same tag. Clone `https://github.com/ggml-org/llama.cpp` at tag `b11476` if the converter is not already beside the runtime.

`scripts/abliterate_mistral.sh` is the old name and runs `abliterate.sh mistral`. CI checks the math on a tiny in-memory model and writes a card for each target:

```bash
bash scripts/abliterate.sh --tiny
```

## 16 GB fit experiment

Run this on the RTX 4090 after the app tests, so the card is free. The goal is real headroom on a 16 GB card: weights plus KV cache at or under 13 GiB, leaving 2–3 GB free. The probe sets llama.cpp `--fit-target` to 13312 MiB, which is that budget, even though the machine has 24 GB. A variant fails when the model buffer spills to CPU or the measured sum exceeds 13 GiB.

Candidates:

- Huihui Qwen 3.6 27B abliterated and the abliterated Gemma 4 31B, at IQ4_XS, IQ3_M, and Q3_K_M. The importance matrix is computed with llama.cpp b11476 `llama-imatrix` on `bakeoff/calibration/ru-fiction.txt` (original Russian fiction, Apache-2.0, same licence as this repo), then `llama-quantize` applies it to the Q8_0 file from the same pinned revision. The Q8 hash is recorded on first download and checked after that.
- Abliterated Mistral Small at the pinned Q4_K_M and at Q5_K_M built the same way.
- Official T-lite-it-2.1 Q4_K_M and Q5_K_M, which already fit a 16 GB card. The fit run measures them. It does not rebuild them.
- Official T-pro-it-2.1 at IQ4_XS and IQ3_M. The importance matrix is computed on the pinned Q8_0 (`T-pro-it-2.1-Q8_0.gguf`, revision `cf18787d8901c26ca9334812e7ff8070f2ddab4a`, SHA-256 `af2b3a761473a95ca31ab9b8647b9dc4288604a4a71f795ffd9402d2938c7621`, 34,816,397,344 bytes) and applied by `llama-quantize`. The Q4_K_M baseline is about 19.8 GB and is expected to fail the 13 GiB budget.

Each cell turns flash attention on and tries KV cache `q8_0` and `q4_0` at 8192 and 16384 context. Against that model's own Q4_K_M it records perplexity on the calibration text, a short score on the first two synopses, and the refusal rate. It also records prompt and generation tokens/s. Finished rows are skipped.

```bash
bash scripts/fit16gb.sh
```

The table is `out/fit16/summary.md` and `out/fit16/summary.csv`. The recommendation prefers a row that fits at 16384, then the smaller quality loss, then higher generation speed. CI does not download weights:

```bash
bash scripts/fit16gb.sh --tiny
```

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
