# Windows twin of scripts/vm_test.sh.
# Non-interactive. Exit 0 pass, 1 a check failed, 2 setup, 3 no supported GPU.
# --smoke (-Smoke) is the short pass: install check, doctor, models list,
# one chapter and one scene on the detected tier, then vxbook validate.
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
    & uv pip install --python $created -e "$Root[dev]"
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
        & uv pip install --python $Py -e "$Root[dev]"
        if ($LASTEXITCODE -ne 0) {
            [Console]::Error.WriteLine("--mock needs the dev extra and it could not be installed")
            Write-Result 2
            exit 2
        }
    }
}

$env:PLOTWEAVER_NO_UPDATE_CHECK = "1"
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
if ($Mock) { Set-Content -Path (Join-Path $Out "mode.txt") -Value "1" -Encoding utf8 }
else { Set-Content -Path (Join-Path $Out "mode.txt") -Value "0" -Encoding utf8 }

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
    $name = & $Py -c "from plotweaver.hardware import query_gpu; from plotweaver.registry import detected_tier; info = query_gpu(); raise SystemExit(1) if info is None else print(detected_tier(info.total_gb))"
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
        Set-Content -Path (Join-Path $dir "vram-peak-mib.txt") -Value "n/a" -Encoding utf8
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
        & $Py -m plotweaver doctor > (Join-Path $dir "doctor.txt")
    }
    $env:PLOTWEAVER_METRICS = Join-Path $dir "metrics.jsonl"
    Set-Content -Path $env:PLOTWEAVER_METRICS -Value "" -Encoding utf8
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
    & $Py @runArgs > (Join-Path $dir "run.json") 2> (Join-Path $dir "stderr.log")
    $code = $LASTEXITCODE
    $elapsed = ((Get-Date) - $started).TotalSeconds
    Set-Content -Path (Join-Path $dir "wall-seconds.txt") -Value "$elapsed" -Encoding utf8
    if ($code -ne 0) { return $code }
    & $Py -m plotweaver vxbook validate (Join-Path $dir "project\export\book.vxbook") --json > (Join-Path $dir "vxbook-validate.json")
    return $LASTEXITCODE
}

function Save-Shots([string]$ExportDir = "") {
    $env:PLOTWEAVER_VM_SHOTS = Join-Path $Out "screenshots"
    if ($ExportDir) { $env:PLOTWEAVER_VM_EXPORT = $ExportDir } else { Remove-Item Env:PLOTWEAVER_VM_EXPORT -ErrorAction SilentlyContinue }
    & $Py -c "import os; from pathlib import Path; from plotweaver.ui.vm_shots import save_vm_shots; raw = os.environ.get('PLOTWEAVER_VM_EXPORT', ''); export = Path(raw) if raw else None; save_vm_shots(Path(os.environ['PLOTWEAVER_VM_SHOTS']), export_dir=export)"
    return $LASTEXITCODE
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
    if ($Mock) { & $Py -m plotweaver doctor --mock > (Join-Path $Out "doctor.txt") }
    else { & $Py -m plotweaver doctor > (Join-Path $Out "doctor.txt") }
    if ($LASTEXITCODE -ne 0) { $status = 1 }
    Write-Output "smoke models list"
    & $Py -m plotweaver models list --json > (Join-Path $Out "checks\models.json")
    if ($LASTEXITCODE -ne 0) { $status = 1 }
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
& $Py -m pytest tests/test_models.py tests/test_cli_machine.py tests/test_vxbook.py tests/test_ui.py::test_vm_shots -q > (Join-Path $Out "checks\pytest.log") 2>&1
if ($LASTEXITCODE -ne 0) { $status = 1 }

Write-Output "CLI smoke"
& $Py -m plotweaver run --project (Join-Path $Out "checks\dry-project") --brief (Join-Path $Root "scripts\vm-brief.md") --chapters 2 --scenes-per-chapter 1 --dark-themes --yes --fb2 --sound --json --dry-run --mock > (Join-Path $Out "checks\run-dry.json")
if ($LASTEXITCODE -ne 0) { $status = 1 }
& $Py -m plotweaver vxbook validate (Join-Path $Root "tests\fixtures\vxbook\manifest.json") --dry-run --json > (Join-Path $Out "checks\vxbook-dry.json")
if ($LASTEXITCODE -ne 0) { $status = 1 }
$env:VM_ROOT = $Root
$env:VM_OUT = Join-Path $Out "checks"
& $Py -c "import json, os; from pathlib import Path; root = Path(os.environ['VM_ROOT']); out = Path(os.environ['VM_OUT']); (out / 'models.toml').write_text((root / 'bakeoff' / 'models.toml').read_text(encoding='utf-8'), encoding='utf-8'); (out / 'forge.json').write_text(json.dumps({'models': [{'id': 'gemma-4-31b-abliterated-iq3-xxs', 'revision': 'pending', 'sha256': 'ab' * 32, 'size': 1}]}), encoding='utf-8')"
& $Py -m plotweaver models import-forge-manifest (Join-Path $Out "checks\forge.json") --registry (Join-Path $Out "checks\models.toml") --dry-run --json > (Join-Path $Out "checks\import-dry.json")
if ($LASTEXITCODE -ne 0) { $status = 1 }

Write-Output "screenshots"
if ((Save-Shots) -ne 0) { $status = 1 }

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
    & $Py -m plotweaver doctor > (Join-Path $Out "doctor.txt")
    if ($LASTEXITCODE -ne 0) { $status = 1 }
    if ($status -eq 0) {
        Write-Output "model download"
        & $Py -c "from plotweaver.hardware import require_supported_gpu; from plotweaver.install import ensure_default_install, ensure_uncensored_models; gpu = require_supported_gpu(); print(f'{gpu.name}: {gpu.free_gb:.1f} of {gpu.total_gb:.1f} GB free'); print('stock', ensure_default_install(free_gb=gpu.free_gb, total_gb=gpu.total_gb)); print('forge', ensure_uncensored_models(total_vram_gb=gpu.total_gb, free_gb=gpu.free_gb))" > (Join-Path $Out "checks\download.txt")
        if ($LASTEXITCODE -ne 0) { $status = 1 }
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
        & $Py -m plotweaver vxbook validate $book --json > (Join-Path $Out "mars" $pair[1])
        if ($LASTEXITCODE -ne 0) { $status = 1 }
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
