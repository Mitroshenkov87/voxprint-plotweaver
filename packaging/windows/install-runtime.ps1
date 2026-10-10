# Downloads uv, installs CPython 3.14, and installs this checkout into a venv.
# Shared model files under LOCALAPPDATA\Voxprint\models are not touched.
$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppRoot

$UvDir = Join-Path $env:LOCALAPPDATA "Voxprint\bin"
New-Item -ItemType Directory -Force -Path $UvDir | Out-Null
$Uv = Join-Path $UvDir "uv.exe"
if (-not (Test-Path $Uv)) {
    $Zip = Join-Path $env:TEMP "uv-x86_64-pc-windows-msvc.zip"
    Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $Zip
    Expand-Archive -Path $Zip -DestinationPath $UvDir -Force
}

& $Uv python install 3.14
$Python = Join-Path $AppRoot ".venv\Scripts\python.exe"
& $Uv venv --python 3.14 (Join-Path $AppRoot ".venv")
& $Uv pip install --python $Python -e $AppRoot
if (-not (Test-Path $Python)) {
    throw "Plotweaver venv was not created"
}
