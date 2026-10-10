# Voxprint AI Plotweaver

Voxprint AI Plotweaver writes a whole novel from a synopsis of about five pages. It is a local desktop app in the Voxprint AI Media Suite. This release is 0.2.0 RC, codename Tzaruf. `plotweaver --version` prints `0.2.0 RC · build N "Tzaruf"` (a local checkout shows `dev` in place of N). It plans the book, drafts it, and exports it with local models only. No cloud writing API is called.

## System requirements

- Windows 11 24H2 or newer, or a Linux distribution from 2025 onward (x86_64).
- An NVIDIA GPU whose name contains RTX and whose compute capability is at least 8.9. That is the RTX 40-series and newer. Older cards, including the RTX 30-series, are refused.
- A 16 GB card keeps 2 GB free and uses the 16 GB model tier. A 24 GB card keeps 3 GB free and uses the 24 GB tier. Cards between those sizes use the 16 GB tier. Settings can override the choice when the card can run it.

The installer includes the app, Python 3.14, the Python dependencies, and the pinned llama.cpp b11476 Vulkan runtime. Model weights download on the first real run.

## Download and install

Release files are on the [v0.2.0-rc4 release](https://github.com/Mitroshenkov87/voxprint-plotweaver/releases/tag/v0.2.0-rc4). Download `SHA256SUMS` with the installer and check it before you run anything.

Windows:

1. Download `VoxprintPlotweaver-0.2.0rc4-win64-setup.exe`.
2. In PowerShell, from the download folder: `Get-FileHash .\VoxprintPlotweaver-0.2.0rc4-win64-setup.exe -Algorithm SHA256`. The hash must match the `VoxprintPlotweaver-0.2.0rc4-win64-setup.exe` line in `SHA256SUMS`.
3. Run the setup. It installs for the current user under `%LOCALAPPDATA%\Voxprint\Plotweaver` and adds a Voxprint entry to the Start menu. Administrator rights are not required.

Linux, Debian package:

```bash
sha256sum -c SHA256SUMS
sudo dpkg -i voxprint-plotweaver_0.2.0rc4_amd64.deb
sudo apt-get install -f
```

The menu entry is Voxprint AI Plotweaver. The files live in `/opt/voxprint-plotweaver`.

Linux, tarball (any distribution with the libraries named in the `.deb` control file):

```bash
sha256sum -c SHA256SUMS
tar -xzf voxprint-plotweaver-0.2.0rc4-linux-x86_64.tar.gz
./voxprint-plotweaver/plotweaver-gui.sh
```

## First run and model download

Open the app on the NVIDIA machine. The first real book reads the GPU, selects the 16 GB or 24 GB tier, and downloads the stock models that fit into the shared suite folder:

- Windows: `%LOCALAPPDATA%\Voxprint\models\llm`
- Linux: `~/.local/share/voxprint/models/llm`

A card under 24 GB installs Gemma 4 12B plus T-lite-it-2.1 Q4_K_M and Q5_K_M. A 24 GB card also installs T-pro-it-2.1. A model file already downloaded by Audiobook Builder is reused. Each file is checked by revision, size, and SHA-256.

Least-censored models are a separate download from Settings, and only when a published file fits the card. On 16 GB those are the Forge Qwen 27B Q3_K_M and the Forge abliterated T-lite IQ4_XS and Q5_K_M. On 24 GB the card also offers the Forge Qwen 27B Q5 and the Forge Gemma 31B Q4_K_M. The Gemma 31B IQ3_XXS row stays disabled until `plotweaver models import-forge-manifest` fills it. A Russian book prefers the larger installed Forge T-lite. Plotweaver does not abliterate or quantize weights.

Settings also has an advanced VRAM-tier override (Auto, 16 GB, 24 GB). The 24 GB choice stays disabled when the card cannot run a published 24 GB model.

## Writing a book from a synopsis

Choose New book. Set the title, the author, and the language. Paste a synopsis, or write loose notes and press **Help me write the brief**. Pages and words per page set the length. Leave chapters at 0 to let the outline decide, or type a count. Point of view and tense stay on the form. The prompt preview is editable.

Leave **Stop for bible and outline approval** unchecked to write the book through. Check it when you want to read `bible.json` and `outline.json` and press Approve and continue. The window does not open an editor for the bible, the outline, or scene beats.

Choose Standard or Least censored. Standard is the stock model for the tier. Least censored uses an installed Model Forge model when one fits, and otherwise the stock drafter.

Press Write the book. Progress stays on the next page. The finished files land in the project folder.

## Dark/mature themes

Check **Dark/mature themes** before you start. With it off, the stock model writes every scene. With it on, the stock model drafts the book, and a least-censored model later fills scenes that were marked dark or that the stock model refused. When no least-censored file is installed, that second pass uses the stock drafter.

## Reference books

Add reference accepts `.txt`, `.md`, `.docx`, and `.epub`. Plotweaver reads them for structure and style, then runs a lexical overlap check against the draft. It does not copy those books into the novel, and it does not use an embedding model.

## Exports

EPUB 3 is always written (`book.epub`), with a navigation document and the suite cover. The project also always writes `book.vxbook`. Optional checkboxes add FictionBook 2.1 (`--fb2` on the command line), DOCX, Markdown, and the legacy numbered speaker-marks file. The author field is stored in the book manifest, the EPUB, and FictionBook title-info.

## Add sound markup

Check **Add sound markup**, or run `plotweaver sound add FILE -o OUT` on an existing book. The app writes a second file, `book.sound.vxbook`, and leaves `book.vxbook` unchanged.

## Hand-off to Audiobook Builder

Import `book.vxbook` into Audiobook Builder. Import `book.sound.vxbook` when you turned sound markup on. Both apps share the model folder, so a GGUF one of them has already stored is not downloaded again.

## Troubleshooting

- The setup refuses Windows older than 11 24H2 (build 26100).
- A GPU whose name does not contain RTX, or whose compute capability is below 8.9, is refused. Install the current NVIDIA driver. On Linux the package also needs the Vulkan loader (`libvulkan1`), which the `.deb` depends on.
- The first real run needs a network connection and enough free disk for the GGUF files (several gigabytes for the 16 GB tier, more when T-pro is included). A failed download can be started again from the app. Finished files are checked before use.
- Settings says no published least-censored model fits this card when every forge row for the tier is still disabled or too large for the free memory.
- `sha256sum -c SHA256SUMS` must succeed before you install. A mismatch means the download is incomplete or not the file this release published.
- The **Mock model (no GPU)** checkbox writes a deterministic sample without a GPU. It is for a trial of the window, not for a novel you will keep.
- Set `PLOTWEAVER_NO_UPDATE_CHECK=1` to skip the GitHub release check. That check sends no client id. Telemetry is off.
- A long run pauses while the card stays hot and resumes when it cools. The suite GPU lock is `%TEMP%/voxprint-gpu.lock` on Windows.

## From source

Python 3.14 is required. From a checkout:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/plotweaver doctor --mock
.venv/bin/plotweaver gui --mock --selftest
```

`docs/architecture.md` describes the pipeline. `docs/bakeoff.md` describes the RTX 4090 bake-off and the Mars end-to-end story. `docs/vm-test.md` is the short RTX 4090 check, `bash scripts/vm_test.sh`. `LICENSE` is Apache-2.0. `NOTICE` names llama.cpp (MIT, not vendored in git) and the model-weight licences, which stay with the downloaded files.

## Documentation

The guides, the command reference, and the API notes are at <https://mitroshenkov87.github.io/voxprint-plotweaver/>. [How to write a brief](docs/WRITING-A-BRIEF.md) is also on that site and in the Help menu.

## Roadmap

What comes next is in [ROADMAP.md](ROADMAP.md).

## ☕ Support the Project

If you find this project useful and would like to support its development, you can buy me a coffee!

- **Network:** TRON (TRC-20)
- **Accepted:** USDT or TRX
- **Address:** `TYveZBXaSpM4FEHa6iGrc7A6zuLfS4z3x6`

> ⚠️ **Important:** Please ensure you are sending funds **only** via the TRON (TRC-20) network. 
> Sending assets from other networks (such as Ethereum ERC-20, BSC BEP-20, etc.) to this address will result in **permanent loss of funds**.
