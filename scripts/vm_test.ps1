# Windows twin of scripts/vm_test.sh.
# Non-interactive. Exit 0 pass, 1 a check failed, 2 setup, 3 no supported GPU.
# --smoke (-Smoke) is the short pass: install check, doctor, models list,
# one chapter and one scene on the detected tier, then vxbook validate.
# Windows PowerShell 5.1 writes `>` as UTF-16. Command output is captured in
# Python as UTF-8. Short notes use Out-File -Encoding utf8.
param()

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Out = "./out/vm-test"
$Mock = $false
$Smoke = $false
$Json = $false

for ($i = 0; $i -lt $args.Count; $i++) {
    $arg = $args[$i]
    switch ($arg) {
        { $_ -in "--mock", "-Mock" } { $Mock = $true }
        { $_ -in "--smoke", "-Smoke" } { $Smoke = $true }
        { $_ -in "--json", "-Json" } { $Json = $true }
        { $_ -in "--out", "-Out" } {
            if ($i + 1 -ge $args.Count -or [string]::IsNullOrWhiteSpace($args[$i + 1])) {
                [Console]::Error.WriteLine("--out needs a directory")
                exit 2
            }
            $i++
            $Out = $args[$i]
        }
        default {
            [Console]::Error.WriteLine("unknown argument: $arg")
            exit 2
        }
    }
}

if ($env:PLOTWEAVER_MOCK -eq "1") {
    $Mock = $true
}

function Write-Result([int]$Code) {
    if (-not $Json) {
        return
    }
    $ok = if ($Code -eq 0) { "true" } else { "false" }
    $mode = if ($Smoke) { "smoke" } else { "full" }
    $mockFlag = if ($Mock) { "true" } else { "false" }
    Write-Output "{`"ok`":$ok,`"exit`":$Code,`"mode`":`"$mode`",`"mock`":$mockFlag}"
}

function Find-Python {
    if ($env:PLOTWEAVER_PYTHON -and (Test-Path $env:PLOTWEAVER_PYTHON)) {
        & $env:PLOTWEAVER_PYTHON -c "import plotweaver" 2>$null
        if ($LASTEXITCODE -eq 0) { return $env:PLOTWEAVER_PYTHON }
    }
    $venv = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path $venv) {
        & $venv -c "import plotweaver" 2>$null
        if ($LASTEXITCODE -eq 0) { return $venv }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        & $python.Source -c "import plotweaver" 2>$null
        if ($LASTEXITCODE -eq 0) { return $python.Source }
    }
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        [Console]::Error.WriteLine("uv is not on PATH and plotweaver is not installed")
        return $null
    }
    & uv venv --python 3.14 (Join-Path $Root ".venv")
    if ($LASTEXITCODE -ne 0) { return $null }
    $created = Join-Path $Root ".venv\Scripts\python.exe"
    & uv pip install --python $created --find-links (Join-Path $Root "packaging\wheels") -e "$Root[dev]" -e (Join-Path $Root "dev\plotweaver_dev")
    if ($LASTEXITCODE -ne 0) { return $null }
    return $created
}

$Py = Find-Python
if (-not $Py) {
    [Console]::Error.WriteLine("could not prepare Python")
    Write-Result 2
    exit 2
}
if ($Mock) {
    & $Py -c "import plotweaver_dev" 2>$null
    if ($LASTEXITCODE -ne 0) {
        & uv pip install --python $Py --find-links (Join-Path $Root "packaging\wheels") -e "$Root[dev]" -e (Join-Path $Root "dev\plotweaver_dev")
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("--mock needs the dev extra and it could not be installed")
            Write-Result 2
            exit 2
        }
    }
}

$env:PLOTWEAVER_NO_UPDATE_CHECK = "1"
$env:PYTHONUTF8 = "1"
$env:QT_QPA_PLATFORM = "offscreen"
$env:PLOTWEAVER_STATE = Join-Path $Out "state"
New-Item -ItemType Directory -Force -Path @(
    (Join-Path $Out "checks"),
    (Join-Path $Out "screenshots"),
    (Join-Path $Out "16gb"),
    (Join-Path $Out "24gb"),
    (Join-Path $Out "mars"),
    (Join-Path $Out "state")
) | Out-Null
if ($Mock) { "1" | Out-File -FilePath (Join-Path $Out "mode.txt") -Encoding utf8 }
else { "0" | Out-File -FilePath (Join-Path $Out "mode.txt") -Encoding utf8 }

function Invoke-Captured([string]$Stdout, [string]$Stderr, [string[]]$Cmd) {
    # Windows PowerShell 5.1 drops an empty argument when it starts a program.
    # "-" means this stream is not written to a file.
    $script = @'
import subprocess
import sys
from pathlib import Path

out, err, *cmd = sys.argv[1:]
if out == '-':
    out = ''
if err == '-':
    err = ''
proc = subprocess.run(
    [sys.executable, *cmd],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
if out:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(proc.stdout)
if err:
    path = Path(err)
    path.parent.mkdir(parents=True, exist_ok=True)
    if err == out:
        with path.open("ab") as handle:
            handle.write(proc.stderr)
    else:
        path.write_bytes(proc.stderr)
elif proc.returncode and proc.stderr:
    sys.stderr.buffer.write(proc.stderr)
raise SystemExit(proc.returncode)
'@
    & $Py -c $script $Stdout $Stderr @Cmd
    return $LASTEXITCODE
}

function Test-Gpu {
    if ($Mock) { return $true }
    & $Py -c "from plotweaver.hardware import is_supported, query_gpu; info = query_gpu(); raise SystemExit(0 if info is not None and is_supported(info) else 1)"
    return $LASTEXITCODE -eq 0
}

if (-not (Test-Gpu)) {
    [Console]::Error.WriteLine("no supported NVIDIA GPU")
    Write-Result 3
    exit 3
}

function Get-DetectedTier {
    if ($Mock) { $env:PLOTWEAVER_FAKE_GPU = "NVIDIA GeForce RTX 4090,8.9,24564,20000" }
    $name = & $Py -c @'
from plotweaver.hardware import query_gpu
from plotweaver.registry import detected_tier
import sys
info = query_gpu()
print(detected_tier(info.total_gb)) if info else sys.exit(1)
'@
    if ($Mock) { Remove-Item Env:PLOTWEAVER_FAKE_GPU -ErrorAction SilentlyContinue }
    if ($LASTEXITCODE -ne 0) { return $null }
    return "$name".Trim()
}

function Set-Tier([string]$Tier) {
    $env:PLOTWEAVER_VM_TIER = $Tier
    & $Py -c "import os; from plotweaver.settings import save_model_tier_override, save_uncensored_models; save_uncensored_models(True); save_model_tier_override(os.environ['PLOTWEAVER_VM_TIER'])"
    Remove-Item Env:PLOTWEAVER_VM_TIER -ErrorAction SilentlyContinue
}

function Invoke-Book([string]$Tier, [int]$Chapters = 2, [int]$Scenes = 1, [bool]$Dark = $true) {
    $dir = Join-Path $Out $Tier
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    $mockArgs = @()
    if ($Mock) {
        $mockArgs = @("--mock")
        "n/a" | Out-File -FilePath (Join-Path $dir "vram-peak-mib.txt") -Encoding utf8
    }
    else {
        if ($Tier -eq "16gb") {
            $env:PLOTWEAVER_VRAM_BUDGET_CAP_GB = "14"
            Set-Tier "16gb"
        }
        else {
            Remove-Item Env:PLOTWEAVER_VRAM_BUDGET_CAP_GB -ErrorAction SilentlyContinue
            Set-Tier "24gb"
        }
        Invoke-Captured (Join-Path $dir "doctor.txt") "-" @("-m", "plotweaver", "doctor") | Out-Null
    }
    $env:PLOTWEAVER_METRICS = Join-Path $dir "metrics.jsonl"
    "" | Out-File -FilePath $env:PLOTWEAVER_METRICS -Encoding utf8
    $runArgs = @(
        "-m", "plotweaver", "run",
        "--project", (Join-Path $dir "project"),
        "--brief", (Join-Path $Root "scripts\vm-brief.md"),
        "--chapters", "$Chapters",
        "--scenes-per-chapter", "$Scenes",
        "--yes", "--fb2", "--sound", "--json"
    ) + $mockArgs
    if ($Dark) { $runArgs += "--dark-themes" }
    $started = Get-Date
    $code = Invoke-Captured (Join-Path $dir "run.json") (Join-Path $dir "stderr.log") $runArgs
    $elapsed = ((Get-Date) - $started).TotalSeconds
    "$elapsed" | Out-File -FilePath (Join-Path $dir "wall-seconds.txt") -Encoding utf8
    if ($code -ne 0) { return $code }
    return Invoke-Captured (Join-Path $dir "vxbook-validate.json") "-" @(
        "-m", "plotweaver", "vxbook", "validate",
        (Join-Path $dir "project\export\book.vxbook"),
        "--json"
    )
}

function Save-Shots([string]$ExportDir = "") {
    $env:PLOTWEAVER_VM_SHOTS = Join-Path $Out "screenshots"
    if ($ExportDir) { $env:PLOTWEAVER_VM_EXPORT = $ExportDir } else { Remove-Item Env:PLOTWEAVER_VM_EXPORT -ErrorAction SilentlyContinue }
    & $Py -c "import os; from pathlib import Path; from plotweaver.ui.vm_shots import save_vm_shots; raw = os.environ.get('PLOTWEAVER_VM_EXPORT', ''); export = Path(raw) if raw else None; save_vm_shots(Path(os.environ['PLOTWEAVER_VM_SHOTS']), export_dir=export)"
    return $LASTEXITCODE
}

function Save-MainWindow {
    $prev = $env:QT_QPA_PLATFORM
    Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
    $shot = Join-Path $Out "screenshots\main-window.png"
    $code = Invoke-Captured "-" "-" @(
        "-c",
        "from pathlib import Path; from plotweaver.ui.vm_shots import save_main_window; save_main_window(Path(r'$shot'))"
    )
    if ($null -ne $prev) { $env:QT_QPA_PLATFORM = $prev }
    return $code
}

function Write-Summary {
    $env:PLOTWEAVER_VM_OUT = $Out
    & $Py -c "import os; from pathlib import Path; from plotweaver.vm_report import write_summary; write_summary(Path(os.environ['PLOTWEAVER_VM_OUT']))"
    return $LASTEXITCODE
}

$status = 0

if ($Smoke) {
    Write-Output "smoke install check"
    & $Py -c "import plotweaver"
    if ($LASTEXITCODE -ne 0) {
        Write-Result 2
        exit 2
    }
    Write-Output "smoke doctor"
    if ($Mock) {
        $code = Invoke-Captured (Join-Path $Out "doctor.txt") "-" @("-m", "plotweaver", "doctor", "--mock")
    }
    else {
        $code = Invoke-Captured (Join-Path $Out "doctor.txt") "-" @("-m", "plotweaver", "doctor")
    }
    if ($code -ne 0) { $status = 1 }
    Write-Output "smoke models list"
    $code = Invoke-Captured (Join-Path $Out "checks\models.json") "-" @("-m", "plotweaver", "models", "list", "--json")
    if ($code -ne 0) { $status = 1 }
    $tier = Get-DetectedTier
    if (-not $tier) { $status = 1 }
    elseif ($status -eq 0) {
        Write-Output "smoke book $tier"
        $book = Invoke-Book $tier 1 1 $false
        if ($book -ne 0) { $status = 1 }
    }
    Write-Summary | Out-Null
    if ($LASTEXITCODE -ne 0) { $status = 1 }
    Write-Result $status
    exit $status
}

Write-Output "pytest subset"
$pytestLog = Join-Path $Out "checks\pytest.log"
$code = Invoke-Captured $pytestLog $pytestLog @(
    "-m", "pytest",
    "tests/test_models.py",
    "tests/test_cli_machine.py",
    "tests/test_vxbook.py",
    "tests/test_ui.py::test_vm_shots",
    "-q"
)
if ($code -ne 0) { $status = 1 }

Write-Output "CLI smoke"
$code = Invoke-Captured (Join-Path $Out "checks\run-dry.json") "-" @(
    "-m", "plotweaver", "run",
    "--project", (Join-Path $Out "checks\dry-project"),
    "--brief", (Join-Path $Root "scripts\vm-brief.md"),
    "--chapters", "2",
    "--scenes-per-chapter", "1",
    "--dark-themes", "--yes", "--fb2", "--sound", "--json",
    "--dry-run", "--mock"
)
if ($code -ne 0) { $status = 1 }
$code = Invoke-Captured (Join-Path $Out "checks\vxbook-dry.json") "-" @(
    "-m", "plotweaver", "vxbook", "validate",
    (Join-Path $Root "tests\fixtures\vxbook\manifest.json"),
    "--dry-run", "--json"
)
if ($code -ne 0) { $status = 1 }
$env:VM_ROOT = $Root
$env:VM_OUT = Join-Path $Out "checks"
& $Py -c "import json, os; from pathlib import Path; root = Path(os.environ['VM_ROOT']); out = Path(os.environ['VM_OUT']); (out / 'models.toml').write_text((root / 'bakeoff' / 'models.toml').read_text(encoding='utf-8'), encoding='utf-8'); (out / 'forge.json').write_text(json.dumps({'models': [{'id': 'gemma-4-31b-abliterated-iq3-xxs', 'revision': 'ab' * 20, 'sha256': 'ab' * 32, 'size': 1}]}), encoding='utf-8')"
$code = Invoke-Captured (Join-Path $Out "checks\import-dry.json") "-" @(
    "-m", "plotweaver", "models", "import-forge-manifest",
    (Join-Path $Out "checks\forge.json"),
    "--registry", (Join-Path $Out "checks\models.toml"),
    "--dry-run", "--json"
)
if ($code -ne 0) { $status = 1 }

Write-Output "screenshots"
if ((Save-Shots) -ne 0) { $status = 1 }
Write-Output "main window"
$shotCode = Save-MainWindow
if ($shotCode -ne 0) {
    if ($Mock) { Write-Output "main window skipped (no display)" }
    else { $status = 1 }
}

if ($Mock) {
    Write-Output "mock 16 GB pass"
    if ((Invoke-Book "16gb") -ne 0) { $status = 1 }
    Write-Output "mock 24 GB pass"
    if ((Invoke-Book "24gb") -ne 0) { $status = 1 }
    Write-Output "Mars hand-off"
    $mars = Join-Path $Out "mars"
    & $Py -m plotweaver scenario-mars --yes --mock --export-dir $mars --project (Join-Path $mars "project")
    if ($LASTEXITCODE -ne 0) { $status = 1 }
    else {
        & $Py -m plotweaver sound add (Join-Path $mars "book.vxbook") -o (Join-Path $mars "book.sound.vxbook") --mock
        if ($LASTEXITCODE -ne 0) { $status = 1 }
    }
}
else {
    Write-Output "GPU doctor"
    $code = Invoke-Captured (Join-Path $Out "doctor.txt") "-" @("-m", "plotweaver", "doctor")
    if ($code -ne 0) { $status = 1 }
    if ($status -eq 0) {
        Write-Output "model download"
        $code = Invoke-Captured (Join-Path $Out "checks\download.txt") "-" @(
            "-c",
            "from plotweaver.hardware import require_supported_gpu; from plotweaver.install import ensure_default_install, ensure_uncensored_models; gpu = require_supported_gpu(); print(f'{gpu.name}: {gpu.free_gb:.1f} of {gpu.total_gb:.1f} GB free'); print('stock', ensure_default_install(free_gb=gpu.free_gb, total_gb=gpu.total_gb)); print('forge', ensure_uncensored_models(total_vram_gb=gpu.total_gb, free_gb=gpu.free_gb))"
        )
        if ($code -ne 0) { $status = 1 }
    }
    if ($status -eq 0) {
        Write-Output "16 GB pass"
        if ((Invoke-Book "16gb") -ne 0) { $status = 1 }
        Write-Output "24 GB pass"
        if ((Invoke-Book "24gb") -ne 0) { $status = 1 }
        $export = Join-Path $Out "24gb\project\export"
        if (Test-Path (Join-Path $export "book.vxbook")) {
            if ((Save-Shots $export) -ne 0) { $status = 1 }
        }
        Write-Output "Mars hand-off"
        $mars = Join-Path $Out "mars"
        & $Py -m plotweaver scenario-mars --yes --export-dir $mars --project (Join-Path $mars "project")
        if ($LASTEXITCODE -ne 0) { $status = 1 }
        else {
            & $Py -m plotweaver sound add (Join-Path $mars "book.vxbook") -o (Join-Path $mars "book.sound.vxbook")
            if ($LASTEXITCODE -ne 0) { $status = 1 }
        }
    }
}

foreach ($pair in @(
        @("book.vxbook", "vxbook-validate.json"),
        @("book.sound.vxbook", "sound-validate.json")
    )) {
    $book = Join-Path $Out "mars" $pair[0]
    if (Test-Path $book) {
        $code = Invoke-Captured (Join-Path $Out "mars" $pair[1]) "-" @(
            "-m", "plotweaver", "vxbook", "validate", $book, "--json"
        )
        if ($code -ne 0) { $status = 1 }
    }
}

Write-Output "summary"
Write-Summary | Out-Null
if (Get-Command tar -ErrorAction SilentlyContinue) {
    tar -C $Out -czf (Join-Path $Out "vm-test-results.tar.gz") summary.md screenshots 16gb 24gb mars checks mode.txt 2>$null
}
Write-Output "wrote $Out/summary.md"
Write-Result $status
exit $status
