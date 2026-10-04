param(
    [string]$Python = "python",
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if ($Clean) {
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

& $Python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller is not installed. Run: $Python -m pip install pyinstaller"
}

& $Python -m PyInstaller --noconfirm --clean DigitalSocietySandbox.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
& $Python -m PyInstaller --noconfirm --clean DigitalSocietySandboxCLI.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller CLI build failed" }
Write-Host "Built dist\DigitalSocietySandbox.exe"
Write-Host "Built dist\DigitalSocietySandboxCLI.exe"
