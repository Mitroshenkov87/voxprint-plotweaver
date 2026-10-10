# Bake-off and the Mars run

Both scripts pick an interpreter that can already `import plotweaver`. If none can, they install `uv`, create `.venv` on Python 3.14, and install this checkout. `PLOTWEAVER_PYTHON` overrides the picker.

## RTX 4090 bake-off

Use a Linux VM with an RTX 4090 (or another RTX 40-series card), the NVIDIA driver, and a CUDA 12 or 13 user-space new enough for the llama.cpp build the script selects. Weights land in `~/.local/share/voxprint/models` and are checked by size and SHA-256. A model whose `min_vram_gb` exceeds free VRAM is skipped. A licence other than Apache-2.0 or MIT is refused unless you pass `--allow-other-license`.

```bash
bash scripts/bakeoff.sh
```

That command:

1. Installs Python dependencies if this checkout is not importable yet.
2. Downloads the three GGUF files in `bakeoff/models.toml` (T-pro as the main Russian model, then the Qwen and Gemma low-refusal quants).
3. Downloads a llama.cpp `llama-server` CUDA build on first real use.
4. Writes every synopsis in `bakeoff/synopses/` as three chapters with dark themes off, one candidate at a time.
5. Writes them again with dark themes on: T-pro drafts, then each low-refusal model fills placeholders in one swap and proofreads.
6. Scores the exports with the main model and builds a blind packet.

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

On the GPU VM, after the bake-off has downloaded T-pro (or with any other Apache-2.0 GGUF you pass explicitly):

```bash
bash scripts/e2e_mars.sh --main-gguf "$HOME/.local/share/voxprint/models/T-pro-it-2.1-Q4_K_M.gguf"
```

Equivalent:

```bash
export PLOTWEAVER_MAIN_GGUF="$HOME/.local/share/voxprint/models/T-pro-it-2.1-Q4_K_M.gguf"
bash scripts/e2e_mars.sh
```

Default output is `./out/mars-e2e/`. Override with `PLOTWEAVER_MARS_OUT`. The script runs autopilot with `--yes` (no bible gate), six chapters, about 6,000 words as the target. The Audiobook Builder file is:

- `out/mars-e2e/book.vxbook` — Voxprint Book hand-off
- `out/mars-e2e/book.sound.vxbook` — the same book plus sound extension v1

`--speaker-marks` also writes numbered `audiobook/speaker-marks.txt` lines (`1. NARRATOR`) from that file.

Mock path, no GPU:

```bash
PLOTWEAVER_MOCK=1 bash scripts/e2e_mars.sh
```

The mock checks the pipeline and the export shape. It does not write 6,000 words of model prose.
