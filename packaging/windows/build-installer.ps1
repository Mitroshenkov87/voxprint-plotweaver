# Build the full Windows setup from a staged runtime and Inno Setup.
# Python, dependencies, and llama.cpp b11476 are inside the setup.
# Model weights are not.
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$Root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Root

python -m pip install -q "uv==0.13.0"
$Stage = Join-Path $Root "build\stage"
if (Test-Path $Stage) { Remove-Item -LiteralPath $Stage -Recurse -Force }
python packaging\assemble.py --dest $Stage
$py = Join-Path $Stage ".venv\Scripts\python.exe"
Push-Location $Stage
& $py -c "import PySide6.QtWidgets, plotweaver; from plotweaver.llama_release import find_server; from pathlib import Path; binary = find_server(Path('runtime') / 'llama.cpp-b11476'); assert binary is not None; print(plotweaver.__version__, binary)"
if ($LASTEXITCODE -ne 0) { throw "staged interpreter failed" }
Pop-Location

$Iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $Iscc)) { throw "Inno Setup 6 is not installed" }
& $Iscc "packaging\windows\plotweaver.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC exited $LASTEXITCODE" }

$Output = Join-Path $Root "packaging\windows\Output"
$exe = Get-ChildItem -Path $Output -Filter "*.exe" | Select-Object -First 1
if (-not $exe) { throw "the setup exe was not produced" }
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $exe.FullName).Hash.ToLower()
[System.IO.File]::WriteAllText((Join-Path $Output "SHA256SUMS"), "$hash  $($exe.Name)`n")
Get-ChildItem $Output | Format-Table Name, Length
