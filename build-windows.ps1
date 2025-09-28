# SSH Server Manager - Windows Build Script
# Builds a single-file portable executable using PyInstaller

Write-Host "Building SSH Server Manager for Windows..." -ForegroundColor Green

# Install dependencies and PyInstaller if not already installed
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install -r requirements.txt
pip install pyinstaller

# Build the executable with necessary hidden imports for cryptography and paramiko
Write-Host "Building executable..." -ForegroundColor Yellow
pyinstaller --onefile --windowed --name="SSHServerManager" `
    --hidden-import=cryptography `
    --hidden-import=paramiko `
    --hidden-import=_cffi_backend `
    --collect-all cryptography `
    --collect-all paramiko `
    main.py

Write-Host "Build complete! Executable created in dist/ directory." -ForegroundColor Green
Write-Host "You can now run dist/SSHServerManager.exe" -ForegroundColor Cyan