#Requires -Version 5.1
<#
.SYNOPSIS
    Build a standalone Windows release of Piano Waterfall.
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
#>
[CmdletBinding()]
param(
    [switch]$SkipInstall,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if (-not $SkipInstall) {
    Write-Host "==> Installing build dependencies" -ForegroundColor Cyan
    & $python -m pip install --disable-pip-version-check -e ".[dev]"
}

Write-Host "==> Running PyInstaller" -ForegroundColor Cyan
& $python -m PyInstaller --noconfirm --clean "packaging\piano-waterfall.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$exe = Join-Path $root "dist\PianoWaterfall\PianoWaterfall.exe"
if (-not (Test-Path $exe)) { throw "Expected executable was not produced: $exe" }

if (-not $SkipSmokeTest) {
    Write-Host "==> Smoke-testing the frozen app" -ForegroundColor Cyan
    $env:PIANO_WATERFALL_DATA_DIR = Join-Path $root ".devdata\exe-smoke"
    $env:PIANO_WATERFALL_EXE = $exe
    & $python -c "import os, subprocess, sys; sys.exit(subprocess.run([os.environ['PIANO_WATERFALL_EXE'], '--smoke-test'], timeout=90).returncode)"
    if ($LASTEXITCODE -ne 0) { throw "Frozen app exited with code $LASTEXITCODE" }
}

$releaseDir = Join-Path $root "release"
New-Item -ItemType Directory -Force $releaseDir | Out-Null
$zip = Join-Path $releaseDir "PianoWaterfall-windows-x64.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Write-Host "==> Packing $zip" -ForegroundColor Cyan
Compress-Archive -Path (Join-Path $root "dist\PianoWaterfall\*") -DestinationPath $zip

$size = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Done: $zip ($size MB)" -ForegroundColor Green
