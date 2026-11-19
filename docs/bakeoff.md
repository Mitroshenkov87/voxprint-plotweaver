# Bake-off and the Mars run

Both scripts pick an interpreter that can already `import plotweaver`. If none can, they install `uv`, create `.venv` on Python 3.14, and install this checkout. `PLOTWEAVER_PYTHON` overrides the picker.

## RTX 4090 bake-off

Use a Linux VM with an RTX 4090 (or another RTX 40-series card) and the NVIDIA driver. The script downloads llama.cpp `llama-server` b11476, the Vulkan build Audiobook Builder pins, into `~/.local/share/voxprint/shared/runtime/llama.cpp-b11476`. GGUF weights land in `~/.local/share/voxprint/models/llm` and are checked by revision, size, and SHA-256. The installer downloads the stock files for the detected tier. A later launch only repairs a missing or corrupt file. It detects VRAM and selects the 16 GB tier (2 GB held back) or the 24 GB tier (3 GB held back). Plotweaver does not abliterate, quantize, or fit weights. Model Forge publishes those files. The bake-off downloads every enabled candidate that fits free VRAM, stock and abliterated, and writes `refusal-rates.json` for those probes. The installer does not: that set is stock models for the selected tier. Least-censored models are a separate Settings download when a published file fits the card. A model from a higher tier, or whose `min_vram_gb` exceeds the usable memory, is hidden in the app. The bake-off skip is free VRAM only. A licence other than Apache-2.0 or MIT is refused unless you pass `--allow-other-license`. An empty licence tag is refused either way.

```bash
bash scripts/bakeoff.sh
```

That command:

1. Installs Python dependencies if this checkout is not importable yet.
2. Uses the GGUF files VOXPrint MDL has already stored under `~/.local/share/voxprint/models/llm`. T-pro Q4_K_M is the 24 GB stock drafter. Gemma 4 12B Q4_K_M and T-lite-it-2.1 Q4_K_M are the 16 GB stock set. T-lite Q5_K_M is optional and is not stock. On 16 GB the enabled least-censored files include Forge Qwen Q3_K_M, both Forge T-lite quants, and Gemma 4 31B IQ3_XXS. On 24 GB the set also includes Forge Qwen Q5 and Forge Gemma 31B Q4_K_M. Disabled placeholders are skipped. Each manifest records the quant licence and the confirmed base licence (Apache-2.0).
3. Uses the bundled llama.cpp b11476 Vulkan `llama-server` when the installer shipped one. Otherwise downloads it into the shared `llm/llama.cpp-b11476` tree. An existing Audiobook Builder copy is reused.
4. Writes every synopsis in `bakeoff/synopses/` as three chapters with dark themes off, one candidate at a time.
5. Writes them again with dark themes on: T-pro drafts, then each least-censored model fills placeholders in one swap and proofreads. The judge scores every export, including the Russian prose from those dark-scene passes.
6. Scores the exports with the main model and builds a blind packet. It also writes `refusal-rates.json`: each candidate completes the dark-fiction probes, and the file groups stock models against abliterated ones.

| Id | Tier | Role | Weights | Base |
|---|---|---|---|---|
| t-pro-it-2.1-q4 | 24 GB | stock standard | Apache-2.0 | t-tech/T-pro-it-2.1, Apache-2.0 |
| gemma-4-12b-it-q4 | 16 GB | stock standard | Apache-2.0 | google/gemma-4-12b-it, Apache-2.0 |
| t-lite-it-2.1-q4 | 16 GB | stock standard | Apache-2.0 | t-tech/T-lite-it-2.1, Apache-2.0 |
| t-lite-it-2.1-q5 | 16 GB | stock standard | Apache-2.0 | t-tech/T-lite-it-2.1, Apache-2.0 |
| qwen3.6-27b-abliterated-q3-k-m | 16 GB | least censored | Apache-2.0 | huihui-ai/Huihui-Qwen3.6-27B-abliterated-MTP-GGUF, Apache-2.0 |
| t-lite-it-2.1-abliterated-iq4-xs | 16 GB | Russian least censored | Apache-2.0 | t-tech/T-lite-it-2.1, Apache-2.0 |
| t-lite-it-2.1-abliterated-q5 | 16 GB | Russian least censored | Apache-2.0 | t-tech/T-lite-it-2.1, Apache-2.0 |
| qwen3.6-27b-abliterated-q5 | 24 GB | least censored | Apache-2.0 | huihui-ai/Huihui-Qwen3.6-27B-abliterated-MTP-GGUF, Apache-2.0 |
| gemma-4-31b-abliterated-q4 | 24 GB | least censored | Apache-2.0 | paperscarecrow/Gemma-4-31B-it-abliterated, Apache-2.0 |
| gemma-4-31b-abliterated-iq3-xxs | 16 GB, on demand | least censored | Apache-2.0 | paperscarecrow/Gemma-4-31B-it-abliterated, Apache-2.0 |

Default install is Huihui Gemma 4 12B abliterated Q4_K_M and the Forge T-lite IQ4_XS on 16 GB, plus Huihui Qwen3.6 27B abliterated Q5_K on 24 GB until the Forge T-pro file is published. Stock Gemma 4 12B Q4, T-lite Q4, and T-pro Q4 stay as optional rows. Qwen Q3_K_M, both Forge T-lite quants, and Gemma 4 31B IQ3_XXS fit 16 GB. The Forge T-lite card is an ablation, not the official stock GGUF. Qwen Q5 is 18.5 GB with KV and does not fit 16 GB after 2 GB headroom, so it stays on 24 GB. Gemma Q4 stays on 24 GB at min_vram_gb 18. Other 16 GB fit rows with empty hashes stay disabled. TheDrummer tunes are omitted because their cards have no licence tag.

Manage models asks VOXPrint MDL for an on-demand file. A Forge publication still uses this JSON shape when a row is filled by hand:

```json
{
  "models": [
    {
      "id": "gemma-4-31b-abliterated-iq3-xxs",
      "revision": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      "size": 1,
      "repo": "Mitroshenkov87/voxprint-gemma4-31b",
      "filename": "gemma-4-31b-abliterated-IQ3_XXS.gguf",
      "min_vram_gb": 6
    }
  ]
}
```

`id`, `revision`, `sha256`, and `size` are required. `revision` is a 40-hex commit and `sha256` is 64 hex. `repo`, `filename`, and `min_vram_gb` are optional. The command enables that row. Stock rows are refused. Re-run it when Model Forge publishes a new hash.

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
