import json
from pathlib import Path
from typing import Dict, List, Optional
from tkinter import messagebox


class CredentialManager:
    """Handles storage and retrieval of SSH server credentials in a plain JSON file."""

    def __init__(self, data_file: str = "servers.json"):
        self.data_file = Path(data_file)
        self.servers: Dict[str, Dict] = {}
        self.load_data()

    def load_data(self):
        """Load server data from the JSON file."""
        if not self.data_file.exists():
            self.servers = {}
            return

        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                # Handle empty file case
                content = f.read()
                if not content:
                    self.servers = {}
                    return
                self.servers = json.loads(content)
        except (json.JSONDecodeError, IOError) as e:
            messagebox.showerror("Error", f"Failed to load server data from {self.data_file}: {e}")
            self.servers = {}

    def save_data(self):
        """Save the current server data to the JSON file."""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.servers, f, indent=4)
        except IOError as e:
            messagebox.showerror("Error", f"Failed to save server data to {self.data_file}: {e}")

    def add_server(self, name: str, host: str, username: str, password: str, port: int = 22):
        """Add or update a server in the store."""
        self.servers[name] = {
            'host': host,
            'username': username,
            'password': password,
            'port': port
        }
        self.save_data()

    def get_server(self, name: str) -> Optional[Dict]:
        """Get server credentials by name."""
        return self.servers.get(name)

    def delete_server(self, name: str):
        """Delete a server from the store."""
        if name in self.servers:
            del self.servers[name]
            self.save_data()

    def list_servers(self) -> List[str]:
        """Get a sorted list of all server names."""
        return sorted(list(self.servers.keys()))

    # ----- Favorite services persistence -----
    def get_services(self, name: str) -> List[str]:
        data = self.servers.get(name) or {}
        svcs = data.get('services')
        if isinstance(svcs, list):
            # keep only strings, unique preserve order
            seen = set()
            out = []
            for s in svcs:
                if isinstance(s, str) and s not in seen:
                    seen.add(s)
                    out.append(s)
            return out
        return []

    def set_services(self, name: str, services: List[str]):
        if name not in self.servers:
            return
        # normalize list
        norm = []
        seen = set()
        for s in services:
            s = str(s).strip()
            if s and s not in seen:
                seen.add(s)
                norm.append(s)
        self.servers[name]['services'] = norm
        self.save_data()
