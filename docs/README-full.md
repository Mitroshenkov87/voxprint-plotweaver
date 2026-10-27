# VOXPrint AI Plotweaver

> [!WARNING]
> **⚠️ Deep alpha.** This software is experimental; nothing is guaranteed to work. Use at your own risk.

VOXPrint AI Plotweaver writes a whole novel from a synopsis of about five pages. It is a local desktop app in the Voxprint AI Media Suite. This release is 0.2.0 RC, codename Erev. `voxprint-plotweaver-cli --version` prints `0.2.0 RC · build N "Erev"` (a local checkout shows `dev` in place of N). It plans the book, drafts it, and exports it with local models only. No cloud writing API is called.

## System requirements

- Windows 11 24H2 or newer, or a Linux distribution from 2025 onward (x86_64).
- An NVIDIA GPU whose name contains RTX and whose compute capability is at least 8.9. That is the RTX 40-series and newer. Older cards, including the RTX 30-series, are refused.
- A card under 23.5 GB keeps 2 GB free and uses the 16 GB model tier. A card of 23.5 GB or more keeps 3 GB free and uses the 24 GB tier. Settings can override the choice when the card can run it.

The installer includes the app, Python 3.14, the Python dependencies (including voxprint-common 0.2.4, bundled so setup does not download it), and the pinned llama.cpp b11476 Vulkan runtime. After the files are copied, an interactive setup opens the VOXPrint MDL window (`voxprint-mdl download --gui --app plotweaver`). A silent install (`/VERYSILENT`) writes the same events to `%LOCALAPPDATA%\Voxprint\logs\plotweaver-mdl-install.log` on Windows and `~/.local/share/voxprint/logs/plotweaver-mdl-install.log` on Linux, and it does not open a window. A failed download does not fail setup. The app then says the models are not ready and offers Manage models, which opens `voxprint-mdl --gui --app plotweaver`. Least-censored models stay optional. The stock set follows the card's total memory, not memory another program is using at that moment.

## Download and install

Release files are on the project [releases page](https://github.com/Mitroshenkov87/voxprint-plotweaver/releases). Download `SHA256SUMS` with the installer and check it before you run anything.

Windows:

1. Download `VoxprintPlotweaver-0.2.0rc8-win64-setup.exe`.
2. In PowerShell, from the download folder: `Get-FileHash .\VoxprintPlotweaver-0.2.0rc8-win64-setup.exe -Algorithm SHA256`. The hash must match the `VoxprintPlotweaver-0.2.0rc8-win64-setup.exe` line in `SHA256SUMS`.
3. Run the setup. It installs to `C:\Program Files\VOXPrint AI Suite\Plotweaver` and needs administrator rights. The Start menu folder is VOXPrint AI Suite and the shortcut is VOXPrint AI Plotweaver. The window is `voxprint-plotweaver.exe`. `voxprint-plotweaver-cli` is added to PATH. Provisioning fills `%LOCALAPPDATA%\Voxprint\shared` while the setup window is still open. A silent install (`/SILENT` or `/VERYSILENT`) does not open the window. An interactive install offers Launch only after that step has finished.

Linux, Debian package:

```bash
sha256sum -c SHA256SUMS
sudo dpkg -i voxprint-plotweaver_0.2.0rc8_amd64.deb
sudo apt-get install -f
```

The package installer runs `voxprint-plotweaver-cli mdl-progress --quiet --installer` as the user who invoked sudo. That step logs to `~/.local/share/voxprint/logs/plotweaver-mdl-install.log`. It does not open the window, and a failed download does not fail the package.

The menu entry is VOXPrint AI Plotweaver. The files live in `/opt/voxprint-ai-suite/plotweaver`. `voxprint-plotweaver-cli` is on PATH.

Linux, tarball (any distribution with the libraries named in the `.deb` control file):

```bash
sha256sum -c SHA256SUMS
sudo tar -C / -xzf voxprint-plotweaver-0.2.0rc8-linux-x86_64.tar.gz
voxprint-plotweaver-cli mdl-progress --quiet --installer
```

An upgrade on Linux removes the previous program folder `/opt/voxprint-plotweaver`. It does not delete `%LOCALAPPDATA%\Voxprint` or the suite home. Shortcuts and PATH are updated, and models and shared files stay. `plotweaver` remains on PATH for this release and prints `plotweaver is deprecated; use voxprint-plotweaver-cli`.

## Shared files

The installer puts shared files in one place:

- Windows: `%LOCALAPPDATA%\Voxprint\shared\` (`runtime\`, `models\`, `tools\`)
- Linux: `~/.local/share/voxprint/shared/`

GGUF weights go in the suite models folder, `<home>/models/llm` (`%LOCALAPPDATA%\Voxprint\models\llm` on Windows, `~/.local/share/voxprint/models/llm` on Linux). `PLOTWEAVER_MODELS` or `VOXPRINT_MODELS_DIR` overrides that folder. llama.cpp b11476 goes in `shared/runtime`. A file another Voxprint app already installed is reused when the size and SHA-256 match, including a Forge GGUF Audiobook Builder already downloaded and a copy left in `shared/models/llm` by an older Plotweaver install. A Forge file whose published name is only the quant, such as `Q5_K_M.gguf`, is stored as the registry id plus that name so two models cannot overwrite each other. `shared/manifest.json` lists the apps that use each file. Removing Plotweaver deletes a file only when no other app still uses it.

Every launch checks whether VOXPrint MDL reports the models ready. The main window opens only then. Otherwise the app shows a short notice and Manage models, which opens `voxprint-mdl --gui --app plotweaver`. If that window cannot start, Plotweaver shows the download events in its own dialog. If the NVIDIA driver is older than the CUDA runtime needs (570.117 on Linux, 551.61 on Windows), the message includes <https://www.nvidia.com/Download/index.aspx> and the app uses the Vulkan runtime.

A card under 23.5 GB installs Gemma 4 12B Q4_K_M plus T-lite-it-2.1 Q4_K_M, and keeps 2 GB of VRAM free. A card of 23.5 GB or more installs T-pro-it-2.1 Q4_K_M only. Setup shows MDL's progress. MDL checks free disk (the file size, plus 10%, plus 2 GB) before the download. Each file is checked by revision, size, and SHA-256.

Least-censored models are optional and stay out of that stock set. On 16 GB the published files are the Forge Qwen 27B Q3_K_M, the Forge abliterated T-lite IQ4_XS and Q5_K_M, and Gemma 4 31B IQ3_XXS. On 24 GB the card also offers the Forge Qwen 27B Q5 and the Forge Gemma 31B Q4_K_M. Manage models downloads the ones that fit. A Russian book prefers the larger installed Forge T-lite. Plotweaver does not abliterate or quantize weights.

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
- The first real run needs a network connection and enough free disk for the GGUF files (several gigabytes for the 16 GB tier, more when T-pro is included). Manage models can start a failed download again. Finished files are checked before use.
- Settings says no published least-censored model fits this card when every forge row for the tier is still disabled or too large for the card.
- `sha256sum -c SHA256SUMS` must succeed before you install. A mismatch means the download is incomplete or not the file this release published.
- The **Mock model (no GPU)** checkbox writes a deterministic sample without a GPU. It is for a trial of the window, not for a novel you will keep.
- Set `PLOTWEAVER_NO_UPDATE_CHECK=1` to skip the GitHub release check. That check sends no client id. Telemetry is off.
- A long run pauses while the card stays hot and resumes when it cools. The suite GPU lock is `%TEMP%/voxprint-gpu.lock` on Windows.

## From source

Python 3.14 is required. From a checkout:

```bash
python -m venv .venv
.venv/bin/python -m pip install --find-links packaging/wheels -e ".[dev]" -e dev/plotweaver_dev
.venv/bin/voxprint-plotweaver-cli doctor --mock
.venv/bin/voxprint-plotweaver-cli gui --mock --selftest
```

`docs/architecture.md` describes the pipeline. `docs/bakeoff.md` describes the RTX 4090 bake-off and the Mars end-to-end story. `docs/vm-test.md` is the short RTX 4090 check: `bash scripts/vm_test.sh` on Linux, `powershell -File scripts/vm_test.ps1` on Windows. `LICENSE` is Apache-2.0. `NOTICE` names llama.cpp (MIT, not vendored in git) and the model-weight licences, which stay with the downloaded files.

## Documentation

The guides, the command reference, and the API notes are at <https://mitroshenkov87.github.io/voxprint-plotweaver/>. [How to write a brief](WRITING-A-BRIEF.md) is also on that site and in the Help menu.

## Roadmap

What comes next is in [ROADMAP.md](https://github.com/Mitroshenkov87/voxprint-plotweaver/blob/main/ROADMAP.md).

## ☕ Support the Project

If you find this project useful and would like to support its development, you can buy me a coffee!

- **Network:** TRON (TRC-20)
- **Accepted:** USDT or TRX
- **Address:** `TYveZBXaSpM4FEHa6iGrc7A6zuLfS4z3x6`

> ⚠️ **Important:** Please ensure you are sending funds **only** via the TRON (TRC-20) network. 
> Sending assets from other networks (such as Ethereum ERC-20, BSC BEP-20, etc.) to this address will result in **permanent loss of funds**.
