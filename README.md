# SSH Server Manager

A secure, cross-platform GUI application for managing SSH server connections with encrypted credential storage. Built with Python and Tkinter, it can be packaged as a portable executable for Windows and macOS.

## Features

- **Secure Credential Storage**: Passwords are encrypted using industry-standard encryption (Fernet/AES)
- **Master Password Protection**: All server data is protected by a master password
- **SSH Connection Management**: Connect to saved servers with one click
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Portable Executables**: Can be built as standalone executables
- **Persistent Storage**: Server credentials are saved locally and restored on app restart

## Security Features

- **Encryption**: Uses `cryptography` library with PBKDF2 key derivation and Fernet encryption
- **Master Password**: All data is encrypted with a user-provided master password
- **Local Storage**: Credentials are stored locally, never transmitted to external servers
- **Secure Connections**: Uses `paramiko` library for robust SSH connections

## Requirements

- Python 3.7 or higher
- Dependencies listed in `requirements.txt`:
  - `cryptography>=3.4.8` - For secure credential encryption
  - `paramiko>=2.8.0` - For SSH connections
  - `pyinstaller>=4.8` - For building executables (optional)

## Running the Application

### Direct Python Execution

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

### First Time Setup

1. Run the application
2. Enter a master password when prompted (this will be used to encrypt your server data)
3. Add your first SSH server using the "Add Server" button
4. Your credentials are automatically encrypted and saved

### Building Portable Executables

#### Windows (PowerShell)

```powershell
# Run the build script
.\build-windows.ps1
```

The executable will be created in the `dist/` directory.

#### macOS (Bash)

```bash
# Make the script executable
chmod +x build-macos.sh

# Run the build script
./build-macos.sh
```

The `.app` bundle will be created in the `dist/` directory.

## Usage

### Adding Servers
1. Click "Add Server"
2. Fill in server details:
   - **Server Name**: A friendly name for identification
   - **Host/IP**: Server hostname or IP address
   - **Username**: SSH username
   - **Password**: SSH password
   - **Port**: SSH port (default: 22)
3. Click "Save"

### Connecting to Servers
1. Select a server from the list
2. Click "Connect"
3. Connection status will be displayed in the status bar

### Managing Servers
- **Edit**: Select a server and click "Edit Server" to modify details
- **Delete**: Select a server and click "Delete Server" to remove it
- **Connect/Disconnect**: Manage SSH connections

## Data Storage

- **File Location**: Credentials are stored in `servers.enc` in the application directory
- **Encryption**: File is encrypted with your master password using PBKDF2 + Fernet encryption
- **Backup**: Consider backing up `servers.enc` (it's useless without your master password)

## Distribution Notes

### Windows
- The generated `.exe` file is portable and doesn't require Python installation
- Windows Defender might flag the executable initially - this is common with PyInstaller builds
- For distribution, consider code signing to avoid security warnings

### macOS
- The generated `.app` bundle works on macOS systems
- For distribution outside the Mac App Store, the app needs to be notarized
- Users might need to right-click and "Open" the first time if the app isn't signed
- Cross-compilation (building macOS executables on Windows/Linux) is not supported

## Security Considerations

### Best Practices
- **Strong Master Password**: Use a unique, strong password for your master password
- **Secure Storage**: Keep the `servers.enc` file secure and backed up
- **SSH Keys**: Consider using SSH keys instead of passwords for better security
- **Regular Updates**: Keep dependencies updated for security patches

### Limitations
- **Master Password**: If you forget your master password, your server data cannot be recovered
- **Local Storage**: Data is stored locally only - no cloud sync
- **SSH Keys**: Currently only supports password authentication (SSH keys planned for future versions)

## Development

### Project Structure

```
├── main.py              # Main application file
├── requirements.txt     # Python dependencies  
├── build-windows.ps1    # Windows build script
├── build-macos.sh       # macOS build script
├── servers.enc          # Encrypted server data (created at runtime)
└── README.md           # This file
```

### Architecture

- **CredentialManager**: Handles encryption/decryption and storage of server credentials
- **SSHConnection**: Manages SSH connections using paramiko
- **ServerManagerGUI**: Main GUI application using Tkinter
- **ServerDialog**: Dialog for adding/editing server information

## Troubleshooting

### Common Issues

1. **"cryptography library not found"**: Install with `pip install cryptography`
2. **"paramiko library not found"**: Install with `pip install paramiko`
3. **Connection timeouts**: Check server address, port, and firewall settings
4. **Authentication failed**: Verify username and password are correct
5. **Forgotten master password**: Unfortunately, data cannot be recovered - delete `servers.enc` to start fresh

### Build Issues

1. **Import errors in executable**: Dependencies should be automatically detected
2. **Missing modules**: The build scripts include necessary hidden imports
3. **Large executable size**: This is normal due to the cryptography library

### Build Requirements

- **Windows**: Requires PowerShell execution policy to allow scripts
- **macOS**: Requires Xcode command line tools for cryptography compilation

## Contributing

Feel free to submit issues and enhancement requests. This is a utility application focused on simplicity and security.

## License

This project is provided as-is for educational and development purposes.