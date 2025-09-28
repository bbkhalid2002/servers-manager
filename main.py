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
import posixpath
import stat

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
        self.connected_server_name: Optional[str] = None
        
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
        
        self.server_listbox.bind("<Double-1>", self.browse_server_sftp)
        
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
        
        self.browse_button = ttk.Button(button_frame, text="Browse Files", command=self.browse_server_sftp)
        self.browse_button.pack(side=tk.LEFT, padx=5)
        
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
        self.browse_button.config(state=state)
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
    
    def browse_server_sftp(self, event=None):
        """Open SFTP browser for the selected server."""
        if not self.ssh_connection.is_connected():
            messagebox.showwarning("Not Connected", "Please connect to a server first to browse its files.")
            return

        selection = self.server_listbox.curselection()
        index = None
        if selection:
            index = selection[0]
        elif event is not None and hasattr(event, 'widget') and isinstance(event.widget, tk.Listbox):
            # On double-click, the selection may not yet be updated; derive from mouse position
            idx = event.widget.nearest(event.y)
            if idx is not None and idx >= 0:
                index = idx

        if index is None:
            messagebox.showwarning("No Server Selected", "Please select a server from the list.")
            return
            
        server_name = self.server_listbox.get(index)
        
        # Check if the selected server is the one we are connected to
        if server_name != self.connected_server_name:
             messagebox.showwarning("Wrong Server", "You are connected to a different server. Please select the correct one.")
             return

        SFTPBrowser(self.root, self.ssh_connection.client, server_name)

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
            self.connected_server_name = server_name
            messagebox.showinfo("Connection Successful", message)
        else:
            self.connected_server_name = None
            messagebox.showerror("Connection Failed", message)
    
    def disconnect_from_server(self):
        """Disconnect from current server."""
        if self.ssh_connection.is_connected():
            self.ssh_connection.disconnect()
            self.connected_server_name = None
            self.status_var.set("Disconnected")
            messagebox.showinfo("Disconnected", "Disconnected from server.")
        else:
            messagebox.showinfo("Not Connected", "No active connection to disconnect from.")

class SFTPBrowser(tk.Toplevel):
    """A Toplevel window for browsing a remote server's filesystem using SFTP."""

    def __init__(self, parent, ssh_client: paramiko.SSHClient, server_name: str):
        super().__init__(parent)
        self.title(f"File Browser - {server_name}")
        self.geometry("600x700")
        self.transient(parent)
        self.grab_set()

        self.ssh_client = ssh_client
        self.sftp_client = None
        self.current_path = tk.StringVar()

        self.setup_ui()
        self.open_sftp_session()

    def setup_ui(self):
        """Setup the UI components for the file browser."""
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Path display and Up button
        path_frame = ttk.Frame(main_frame)
        path_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        path_frame.columnconfigure(1, weight=1)

        up_button = ttk.Button(path_frame, text="..", command=self.go_up_directory, width=4)
        up_button.grid(row=0, column=0, sticky=tk.W)

        path_label = ttk.Entry(path_frame, textvariable=self.current_path, state='readonly')
        path_label.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)

        # Treeview for file listing
        tree_frame = ttk.Frame(main_frame)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, columns=("size", "type"), show="tree headings")
        self.tree.heading("size", text="Size")
        self.tree.heading("type", text="Type")
        self.tree.column("size", width=100, anchor='e')
        self.tree.column("type", width=100, anchor='w')

        # Display filename in the tree column (#0)
        self.tree.column("#0", width=350, anchor='w')
        self.tree.heading("#0", text="Name")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<Double-1>", self.on_item_double_click)

        # Status bar
        self.status_var = tk.StringVar(value="Connecting...")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        self.protocol("WM_DELETE_WINDOW", self.close_sftp_session)

    def open_sftp_session(self):
        """Opens an SFTP session and lists the initial directory."""
        try:
            self.sftp_client = self.ssh_client.open_sftp()
            initial_path = self.sftp_client.normalize('.')
            initial_path = posixpath.normpath(initial_path)
            self.list_directory(initial_path)
        except Exception as e:
            self.status_var.set(f"Error: {e}")
            messagebox.showerror("SFTP Error", f"Could not open SFTP session: {e}", parent=self)
            self.destroy()

    def list_directory(self, path: str):
        """Lists the contents of a remote directory in the treeview."""
        path = posixpath.normpath(path) if path else '/'
        self.current_path.set(path)
        self.tree.delete(*self.tree.get_children())

        try:
            items = self.sftp_client.listdir_attr(path)
            self.status_var.set(f"Listing contents of {path}")

            # Separate directories and files for sorting
            dirs = []
            files = []
            for attr in items:
                is_dir = stat.S_ISDIR(attr.st_mode)
                item_type = "Directory" if is_dir else "File"
                item = (attr.filename, attr.st_size, item_type, is_dir)
                if is_dir:
                    dirs.append(item)
                else:
                    files.append(item)

            # Sort alphabetically
            dirs.sort(key=lambda x: x[0].lower())
            files.sort(key=lambda x: x[0].lower())

            for name, size, item_type, is_dir in dirs + files:
                tags = ('directory',) if is_dir else ()
                self.tree.insert("", "end", text=name, values=(size, item_type), tags=tags)

            self.tree.tag_configure('directory', foreground='blue', font=('TkDefaultFont', 9, 'bold'))

        except Exception as e:
            self.status_var.set(f"Error listing directory: {e}")
            messagebox.showerror("Error", f"Could not list directory '{path}':\n{e}", parent=self)

    def on_item_double_click(self, event):
        """Handle double-click on a treeview item."""
        item_id = self.tree.focus()
        if not item_id:
            return

        item = self.tree.item(item_id)
        values = item.get('values') or []
        item_type = values[1] if len(values) > 1 else None

        if item_type == "Directory":
            dir_name = item['text']
            new_path = posixpath.normpath(posixpath.join(self.current_path.get(), dir_name))
            self.list_directory(new_path)

    def go_up_directory(self):
        """Navigate to the parent directory."""
        current = self.current_path.get() or '/'
        norm_current = posixpath.normpath(current)
        if norm_current == '/':
            self.list_directory('/')
            return
        parent_path = posixpath.dirname(norm_current)
        if not parent_path:
            parent_path = '/'
        self.list_directory(parent_path)

    def close_sftp_session(self):
        """Cleanly close the SFTP session and the window."""
        if self.sftp_client:
            try:
                self.sftp_client.close()
            except Exception:
                pass
        self.destroy()

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