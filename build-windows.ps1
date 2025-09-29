<#
 SSH Server Manager - Windows Build Script
 Builds a single-file portable executable using PyInstaller.
 This script uses `python -m pip` and `python -m PyInstaller` so it works even if
 the `pyinstaller` command isn't on PATH.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Building SSH Server Manager for Windows..." -ForegroundColor Green

# Resolve a Python command we can use
$pythonCmd = "python"
if (-not (Get-Command $pythonCmd -ErrorAction SilentlyContinue)) {
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        $pythonCmd = "py"
    } else {
        Write-Error "Python was not found on PATH. Please install Python 3.11+ and retry."
        exit 1
    }
}

# Ensure pip is available and update basic build tooling
Write-Host "Installing/updating Python build tools..." -ForegroundColor Yellow
& $pythonCmd -m pip install --upgrade pip setuptools wheel

# Install project dependencies and PyInstaller
Write-Host "Installing dependencies..." -ForegroundColor Yellow
& $pythonCmd -m pip install -r requirements.txt
& $pythonCmd -m pip install pyinstaller

# Build the executable with necessary hidden imports for cryptography and paramiko
Write-Host "Building executable..." -ForegroundColor Yellow
& $pythonCmd -m PyInstaller --onefile --windowed --name="SSHServerManager" `
    --add-data "server_manager_icons;server_manager_icons" `
    --hidden-import=cryptography `
    --hidden-import=paramiko `
    --hidden-import=_cffi_backend `
    --collect-all cryptography `
    --collect-all paramiko `
    main.py

if (Test-Path "dist/SSHServerManager.exe") {
    Write-Host "Build complete! Executable created in dist/ directory." -ForegroundColor Green
    Write-Host "You can now run dist/SSHServerManager.exe" -ForegroundColor Cyan
} else {
    Write-Error "Build failed. Check the output above for errors."
    exit 1
}