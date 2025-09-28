#!/bin/bash
# SSH Server Manager - macOS Build Script
# Builds a single-file portable application using PyInstaller

echo "Building SSH Server Manager for macOS..."

# Install dependencies and PyInstaller if not already installed
echo "Installing dependencies..."
pip3 install -r requirements.txt
pip3 install pyinstaller

# Build the application bundle with necessary hidden imports for cryptography and paramiko
echo "Building application bundle..."
pyinstaller --onefile --windowed --name="SSHServerManager" \
    --hidden-import=cryptography \
    --hidden-import=paramiko \
    --hidden-import=_cffi_backend \
    --collect-all cryptography \
    --collect-all paramiko \
    main.py

echo "Build complete! Application created in dist/ directory."
echo "You can now run dist/SSHServerManager.app"