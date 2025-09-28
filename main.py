#!/usr/bin/env python3
"""
Secure SSH Server Manager
A cross-platform GUI application for managing SSH server connections.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import json
import sys
import threading
from pathlib import Path
from typing import Dict, List, Optional

try:
    import paramiko
except ImportError:
    messagebox.showerror("Dependency Error", "Error: paramiko library not found. Please install it by running: pip install paramiko")
    sys.exit(1)

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

class SSHConnection:
    """Handles SSH connections to remote servers."""
    
    def __init__(self):
        self.client = None
    
    def connect(self, host: str, username: str, password: str, port: int = 22) -> tuple:
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

class ServerManagerGUI:
    """Main GUI application for SSH server management."""
    
    def __init__(self, root):
        self.root = root
        self.root.title("SSH Server Manager")
        self.root.geometry("700x500")
        
        self.credential_manager = CredentialManager()
        self.ssh_connection = SSHConnection()
        
        self.setup_ui()
        self.refresh_server_list()
    
    def setup_ui(self):
        """Setup the main user interface."""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        title_label = ttk.Label(main_frame, text="SSH Server Manager", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, columnspan=2, pady=(0, 20))
        
        list_frame = ttk.LabelFrame(main_frame, text="Saved Servers", padding="5")
        list_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        self.server_listbox = tk.Listbox(list_frame)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.server_listbox.yview)
        self.server_listbox.config(yscrollcommand=scrollbar.set)
        
        self.server_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=(10, 10), sticky=tk.W)
        
        self.add_button = ttk.Button(button_frame, text="Add Server", command=self.add_server_dialog)
        self.add_button.pack(side=tk.LEFT, padx=(0, 5))
        self.edit_button = ttk.Button(button_frame, text="Edit Server", command=self.edit_server_dialog)
        self.edit_button.pack(side=tk.LEFT, padx=5)
        self.delete_button = ttk.Button(button_frame, text="Delete Server", command=self.delete_server)
        self.delete_button.pack(side=tk.LEFT, padx=5)
        self.connect_button = ttk.Button(button_frame, text="Connect", command=self.connect_to_server)
        self.connect_button.pack(side=tk.LEFT, padx=5)
        self.disconnect_button = ttk.Button(button_frame, text="Disconnect", command=self.disconnect_from_server)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)
        
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E))

    def set_controls_enabled(self, enabled: bool):
        """Enable or disable interactive controls."""
        state = 'normal' if enabled else 'disabled'
        self.add_button.config(state=state)
        self.edit_button.config(state=state)
        self.delete_button.config(state=state)
        self.connect_button.config(state=state)
        self.disconnect_button.config(state=state)
        self.server_listbox.config(state=state)

    def refresh_server_list(self):
        """Refresh the server list display."""
        self.server_listbox.delete(0, tk.END)
        for server_name in self.credential_manager.list_servers():
            self.server_listbox.insert(tk.END, server_name)
    
    def add_server_dialog(self):
        """Show dialog to add a new server."""
        dialog = ServerDialog(self.root, "Add Server")
        if dialog.result:
            name, host, username, password, port = dialog.result
            self.credential_manager.add_server(name, host, username, password, port)
            self.refresh_server_list()
            self.status_var.set(f"Added server: {name}")
    
    def edit_server_dialog(self):
        """Show dialog to edit selected server."""
        selection = self.server_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a server to edit")
            return
        
        server_name = self.server_listbox.get(selection[0])
        server_data = self.credential_manager.get_server(server_name)
        
        dialog = ServerDialog(self.root, "Edit Server", server_data, server_name)
        if dialog.result:
            new_name, host, username, password, port = dialog.result
            # Add/update with new name
            self.credential_manager.add_server(new_name, host, username, password, port)
            
            # Delete old entry if name changed
            if new_name != server_name:
                self.credential_manager.delete_server(server_name)

            self.refresh_server_list()
            self.status_var.set(f"Updated server: {new_name}")
    
    def delete_server(self):
        """Delete selected server."""
        selection = self.server_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a server to delete")
            return
        
        server_name = self.server_listbox.get(selection[0])
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete server '{server_name}'?"):
            self.credential_manager.delete_server(server_name)
            self.refresh_server_list()
            self.status_var.set(f"Deleted server: {server_name}")
    
    def connect_to_server(self):
        """Connect to selected server."""
        if self.ssh_connection.is_connected():
            messagebox.showwarning("Already Connected", "Please disconnect before starting a new connection.")
            return

        selection = self.server_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a server to connect to")
            return
        
        server_name = self.server_listbox.get(selection[0])
        server_data = self.credential_manager.get_server(server_name)
        
        self.status_var.set(f"Connecting to {server_name}...")
        self.set_controls_enabled(False)
        
        def connect_thread():
            success, message = self.ssh_connection.connect(
                server_data['host'],
                server_data['username'], 
                server_data['password'],
                server_data['port']
            )
            self.root.after(0, lambda: self.connection_result(success, message, server_name))
        
        threading.Thread(target=connect_thread, daemon=True).start()
    
    def connection_result(self, success: bool, message: str, server_name: str):
        """Handle connection result in main thread."""
        self.set_controls_enabled(True)
        self.status_var.set(message)
        if success:
            messagebox.showinfo("Connection Successful", message)
        else:
            messagebox.showerror("Connection Failed", message)
    
    def disconnect_from_server(self):
        """Disconnect from current server."""
        if self.ssh_connection.is_connected():
            self.ssh_connection.disconnect()
            self.status_var.set("Disconnected")
            messagebox.showinfo("Disconnected", "Disconnected from server.")
        else:
            messagebox.showinfo("Not Connected", "No active connection to disconnect from.")

class ServerDialog:
    """Dialog for adding/editing server information."""
    
    def __init__(self, parent, title, server_data=None, server_name=""):
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x280")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.dialog.geometry(f"+{parent.winfo_rootx()+50}+{parent.winfo_rooty()+50}")
        
        self.setup_dialog_ui(server_data, server_name)
        
        self.dialog.wait_window()
    
    def setup_dialog_ui(self, server_data, server_name):
        """Setup dialog UI elements."""
        main_frame = ttk.Frame(self.dialog, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        form_frame = ttk.Frame(main_frame)
        form_frame.pack(fill=tk.X, expand=True)
        form_frame.columnconfigure(1, weight=1)

        ttk.Label(form_frame, text="Server Name:").grid(row=0, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.name_var = tk.StringVar(value=server_name)
        ttk.Entry(form_frame, textvariable=self.name_var).grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(form_frame, text="Host/IP:").grid(row=1, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.host_var = tk.StringVar(value=server_data['host'] if server_data else '')
        ttk.Entry(form_frame, textvariable=self.host_var).grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(form_frame, text="Username:").grid(row=2, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.username_var = tk.StringVar(value=server_data['username'] if server_data else '')
        ttk.Entry(form_frame, textvariable=self.username_var).grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(form_frame, text="Password:").grid(row=3, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.password_var = tk.StringVar(value=server_data['password'] if server_data else '')
        ttk.Entry(form_frame, textvariable=self.password_var, show='*').grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        
        ttk.Label(form_frame, text="Port:").grid(row=4, column=0, sticky=tk.W, pady=5, padx=(0, 10))
        self.port_var = tk.StringVar(value=str(server_data['port']) if server_data else '22')
        ttk.Entry(form_frame, textvariable=self.port_var).grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(pady=(20, 0))
        
        ttk.Button(button_frame, text="Save", command=self.save_server).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.LEFT, padx=5)
    
    def save_server(self):
        """Validate and save server information."""
        name = self.name_var.get().strip()
        host = self.host_var.get().strip()
        username = self.username_var.get().strip()
        password = self.password_var.get()
        port_str = self.port_var.get().strip()
        
        if not all([name, host, username, password, port_str]):
            messagebox.showerror("Error", "All fields are required.", parent=self.dialog)
            return
        
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                raise ValueError()
        except ValueError:
            messagebox.showerror("Error", "Port must be a number between 1 and 65535.", parent=self.dialog)
            return
        
        self.result = (name, host, username, password, port)
        self.dialog.destroy()
    
    def cancel(self):
        """Cancel dialog."""
        self.dialog.destroy()

def main():
    """Main application entry point."""
    root = tk.Tk()
    
    def on_closing():
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    try:
        ServerManagerGUI(root)
        root.mainloop()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Fatal Error", f"A fatal application error occurred: {e}\n\nThe application will now close.")
        sys.exit(1)

if __name__ == "__main__":
    main()