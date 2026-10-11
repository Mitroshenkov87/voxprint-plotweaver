# Shared files

Plotweaver shares runtimes and model files with the other Voxprint apps. The installer checks what is already there and fills the gaps before the first book. A later launch only repairs a file that is missing or corrupt.

## Location

`VOXPRINT_HOME` replaces the Voxprint directory when it is set. Otherwise:

| System | Shared folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Voxprint\shared\` |
| Linux | `$XDG_DATA_HOME/voxprint/shared` or `~/.local/share/voxprint/shared` |

Inside that folder:

| Directory | Contents |
| --- | --- |
| `runtime/` | Python, llama.cpp b11476 Vulkan, llama.cpp b11476 CUDA |
| `models/llm/` | GGUF weights |
| `tools/` | Reserved for shared helper programs |
| `manifest.json` | Which apps use each resource |

`PLOTWEAVER_MODELS` still overrides the model folder. `PLOTWEAVER_LLAMA_DIR` overrides the Vulkan tree.

## Manifest

`manifest.json` is schema 1: `schema` and `components`. A component has `kind`, `version`, `path` (relative to the shared folder), `sha256`, `installed_at`, and `refs`. Plotweaver also stores `files` (name to SHA-256), `bytes`, and `source` on the component. An older file with `version` and `resources` is rewritten to schema 1 the first time it is read. Refs that belong to other apps are kept.

```json
{
  "schema": 1,
  "components": {
    "gemma-4-12b-it-q4": {
      "kind": "model",
      "version": "1",
      "path": "models/llm",
      "sha256": "<sha256>",
      "installed_at": "2026-10-11T12:00:00+00:00",
      "refs": ["audiobook-builder", "plotweaver"],
      "bytes": 7121861440,
      "files": {"gemma-4-12b-it-Q4_K_M.gguf": "<sha256>"},
      "source": "unsloth/gemma-4-12b-it-GGUF"
    }
  }
}
```

Removing Plotweaver runs `plotweaver release-shared`. That drops `plotweaver` from each component and deletes files only when `refs` is empty. A component Audiobook Builder still lists is left in place.

## Older layout

Audiobook Builder and Movie Dubber still read `<home>/models/llm` and `<home>/models/.users.json`. Plotweaver keeps writing `plotweaver: true` in that users file. When a GGUF there matches the registry size and SHA-256, the installer hard-links it into `shared/models/llm` and does not download it again. The older file is not deleted.

## What the installer checks

1. Python 3.14, copied from the app bundle or recorded from the interpreter that is already running.
2. llama.cpp b11476 Vulkan. The copy shipped beside the app is reused. Otherwise the pinned archive is downloaded.
3. llama.cpp b11476 CUDA, when the NVIDIA driver is new enough: 570.117 or newer on Linux, 551.61 or newer on Windows. Those floors are the CUDA toolkit drivers paired with the pinned builds (CUDA 12.8 on Linux, CUDA 12.4 on Windows).
4. The stock models for the detected VRAM tier.

An older driver does not stop the install. The message names the installed version, the minimum, and <https://www.nvidia.com/Download/index.aspx>. The app then uses the Vulkan runtime.

Least-censored models are not part of this set. Settings downloads them when the user turns the feature on. The window shows the file size and a time estimate, then a remaining-time line while the bytes arrive.

## Checks after install

Every launch of the window, every real `plotweaver run`, and `plotweaver --selftest --json` repeat the check. A file whose size and recorded timestamp still match is not hashed again. A missing file, a size mismatch, or a bad checksum is downloaded again. The window shows a progress dialog. Failures are one sentence, not a traceback.
