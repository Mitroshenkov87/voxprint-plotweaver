# VM test

One command on the RTX 4090 VM. Cheap checks run first. The GPU passes are two short books, not the full bake-off.

```bash
bash scripts/vm_test.sh
```

On Windows:

```powershell
powershell -File scripts/vm_test.ps1
```

Run that from the repository root. The default output directory is `./out/vm-test`. `--out PATH` (`-Out` in PowerShell) changes it. The folder contains `summary.md` and `vm-test-results.tar.gz`.

`--mock` (`-Mock`) runs the same checks, a mock book, the screenshots, and the Mars hand-off without a GPU and without downloading weights. The 4090 command does not pass `--mock`.

`--smoke` (`-Smoke`) is the short pass, about ten minutes: install check, `plotweaver doctor`, `plotweaver models list`, one chapter and one scene on the detected tier, then `vxbook validate`. It does not run the pytest subset, the second tier, the screenshots, or the Mars story.

`--json` (`-Json`) prints one JSON object as the last line: `ok`, `exit`, `mode` (`full` or `smoke`), and `mock`.

Exit codes for both scripts:

| Code | Meaning |
| --- | --- |
| 0 | Every check passed. |
| 1 | A check failed. |
| 2 | Setup failed (unknown argument, or Python could not be prepared). |
| 3 | No supported NVIDIA GPU, and the run is not `--mock`. |

Neither script asks questions. A missing GPU on a non-mock run stops before the books.

## What the GPU command does

1. Pytest subset: `tests/test_models.py`, `tests/test_cli_machine.py`, `tests/test_vxbook.py`, and `tests/test_ui.py::test_vm_shots`.
2. CLI smoke with `--json` and `--dry-run`: `run`, `vxbook validate`, and `models import-forge-manifest`.
3. `plotweaver doctor`, which prints the GPU, the detected tier, and the usable VRAM.
4. Stock models for the detected tier only, then the published Forge least-censored files that fit the card, into the suite models folder (`~/.local/share/voxprint/models/llm` on Linux). The download shows the total size and stops when the drive cannot hold the next file, plus 10%, plus 2 GB. llama.cpp b11476 is downloaded under `~/.local/share/voxprint/shared/runtime` if this checkout does not already have it.
5. A 16 GB pass. Settings for this run are stored under the output directory (`PLOTWEAVER_STATE`), so the machine's saved settings stay as they were. The tier override is `16gb`. `PLOTWEAVER_VRAM_BUDGET_CAP_GB=14` makes the 24 GB card plan a 16 GB server budget (16 GB minus the 2 GB headroom). The book is `scripts/vm-brief.md`: two chapters, one scene each, dark themes on, so the stock model drafts and the Forge least-censored model fills. Exports are EPUB 3, FictionBook 2.1, `book.vxbook`, and `book.sound.vxbook`. The script validates `book.vxbook`.
6. A 24 GB pass of the same brief, with the override set to `24gb` and the budget cap cleared.
7. The short Mars story, `scripts/e2e_mars.sh`, as the Audiobook Builder hand-off sample (`book.vxbook` and `book.sound.vxbook`).
8. Tokens per second from `PLOTWEAVER_METRICS` (llama-server completions), peak VRAM from `nvidia-smi`, wall time per stage from the progress log, and the refusal count from `run --json`.
9. `summary.md` and `vm-test-results.tar.gz`.

If the cheap checks fail, the script records that and does not start the GPU books.

## Screenshots

The script saves these offscreen Qt renders (`QT_QPA_PLATFORM=offscreen`) in `screenshots/`:

| File | Screen |
| --- | --- |
| `brief-form.png` | New-book form after **Help me write the brief** |
| `progress.png` | Progress screen mid-run (story bible through the dark-scene fill) |
| `result.png` | Result screen listing `book.epub`, `book.fb2`, `book.vxbook`, and `book.sound.vxbook`. On a GPU run this is rendered again from the 24 GB export. |
| `settings-tier.png` | Settings model tier panel |
| `main-window.png` | The real main window at 1920×1080, grabbed from the display. A mock run with no display prints a note and continues. |

When no GPU is visible, the Settings panel is rendered against a stand-in RTX 4090 (24576 MiB total, 22000 MiB free) so the 24 GB tier is on screen. A real 4090 reports 24564 MiB, which is 23.99 GiB, and is still the 24 GB tier. The tier floor is 23.5 GB.

## Models this build expects

16 GB least-censored files from Model Forge: Qwen 27B `Q3_K_M.gguf` (min_vram_gb 13), and the abliterated T-lite `IQ4_XS.gguf` (5) and `Q5_K_M.gguf` (6.5). The T-lite card is an in-house ablation, not the official stock quant. Its Q5 section is a 24 GB evaluation budget; the file fits 16 GB after 2 GB headroom, so the row stays on 16 GB.

24 GB least-censored files: Qwen 27B `Huihui-Qwen3.6-27B-abliterated-ggml-model-Q5_K.gguf` (min_vram_gb 18.5) and Gemma 31B `gemma-4-31b-abliterated-Q4_K_M.gguf` (18). The Qwen Q5 file is 18.5 GB with KV, which does not fit a 16 GB card after 2 GB headroom, so it stays on 24 GB.

`gemma-4-31b-abliterated-iq3-xxs` stays disabled. The card names an IQ3_XXS quant, and that file is not in the pinned revision. `plotweaver models import-forge-manifest` enables the row when the file is published.

## Requirements

- Linux or Windows, an NVIDIA RTX 4090, the current driver, and `nvidia-smi` on `PATH`. `scripts/vm_test.ps1` is the Windows command. `scripts/vm_test.sh` is the Linux command.
- A network connection for the GGUF files. The shared folder needs tens of gigabytes free.
- Python 3.14. The script installs a `.venv` with `uv` when this checkout cannot be imported yet.
