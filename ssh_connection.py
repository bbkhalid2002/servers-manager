from typing import Optional, Tuple
import paramiko


class SSHConnection:
    """Handles SSH connections to remote servers."""

    def __init__(self):
        self.client: Optional[paramiko.SSHClient] = None

    def connect(self, host: str, username: str, password: str, port: int = 22) -> Tuple[bool, str]:
        """Connect to SSH server. Returns (success: bool, message: str)"""
        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=10
            )
            return True, f"Successfully connected to {host}"
        except paramiko.AuthenticationException:
            return False, "Authentication failed: Incorrect username or password."
        except paramiko.SSHException as e:
            return False, f"SSH error: {e}"
        except Exception as e:
            return False, f"Connection failed: {str(e)}"

    def disconnect(self):
        """Disconnect from SSH server."""
        if self.client:
            self.client.close()
            self.client = None

    def is_connected(self) -> bool:
        """Check if currently connected."""
        if self.client and self.client.get_transport():
            return self.client.get_transport().is_active()
        return False
