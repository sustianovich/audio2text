$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment' }
}
& $python -m pip install --quiet -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
# Ensure this Windows Python install can locate Tcl/Tk during analysis.
$base = & $python -c "import sys; print(sys.base_prefix)"
$env:TCL_LIBRARY = Join-Path $base 'tcl\tcl8.6'
$env:TK_LIBRARY = Join-Path $base 'tcl\tk8.6'
& $python -m PyInstaller --noconfirm --log-level WARN Audio2Text.spec
if ($LASTEXITCODE -ne 0) { throw 'Executable build failed' }
$candidates = @(
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
)
$compiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $compiler) { throw 'Install Inno Setup 6: winget install --id JRSoftware.InnoSetup --exact' }
$version = & $python -c "from importlib.metadata import version; print(version('audio2text'))"
if ($LASTEXITCODE -ne 0) { throw 'Could not read application version' }
& $compiler /Q "/DAppVersion=$version" installer.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
Write-Host "Installer: release\Audio2Text-Setup-$version.exe"
