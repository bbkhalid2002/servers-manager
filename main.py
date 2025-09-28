#!/usr/bin/env python3
"""
Secure SSH Server Manager
A cross-platform GUI application for managing SSH server connections.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
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

# ---------- UI helpers ----------
def center_window(win: tk.Toplevel | tk.Tk, relative_to: Optional[tk.Misc] = None):
    """Center a window relative to a parent widget or the screen.

    - win: the Toplevel/Tk window to center
    - relative_to: the widget to center relative to (defaults to win.master or screen)
    """
    try:
        win.update_idletasks()
        # Determine parent to center against
        parent = relative_to
        if parent is None:
            try:
                parent = win.master if getattr(win, 'master', None) else win.winfo_toplevel()
            except Exception:
                parent = None

        # Target window size
        w = win.winfo_width()
        h = win.winfo_height()
        if w <= 1 or h <= 1:
            w = win.winfo_reqwidth()
            h = win.winfo_reqheight()

        if parent is not None:
            try:
                parent.update_idletasks()
            except Exception:
                pass
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width() or parent.winfo_reqwidth()
            ph = parent.winfo_height() or parent.winfo_reqheight()
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
        else:
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = max(0, (sw - w) // 2)
            y = max(0, (sh - h) // 2)

        # Clamp to screen bounds
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h))
        win.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        # Best-effort; ignore centering failures
        pass

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
        # Geometry is set in main() to center at 50% of screen
        
        self.credential_manager = CredentialManager()
        self.ssh_connection = SSHConnection()
        self.connected_server_name: Optional[str] = None
        
        self.setup_ui()
        self.refresh_server_list()
    
    def setup_ui(self):
        """Setup the main user interface."""
        # Menu bar
        menubar = tk.Menu(self.root)
        servers_menu = tk.Menu(menubar, tearoff=0)
        servers_menu.add_command(label="Add", command=self.add_server_dialog)
        servers_menu.add_command(label="Edit", command=self.edit_server_dialog)
        servers_menu.add_command(label="Delete", command=self.delete_server)
        servers_menu.add_separator()
        servers_menu.add_command(label="Connect", command=self.connect_to_server)
        servers_menu.add_command(label="Disconnect", command=self.disconnect_from_server)
        menubar.add_cascade(label="Servers", menu=servers_menu)
        self.root.config(menu=menubar)

        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        
        title_label = ttk.Label(main_frame, text="SSH Server Manager", font=("Arial", 16, "bold"))
        title_label.grid(row=0, column=0, sticky=(tk.W), pady=(0, 10))

        # Paned window split: left servers list, right file browser
        paned = ttk.Panedwindow(main_frame, orient=tk.HORIZONTAL)
        paned.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        self.paned = paned

        # Left panel: servers
        left_panel = ttk.Frame(paned, padding="5")
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=1)

        ttk.Label(left_panel, text="Servers", font=("Arial", 11, "bold")).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))

        servers_frame = ttk.Frame(left_panel)
        servers_frame.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        servers_frame.columnconfigure(0, weight=1)
        servers_frame.rowconfigure(0, weight=1)

        self.server_listbox = tk.Listbox(servers_frame)
        scrollbar = ttk.Scrollbar(servers_frame, orient="vertical", command=self.server_listbox.yview)
        self.server_listbox.config(yscrollcommand=scrollbar.set)
        self.server_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Double-click action on server item
        self.server_listbox.bind("<Double-1>", self.on_server_double_click)

        # Right panel: notebook with tabs (File Management selected, Server empty)
        right_panel = ttk.Frame(paned, padding="5")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        # Style: add padding to tab labels and margins, and spacing between tabs and content
        try:
            style = ttk.Style(self.root)
            style.configure('Custom.TNotebook.Tab', padding=(12, 6))  # tab label padding (x, y)
            style.configure('Custom.TNotebook', tabmargins=(6, 6, 6, 0))  # space around tab area
        except Exception:
            pass

        notebook = ttk.Notebook(right_panel, style='Custom.TNotebook')
        notebook.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # File Management tab
        file_mgmt_tab = ttk.Frame(notebook, padding=(10, 12, 10, 10))  # add content padding (l, t, r, b)
        file_mgmt_tab.columnconfigure(0, weight=1)
        file_mgmt_tab.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(file_mgmt_tab)
        toolbar.grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        self.upload_button = ttk.Button(toolbar, text="Upload", command=self.on_upload_click, state='disabled')
        self.upload_button.pack(side=tk.LEFT)
        self.download_button = ttk.Button(toolbar, text="Download", command=self.on_download_click, state='disabled')
        self.download_button.pack(side=tk.LEFT, padx=(5, 0))

        self.file_browser = RemoteFileBrowserFrame(file_mgmt_tab)
        self.file_browser.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # Server tab - manage favorite services
        server_tab = ttk.Frame(notebook, padding=(10, 12, 10, 10))
        server_tab.columnconfigure(0, weight=1)
        server_tab.rowconfigure(1, weight=1)

        server_toolbar = ttk.Frame(server_tab)
        server_toolbar.grid(row=0, column=0, sticky=tk.W, pady=(0, 8))
        ttk.Label(server_toolbar, text="Service:").pack(side=tk.LEFT)
        self.service_name_var = tk.StringVar()
        self.service_entry = ttk.Entry(server_toolbar, textvariable=self.service_name_var, width=30)
        self.service_entry.pack(side=tk.LEFT, padx=(6, 6))
        # Update Add button state as the user types and allow Enter key to add
        try:
            self.service_name_var.trace_add('write', lambda *args: self._update_service_actions_state())
        except Exception:
            # Fallback for very old Tk versions
            try:
                self.service_name_var.trace('w', lambda *args: self._update_service_actions_state())
            except Exception:
                pass
        self.service_entry.bind('<Return>', lambda e: self._add_service())
        self.add_service_btn = ttk.Button(server_toolbar, text="Add", command=self._add_service, state='disabled')
        self.add_service_btn.pack(side=tk.LEFT)
        self.remove_service_btn = ttk.Button(server_toolbar, text="Remove", command=self._remove_selected_service, state='disabled')
        self.remove_service_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Services list (Treeview with Service and Status columns)
        svc_frame = ttk.Frame(server_tab)
        svc_frame.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        svc_frame.columnconfigure(0, weight=1)
        svc_frame.rowconfigure(0, weight=1)
        self.services_tree = ttk.Treeview(svc_frame, columns=("service", "status"), show="headings", selectmode='browse')
        self.services_tree.heading("service", text="Service")
        self.services_tree.heading("status", text="Status")
        self.services_tree.column("service", width=260, anchor='w')
        self.services_tree.column("status", width=120, anchor='w')
        svc_scroll = ttk.Scrollbar(svc_frame, orient='vertical', command=self.services_tree.yview)
        self.services_tree.configure(yscrollcommand=svc_scroll.set)
        self.services_tree.grid(row=0, column=0, sticky='nsew')
        svc_scroll.grid(row=0, column=1, sticky='ns')
        self.services_tree.bind('<<TreeviewSelect>>', lambda e: self._update_service_actions_state())
        # Context menu for services (Start/Stop/Status)
        self._services_menu = tk.Menu(server_tab, tearoff=0)
        self._services_menu.add_command(label='Start', command=lambda: self._svc_action('start'))
        self._services_menu.add_command(label='Stop', command=lambda: self._svc_action('stop'))
        self._services_menu.add_command(label='Status', command=lambda: self._svc_action('status'))
        def _on_services_right_click(event):
            row_id = self.services_tree.identify_row(event.y)
            if row_id:
                self.services_tree.selection_set(row_id)
                self.services_tree.focus(row_id)
                # Enable/disable actions based on connection state and selection
                enabled = self.ssh_connection.is_connected()
                state = 'normal' if enabled else 'disabled'
                try:
                    self._services_menu.entryconfigure(0, state=state)
                    self._services_menu.entryconfigure(1, state=state)
                    self._services_menu.entryconfigure(2, state=state)
                except Exception:
                    pass
                try:
                    self._services_menu.tk_popup(event.x_root, event.y_root)
                finally:
                    self._services_menu.grab_release()
        self.services_tree.bind('<Button-3>', _on_services_right_click)

        # Action buttons
        actions = ttk.Frame(server_tab)
        actions.grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        self.svc_start_btn = ttk.Button(actions, text='Start', command=lambda: self._svc_action('start'), state='disabled')
        self.svc_stop_btn = ttk.Button(actions, text='Stop', command=lambda: self._svc_action('stop'), state='disabled')
        self.svc_status_btn = ttk.Button(actions, text='Status', command=lambda: self._svc_action('status'), state='disabled')
        for b in (self.svc_start_btn, self.svc_stop_btn, self.svc_status_btn):
            b.pack(side=tk.LEFT, padx=(0, 6))

        notebook.add(file_mgmt_tab, text="File Management")
        notebook.add(server_tab, text="Services")
        notebook.select(file_mgmt_tab)

        paned.add(left_panel, weight=1)
        paned.add(right_panel, weight=2)

    # Status bar at bottom
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(8, 0))

        # Set default left pane width to 25% of screen (with clamping), without locking resizing
        try:
            self.root.after(150, self._set_initial_sash)
        except Exception:
            pass

    def _set_initial_sash(self):
        try:
            self.root.update_idletasks()
            pw = self.paned.winfo_width()
            # If paned width isn't laid out yet, retry shortly
            if pw <= 1:
                self.root.after(150, self._set_initial_sash)
                return
            desired_left = int(pw * 0.25)
            # Keep both panes visible
            min_side = 150
            # Clamp desired position inside [min_side, pw - min_side]
            max_left = max(min_side, pw - min_side)
            pos = max(min_side, min(desired_left, max_left))
            # Apply position
            try:
                self.paned.sashpos(0, pos)
            except Exception:
                # Retry once after a brief delay if size isn't ready yet
                self.root.after(150, lambda: self._safe_set_sash(pos))
        except Exception:
            pass

    def _safe_set_sash(self, pos: int):
        try:
            self.paned.sashpos(0, pos)
        except Exception:
            pass

    def set_controls_enabled(self, enabled: bool):
        """Enable or disable interactive controls."""
        state = 'normal' if enabled else 'disabled'
        # top menu remains active; only listbox gets toggled here
        self.server_listbox.config(state=state)
        # Upload button follows connection state elsewhere; don't toggle here

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
    
    def on_server_double_click(self, event):
        # Determine clicked index reliably
        idx = event.widget.nearest(event.y)
        if idx is None or idx < 0:
            return
        self.server_listbox.selection_clear(0, tk.END)
        self.server_listbox.selection_set(idx)
        self.server_listbox.activate(idx)

        server_name = self.server_listbox.get(idx)
        if not self.ssh_connection.is_connected() or self.connected_server_name != server_name:
            self.connect_to_server_by_name(server_name)
        else:
            # Already connected to this server, refresh file browser
            self.file_browser.attach_client(self.ssh_connection.client)

    def connect_to_server(self):
        """Connect to the currently selected server from the listbox."""
        selection = self.server_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a server to connect to")
            return
        server_name = self.server_listbox.get(selection[0])
        self.connect_to_server_by_name(server_name)

    def connect_to_server_by_name(self, server_name: str):
        """Connect to the server by its name."""
        if self.ssh_connection.is_connected():
            messagebox.showwarning("Already Connected", "Please disconnect before starting a new connection.")
            return
        
        server_data = self.credential_manager.get_server(server_name)
        if not server_data:
            messagebox.showerror("Error", f"Server data not found for '{server_name}'")
            return
        
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
            # Attach/reload the file browser on successful connection
            self.file_browser.attach_client(self.ssh_connection.client)
            # Enable upload when connected
            self.upload_button.config(state='normal')
            self.download_button.config(state='normal')
            # Load services for this server and enable UI
            self._load_services_for_connected()
        else:
            self.connected_server_name = None
            self.file_browser.attach_client(None)
            self.upload_button.config(state='disabled')
            self.download_button.config(state='disabled')
            messagebox.showerror("Connection Failed", message)

    def disconnect_from_server(self):
        """Disconnect from current server."""
        if self.ssh_connection.is_connected():
            self.ssh_connection.disconnect()
            self.connected_server_name = None
            self.file_browser.attach_client(None)
            self.upload_button.config(state='disabled')
            self.download_button.config(state='disabled')
            # Clear/disable services UI
            try:
                self.services_tree.delete(*self.services_tree.get_children())
                self._set_services_ui_enabled(False)
            except Exception:
                pass
            self.status_var.set("Disconnected")
            messagebox.showinfo("Disconnected", "Disconnected from server.")
        else:
            messagebox.showinfo("Not Connected", "No active connection to disconnect from.")

    def on_upload_click(self):
        """Handle click on Upload button to upload a file to current/selected remote directory."""
        self.file_browser.prompt_and_upload()

    def on_download_click(self):
        """Handle click on Download button to download selected file from remote to local."""
        self.file_browser.prompt_and_download()

    # ----- Server tab: favorite services management -----
    def _load_services_for_connected(self):
        # Load services list when connected server changes
        # reset tree and populate raw services (status refreshed asynchronously)
        try:
            self.services_tree.delete(*self.services_tree.get_children())
        except Exception:
            pass
        if not self.connected_server_name:
            self._set_services_ui_enabled(False)
            return
        svcs = self.credential_manager.get_services(self.connected_server_name)
        for s in svcs:
            self.services_tree.insert('', 'end', values=(s, ''))
        self._set_services_ui_enabled(self.ssh_connection.is_connected())
        self._update_service_actions_state()
        # Refresh statuses to annotate items
        self._refresh_services_status_async()

    def _set_services_ui_enabled(self, enabled: bool):
        state = 'normal' if enabled else 'disabled'
        # Buttons and entry
        for w in (self.add_service_btn, self.remove_service_btn, self.svc_start_btn,
                   self.svc_stop_btn, self.svc_status_btn,
                   self.service_entry):
            try:
                w.config(state=state)
            except Exception:
                pass
        # Treeview selection mode behaves as enable/disable
        try:
            self.services_tree.configure(selectmode='browse' if enabled else 'none')
        except Exception:
            pass
        # After generic toggle, refine action buttons based on selection
        self._update_service_actions_state()

    def _update_service_actions_state(self):
        enabled = self.ssh_connection.is_connected()
        sel = self.services_tree.selection()
        is_sel = bool(sel)
        for b in (self.remove_service_btn, self.svc_start_btn, self.svc_stop_btn, self.svc_status_btn):
            b.config(state='normal' if (enabled and is_sel) else 'disabled')
        # Add button enabled if entry has text and connected
        name = (self.service_name_var.get() or '').strip()
        self.add_service_btn.config(state='normal' if (enabled and name) else 'disabled')

    def _add_service(self):
        name = (self.service_name_var.get() or '').strip()
        if not name:
            return
        # insert if not exist
        # existing services from tree
        existing = []
        try:
            for iid in self.services_tree.get_children():
                vals = self.services_tree.item(iid).get('values') or []
                if vals:
                    existing.append(str(vals[0]))
        except Exception:
            pass
        if name in existing:
            messagebox.showinfo('Service Exists', f"'{name}' is already in favorites.")
            return
        self.services_tree.insert('', 'end', values=(name, ''))
        self.service_name_var.set('')
        self._persist_services()
        self._refresh_services_status_async()
        self._update_service_actions_state()

    def _remove_selected_service(self):
        sel = self.services_tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self.services_tree.item(iid).get('values') or []
        name = vals[0] if vals else ''
        if not messagebox.askyesno('Remove Service', f"Remove '{name}' from favorites?"):
            return
        try:
            self.services_tree.delete(iid)
        except Exception:
            pass
        self._persist_services()
        self._refresh_services_status_async()
        self._update_service_actions_state()

    def _persist_services(self):
        if not self.connected_server_name:
            return
        # Collect raw service names from tree
        raw = []
        try:
            for iid in self.services_tree.get_children():
                vals = self.services_tree.item(iid).get('values') or []
                if vals:
                    name = str(vals[0]).strip()
                    if name:
                        raw.append(name)
        except Exception:
            pass
        self.credential_manager.set_services(self.connected_server_name, raw)

    def _svc_action(self, action: str):
        if not self.ssh_connection.is_connected():
            messagebox.showwarning('Not Connected', 'Connect to a server first.')
            return
        sel = self.services_tree.selection()
        if not sel:
            return
        vals = self.services_tree.item(sel[0]).get('values') or []
        service = vals[0] if vals else ''
        # Map action to command
        cmd = None
        if action in ('start', 'stop', 'status'):
            # Use sudo -n (no prompt) and capture accordingly; status shouldn't require sudo
            if action == 'status':
                cmd = f"systemctl status --no-pager {service}"
            else:
                cmd = f"sudo -n systemctl {action} {service} || systemctl {action} {service}"
        if not cmd:
            return
        if action in ('start', 'stop'):
            # Run silently and refresh status
            try:
                self.ssh_connection.client.exec_command(cmd)
            except Exception as e:
                messagebox.showerror('SSH Error', f"Failed to execute command:\n{e}")
                return
            # give systemd a moment and refresh
            self.root.after(500, self._refresh_services_status_async)
        elif action == 'status':
            # status: show popup
            self._run_remote_cmd(cmd, title=f"systemctl {action} {service}")

    def _run_remote_cmd(self, cmd: str, title: str = 'Command Output'):
        try:
            stdin, stdout, stderr = self.ssh_connection.client.exec_command(cmd)
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
        except Exception as e:
            messagebox.showerror('SSH Error', f"Failed to execute command:\n{e}")
            return
        # Show output in a simple dialog
        dlg = tk.Toplevel(self.root)
        dlg.title(title)
        dlg.transient(self.root)
        dlg.grab_set()
        frm = ttk.Frame(dlg, padding=10)
        frm.grid(row=0, column=0, sticky='nsew')
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)
        txt = tk.Text(frm, wrap='word', height=30, width=100)
        scr = ttk.Scrollbar(frm, orient='vertical', command=txt.yview)
        txt.configure(yscrollcommand=scr.set)
        txt.grid(row=0, column=0, sticky='nsew')
        scr.grid(row=0, column=1, sticky='ns')
        txt.insert('1.0', out if out.strip() else err)
        txt.config(state='disabled')
        ttk.Button(frm, text='Close', command=dlg.destroy).grid(row=1, column=0, pady=(8,0), sticky='e')
        try:
            center_window(dlg, self.root)
        except Exception:
            pass

    # ----- Status refresh helpers -----
    def _refresh_services_status_async(self):
        if not self.ssh_connection.is_connected():
            return
        # Run in background thread to avoid blocking UI
        def worker():
            try:
                services = self.credential_manager.get_services(self.connected_server_name or '')
                statuses = []
                for s in services:
                    try:
                        cmd = f"systemctl is-active {s} || true"
                        stdin, stdout, stderr = self.ssh_connection.client.exec_command(cmd)
                        out = stdout.read().decode('utf-8', errors='ignore').strip()
                        status = out if out else 'unknown'
                    except Exception:
                        status = 'unknown'
                    statuses.append((s, status))
            except Exception:
                statuses = []
            # Update UI on main thread
            def update_ui():
                try:
                    # Keep current selection by service name if possible
                    prev_sel = None
                    try:
                        sel = self.services_tree.selection()
                        if sel:
                            vals = self.services_tree.item(sel[0]).get('values') or []
                            prev_sel = vals[0] if vals else None
                    except Exception:
                        prev_sel = None
                    self.services_tree.delete(*self.services_tree.get_children())
                    selected_iid = None
                    for name, st in statuses:
                        iid = self.services_tree.insert('', 'end', values=(name, st))
                        if prev_sel and name == prev_sel:
                            selected_iid = iid
                    if selected_iid:
                        self.services_tree.selection_set(selected_iid)
                        self.services_tree.focus(selected_iid)
                except Exception:
                    pass
            try:
                self.root.after(0, update_ui)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

class RemoteFileBrowserFrame(ttk.Frame):
    """Embeddable SFTP browser frame for the main window right pane."""

    def __init__(self, parent):
        super().__init__(parent)
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.sftp_client = None
        self.current_path = tk.StringVar(value="Not connected")
        # Editor state
        self.open_file_path: Optional[str] = None
        self._editor_dirty: bool = False

        self._build_ui()

    def _build_ui(self):
        self.columnconfigure(0, weight=1)
        # Give both the tree (row 1) and editor (row 3) flexible space
        self.rowconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)

        path_frame = ttk.Frame(self)
        path_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        path_frame.columnconfigure(1, weight=1)

        self.up_button = ttk.Button(path_frame, text="..", command=self.go_up_directory, width=4)
        self.up_button.grid(row=0, column=0, sticky=tk.W)

        self.path_entry = ttk.Entry(path_frame, textvariable=self.current_path, state='readonly')
        self.path_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5)

        tree_frame = ttk.Frame(self)
        tree_frame.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(5, 0))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        # Columns: keep size and type first to preserve existing logic, then owner/group/perms
        self.tree = ttk.Treeview(tree_frame, columns=("size", "type", "owner", "group", "perms"), show="tree headings")
        self.tree.heading("size", text="Size")
        self.tree.heading("type", text="Type")
        self.tree.heading("owner", text="Owner")
        self.tree.heading("group", text="Group")
        self.tree.heading("perms", text="Permissions")
        self.tree.column("size", width=90, anchor='e')
        self.tree.column("type", width=80, anchor='w')
        self.tree.column("owner", width=120, anchor='w')
        self.tree.column("group", width=120, anchor='w')
        self.tree.column("perms", width=110, anchor='w')
        self.tree.column("#0", width=300, anchor='w')
        self.tree.heading("#0", text="Name")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.tree.bind("<Double-1>", self.on_item_double_click)
        # Context menu (right-click)
        self.tree.bind("<Button-3>", self.on_right_click)
        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(label="Change Permissions", command=self.change_permissions_selected)
        self._context_menu.add_command(label="Change Owner/Group", command=self.change_owner_group_selected)
        self._context_menu.add_command(label="Download", command=self.prompt_and_download)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="Delete", command=self.delete_selected)

        # Editor toolbar (Save + Search)
        editor_toolbar = ttk.Frame(self)
        editor_toolbar.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        editor_toolbar.columnconfigure(4, weight=1)

        ttk.Label(editor_toolbar, text="Editor:").grid(row=0, column=0, padx=(0, 6))
        self.save_button = ttk.Button(editor_toolbar, text="Save", command=self.save_open_file, state='disabled')
        self.save_button.grid(row=0, column=1)

        ttk.Label(editor_toolbar, text="Search:").grid(row=0, column=2, padx=(10, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(editor_toolbar, textvariable=self.search_var, state='disabled')
        self.search_entry.grid(row=0, column=3, sticky=(tk.W, tk.E))
        self.find_next_button = ttk.Button(editor_toolbar, text="Find Next", command=self.find_next, state='disabled')
        self.find_next_button.grid(row=0, column=4, padx=(6, 0), sticky=tk.W)

        # Editor text area
        editor_frame = ttk.Frame(self)
        editor_frame.grid(row=3, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(5, 0))
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        self.editor_text = tk.Text(editor_frame, wrap='none', undo=True)
        self.editor_vscroll = ttk.Scrollbar(editor_frame, orient='vertical', command=self.editor_text.yview)
        self.editor_hscroll = ttk.Scrollbar(editor_frame, orient='horizontal', command=self.editor_text.xview)
        self.editor_text.configure(yscrollcommand=self.editor_vscroll.set, xscrollcommand=self.editor_hscroll.set)
        self.editor_text.grid(row=0, column=0, sticky='nsew')
        self.editor_vscroll.grid(row=0, column=1, sticky='ns')
        self.editor_hscroll.grid(row=1, column=0, sticky='ew')

        # Configure tags and bindings for editor
        self.editor_text.tag_configure('search_highlight', background='yellow')
        self.editor_text.bind('<<Modified>>', self._on_text_modified)

        self.status_var = tk.StringVar(value="Not connected")
        status_bar = ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(5, 0))

        self.set_enabled(False)

    def set_enabled(self, enabled: bool):
        state = 'normal' if enabled else 'disabled'
        self.up_button.config(state=state)
        self.tree.config(selectmode='browse' if enabled else 'none')
        self.enabled = enabled
        # Editor controls follow enabled state but remain disabled until a file is open
        if not enabled:
            self._set_editor_enabled(False)

    def attach_client(self, ssh_client: Optional[paramiko.SSHClient]):
        """Attach or detach an SSH client; refresh the view accordingly."""
        # Close previous SFTP if any
        if self.sftp_client:
            try:
                self.sftp_client.close()
            except Exception:
                pass
            self.sftp_client = None

        self.ssh_client = ssh_client

        if self.ssh_client is None:
            self.current_path.set("Not connected")
            self.status_var.set("Not connected")
            self.tree.delete(*self.tree.get_children())
            self.set_enabled(False)
            self._transfer_in_progress = False
            return

        try:
            self.sftp_client = self.ssh_client.open_sftp()
            # Reset owner/group caches for the new connection
            self._uid_cache: Dict[int, str] = {}
            self._gid_cache: Dict[int, str] = {}
            initial_path = self.sftp_client.normalize('.')
            initial_path = posixpath.normpath(initial_path)
            self.set_enabled(True)
            self.list_directory(initial_path)
        except Exception as e:
            self.status_var.set(f"SFTP error: {e}")
            messagebox.showerror("SFTP Error", f"Could not open SFTP session: {e}")
            self.set_enabled(False)

    def list_directory(self, path: str):
        if not self.sftp_client:
            return
        path = posixpath.normpath(path) if path else '/'
        self.current_path.set(path)
        self.tree.delete(*self.tree.get_children())
        try:
            items = self.sftp_client.listdir_attr(path)
            self.status_var.set(f"Listing {path}")
            # Resolve owner/group for any unknown uids/gids
            pending_uids = set()
            pending_gids = set()
            for attr in items:
                uid = getattr(attr, 'st_uid', None)
                gid = getattr(attr, 'st_gid', None)
                if isinstance(uid, int) and uid not in getattr(self, '_uid_cache', {}):
                    pending_uids.add(uid)
                if isinstance(gid, int) and gid not in getattr(self, '_gid_cache', {}):
                    pending_gids.add(gid)
            if pending_uids or pending_gids:
                try:
                    self._resolve_ids(pending_uids, pending_gids)
                except Exception:
                    # Non-fatal; leave numeric if resolution failed
                    pass
            dirs, files = [], []
            for attr in items:
                is_dir = stat.S_ISDIR(attr.st_mode)
                perms = self._perms_from_mode(attr.st_mode)
                uid = getattr(attr, 'st_uid', None)
                gid = getattr(attr, 'st_gid', None)
                owner = self._uid_cache.get(uid, str(uid) if uid is not None else '?')
                group = self._gid_cache.get(gid, str(gid) if gid is not None else '?')
                entry = (attr.filename, attr.st_size, is_dir, owner, group, perms)
                (dirs if is_dir else files).append(entry)
            dirs.sort(key=lambda x: x[0].lower())
            files.sort(key=lambda x: x[0].lower())
            for name, size, is_dir, owner, group, perms in dirs + files:
                values = (size, "Directory" if is_dir else "File", owner, group, perms)
                tags = ('directory',) if is_dir else ()
                self.tree.insert("", "end", text=name, values=values, tags=tags)
            self.tree.tag_configure('directory', foreground='blue', font=('TkDefaultFont', 9, 'bold'))
        except Exception as e:
            self.status_var.set(f"Error: {e}")
            messagebox.showerror("Error", f"Could not list directory '{path}':\n{e}")

    def _perms_from_mode(self, mode: int) -> str:
        # File type
        if stat.S_ISDIR(mode):
            ftype = 'd'
        elif stat.S_ISLNK(mode):
            ftype = 'l'
        else:
            ftype = '-'
        # Permissions rwx for user, group, other
        perms = ''
        for who, r, w, x in (
            ('USR', stat.S_IRUSR, stat.S_IWUSR, stat.S_IXUSR),
            ('GRP', stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP),
            ('OTH', stat.S_IROTH, stat.S_IWOTH, stat.S_IXOTH),
        ):
            perms += 'r' if (mode & r) else '-'
            perms += 'w' if (mode & w) else '-'
            perms += 'x' if (mode & x) else '-'
        return ftype + perms

    def _resolve_ids(self, uids: set, gids: set):
        """Resolve numeric uids/gids to names on the remote system using getent or passwd/group files."""
        if not self.ssh_client:
            return
        # Initialize caches if missing
        if not hasattr(self, '_uid_cache'):
            self._uid_cache = {}
        if not hasattr(self, '_gid_cache'):
            self._gid_cache = {}

        def run_cmd(cmd: str) -> str:
            try:
                stdin, stdout, stderr = self.ssh_client.exec_command(cmd, timeout=5)
                out = stdout.read().decode('utf-8', errors='ignore')
                return out
            except Exception:
                return ''

        # Try getent for users
        if uids:
            # getent passwd 0 1000 1001 ...
            uid_list = ' '.join(str(u) for u in uids)
            out = run_cmd(f"getent passwd {uid_list}")
            for line in out.splitlines():
                parts = line.split(':')
                if len(parts) >= 3 and parts[2].isdigit():
                    uid = int(parts[2])
                    name = parts[0]
                    self._uid_cache[uid] = name
            # Fallback: parse /etc/passwd if needed
            missing_uids = [u for u in uids if u not in self._uid_cache]
            if missing_uids:
                etc = run_cmd('cat /etc/passwd')
                for line in etc.splitlines():
                    parts = line.split(':')
                    if len(parts) >= 3 and parts[2].isdigit():
                        uid = int(parts[2])
                        name = parts[0]
                        if uid in missing_uids:
                            self._uid_cache[uid] = name

        # Try getent for groups
        if gids:
            gid_list = ' '.join(str(g) for g in gids)
            out = run_cmd(f"getent group {gid_list}")
            for line in out.splitlines():
                parts = line.split(':')
                if len(parts) >= 3 and parts[2].isdigit():
                    gid = int(parts[2])
                    name = parts[0]
                    self._gid_cache[gid] = name
            missing_gids = [g for g in gids if g not in self._gid_cache]
            if missing_gids:
                etc = run_cmd('cat /etc/group')
                for line in etc.splitlines():
                    parts = line.split(':')
                    if len(parts) >= 3 and parts[2].isdigit():
                        gid = int(parts[2])
                        name = parts[0]
                        if gid in missing_gids:
                            self._gid_cache[gid] = name

    def on_item_double_click(self, event):
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
        elif item_type == "File":
            filename = item['text']
            remote_path = posixpath.normpath(posixpath.join(self.current_path.get(), filename))
            self.open_remote_file(remote_path)

    def on_right_click(self, event):
        # Select the row under the mouse and show the context menu
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
            self.tree.focus(row_id)
            # Enable/disable menu items based on whether it's a file or directory
            try:
                item = self.tree.item(row_id)
                values = item.get('values') or []
                item_type = values[1] if len(values) > 1 else None
                is_file = item_type == 'File'
                # indices: 0=Change Permissions,1=Change Owner/Group,2=sep,3=Download,4=Delete
                self._context_menu.entryconfigure(2, state='normal' if is_file else 'disabled')  # Download
                self._context_menu.entryconfigure(4, state='normal' if is_file else 'disabled')  # Delete
            except Exception:
                # Fall back to enabling everything
                self._context_menu.entryconfigure(3, state='normal')
                self._context_menu.entryconfigure(4, state='normal')
            self._context_menu.tk_popup(event.x_root, event.y_root)
        else:
            # Clicked empty area; optionally could show generic menu
            pass

    def _get_selected_item_info(self):
        sel = self.tree.selection()
        if not sel:
            return None, None, None
        item = self.tree.item(sel[0])
        values = item.get('values') or []
        item_type = values[1] if len(values) > 1 else None
        name = item['text']
        remote_path = posixpath.normpath(posixpath.join(self.current_path.get(), name))
        try:
            attr = self.sftp_client.stat(remote_path) if self.sftp_client else None
        except Exception:
            attr = None
        return remote_path, item_type, attr

    def change_permissions_selected(self):
        if not self.sftp_client:
            return
        remote_path, item_type, attr = self._get_selected_item_info()
        if not remote_path or not attr:
            return
        dlg = PermissionsDialog(self, attr.st_mode)
        if dlg.result is None:
            return
        new_perm_bits = dlg.result  # lower 9 bits
        # Preserve file type bits
        new_mode = (attr.st_mode & ~0o777) | (new_perm_bits & 0o777)
        try:
            self.sftp_client.chmod(remote_path, new_mode)
            self.status_var.set(f"Permissions updated for {remote_path}")
            self.list_directory(self.current_path.get())
        except Exception as e:
            messagebox.showerror("Change Permissions Failed", f"Could not change permissions:\n{e}")

    def change_owner_group_selected(self):
        if not self.sftp_client:
            return
        remote_path, item_type, attr = self._get_selected_item_info()
        if not remote_path or not attr:
            return
        # Prefill with names if available from caches; else numeric
        uid = getattr(attr, 'st_uid', None)
        gid = getattr(attr, 'st_gid', None)
        owner_name = self._uid_cache.get(uid, str(uid) if uid is not None else '') if hasattr(self, '_uid_cache') else (str(uid) if uid is not None else '')
        group_name = self._gid_cache.get(gid, str(gid) if gid is not None else '') if hasattr(self, '_gid_cache') else (str(gid) if gid is not None else '')
        dlg = OwnerGroupDialog(self, owner_name, group_name)
        if dlg.result is None:
            return
        new_owner, new_group = dlg.result
        # Resolve names to ids (numeric allowed)
        uid_val = self._name_to_uid(new_owner) if new_owner != '' else uid
        gid_val = self._name_to_gid(new_group) if new_group != '' else gid
        if uid_val is None or gid_val is None:
            messagebox.showerror("Invalid Owner/Group", "Failed to resolve owner or group to numeric IDs.")
            return
        try:
            self.sftp_client.chown(remote_path, uid_val, gid_val)
            # Update caches
            if hasattr(self, '_uid_cache'):
                self._uid_cache[uid_val] = new_owner
            if hasattr(self, '_gid_cache'):
                self._gid_cache[gid_val] = new_group
            self.status_var.set(f"Owner/Group updated for {remote_path}")
            self.list_directory(self.current_path.get())
        except Exception as e:
            messagebox.showerror("Change Owner/Group Failed", f"Could not change owner/group:\n{e}")

    def delete_selected(self):
        if not self.sftp_client:
            return
        remote_path, item_type, attr = self._get_selected_item_info()
        if not remote_path or not attr:
            return
        if item_type != 'File':
            messagebox.showwarning("Unsupported", "Delete currently supports files only.")
            return
        name = posixpath.basename(remote_path)
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{name}'?"):
            return
        try:
            self.sftp_client.remove(remote_path)
            self.status_var.set(f"Deleted {name}")
            self.list_directory(self.current_path.get())
        except Exception as e:
            messagebox.showerror("Delete Failed", f"Could not delete file:\n{e}")

    def _name_to_uid(self, name: str) -> Optional[int]:
        if name is None or name == '':
            return None
        name = str(name).strip()
        if name.isdigit():
            return int(name)
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(f"id -u {name}", timeout=5)
            out = stdout.read().decode('utf-8', errors='ignore').strip()
            if out.isdigit():
                uid = int(out)
                if hasattr(self, '_uid_cache'):
                    self._uid_cache[uid] = name
                return uid
        except Exception:
            pass
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(f"getent passwd {name}", timeout=5)
            out = stdout.read().decode('utf-8', errors='ignore')
            for line in out.splitlines():
                parts = line.split(':')
                if len(parts) >= 3 and parts[0] == name and parts[2].isdigit():
                    uid = int(parts[2])
                    if hasattr(self, '_uid_cache'):
                        self._uid_cache[uid] = name
                    return uid
        except Exception:
            pass
        return None

    def _name_to_gid(self, name: str) -> Optional[int]:
        if name is None or name == '':
            return None
        name = str(name).strip()
        if name.isdigit():
            return int(name)
        try:
            stdin, stdout, stderr = self.ssh_client.exec_command(f"getent group {name}", timeout=5)
            out = stdout.read().decode('utf-8', errors='ignore')
            for line in out.splitlines():
                parts = line.split(':')
                if len(parts) >= 3 and parts[0] == name and parts[2].isdigit():
                    gid = int(parts[2])
                    if hasattr(self, '_gid_cache'):
                        self._gid_cache[gid] = name
                    return gid
        except Exception:
            pass
        return None

    def go_up_directory(self):
        current = self.current_path.get() or '/'
        norm_current = posixpath.normpath(current)
        if norm_current == '/':
            self.list_directory('/')
            return
        parent_path = posixpath.dirname(norm_current)
        if not parent_path:
            parent_path = '/'
        self.list_directory(parent_path)

    def _get_active_or_selected_dir(self) -> Optional[str]:
        """Return the target remote directory: selected directory if any, else current path."""
        if not self.enabled or not self.sftp_client:
            return None
        base = self.current_path.get()
        sel = self.tree.selection()
        if sel:
            item = self.tree.item(sel[0])
            values = item.get('values') or []
            item_type = values[1] if len(values) > 1 else None
            if item_type == 'Directory':
                dir_name = item['text']
                return posixpath.normpath(posixpath.join(base, dir_name))
        return base

    def prompt_and_upload(self):
        """Open a file dialog and upload the chosen file to the active/selected remote directory."""
        if not self.sftp_client:
            messagebox.showwarning("Not Connected", "Please connect to a server first.")
            return

        if getattr(self, '_transfer_in_progress', False):
            self.status_var.set("Another transfer is in progress. Please wait...")
            return

        # center native dialog by passing parent
        local_path = filedialog.askopenfilename(title="Select file to upload", parent=self)
        if not local_path:
            return  # cancelled

        remote_dir = self._get_active_or_selected_dir()
        if not remote_dir:
            messagebox.showwarning("No Target", "Unable to determine remote directory.")
            return

        filename = Path(local_path).name
        remote_path = posixpath.join(remote_dir, filename)

        # Existence and overwrite checks
        def _stat(path):
            try:
                return self.sftp_client.stat(path)
            except Exception:
                return None

        existing = _stat(remote_path)
        if existing is not None:
            # If a directory exists with same name, block
            if stat.S_ISDIR(existing.st_mode):
                messagebox.showerror("Upload Error", f"A directory named '{filename}' already exists at the destination.")
                return
            # Confirm overwrite
            if not messagebox.askyesno("Overwrite?", f"'{filename}' already exists. Overwrite?"):
                return

        # Run upload in background to keep UI responsive
        self._transfer_in_progress = True
        self.status_var.set(f"Uploading {filename} to {remote_dir}...")
        self.set_enabled(False)

        def _do_upload():
            err = None
            try:
                self.sftp_client.put(local_path, remote_path)
            except Exception as e:
                err = e
            finally:
                # Back to UI thread
                try:
                    self.after(0, lambda: self._after_upload(remote_dir, filename, err))
                except Exception:
                    pass

        threading.Thread(target=_do_upload, daemon=True).start()

    def _after_upload(self, remote_dir: str, filename: str, err: Optional[Exception]):
        self._transfer_in_progress = False
        self.set_enabled(True)
        if err is None:
            self.status_var.set(f"Uploaded {filename} to {remote_dir}")
            # Refresh listing
            self.list_directory(remote_dir)
        else:
            self.status_var.set(f"Upload failed: {err}")
            messagebox.showerror("Upload Failed", f"Could not upload file:\n{err}")

    def prompt_and_download(self):
        """Download the selected file from the remote browser to a chosen local path."""
        if not self.sftp_client:
            messagebox.showwarning("Not Connected", "Please connect to a server first.")
            return

        if getattr(self, '_transfer_in_progress', False):
            self.status_var.set("Another transfer is in progress. Please wait...")
            return

        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select a file to download.")
            return

        item = self.tree.item(sel[0])
        values = item.get('values') or []
        item_type = values[1] if len(values) > 1 else None
        if item_type != 'File':
            messagebox.showwarning("Invalid Selection", "Please select a file (not a directory).")
            return

        filename = item['text']
        remote_path = posixpath.normpath(posixpath.join(self.current_path.get(), filename))

        # Ask for local save location
        # center native dialog by passing parent
        local_path = filedialog.asksaveasfilename(title="Save As", initialfile=filename, parent=self)
        if not local_path:
            return

        local_path_obj = Path(local_path)
        if local_path_obj.exists() and local_path_obj.is_dir():
            messagebox.showerror("Download Error", "A directory exists at the chosen path. Please choose a file path.")
            return
        if local_path_obj.exists():
            if not messagebox.askyesno("Overwrite?", f"'{local_path_obj.name}' already exists. Overwrite?"):
                return

        # Run download in background
        self._transfer_in_progress = True
        self.status_var.set(f"Downloading {filename}...")
        self.set_enabled(False)

        def _do_download():
            err = None
            try:
                self.sftp_client.get(remote_path, str(local_path_obj))
            except Exception as e:
                err = e
            finally:
                try:
                    self.after(0, lambda: self._after_download(filename, str(local_path_obj), err))
                except Exception:
                    pass

        threading.Thread(target=_do_download, daemon=True).start()

    def _after_download(self, filename: str, local_path: str, err: Optional[Exception]):
        self._transfer_in_progress = False
        self.set_enabled(True)
        if err is None:
            self.status_var.set(f"Downloaded {filename} to {local_path}")
        else:
            self.status_var.set(f"Download failed: {err}")
            messagebox.showerror("Download Failed", f"Could not download file:\n{err}")

    # ----- Editor features -----
    def _set_editor_enabled(self, enabled: bool):
        state = 'normal' if enabled else 'disabled'
        self.save_button.config(state=state)
        self.search_entry.config(state=state)
        self.find_next_button.config(state=state)
        self.editor_text.config(state=state)

    def _on_text_modified(self, event=None):
        # Tk sets the modified flag continuously; we need to reset it
        if self.editor_text.edit_modified():
            self._editor_dirty = True
            self.status_var.set(f"Editing: {self.open_file_path or ''} (modified)")
            self.editor_text.edit_modified(False)

    def open_remote_file(self, remote_path: str):
        if not self.sftp_client:
            return
        # Limit preview size to ~2MB to avoid freezing UI
        MAX_PREVIEW_BYTES = 2_000_000
        try:
            attr = self.sftp_client.stat(remote_path)
            if stat.S_ISDIR(attr.st_mode):
                return
            if attr.st_size > MAX_PREVIEW_BYTES:
                messagebox.showwarning("Large File", "File is larger than 2MB. Download it instead for viewing.")
                return
            with self.sftp_client.open(remote_path, 'r') as f:
                raw = f.read()
            if b'\x00' in raw:
                messagebox.showwarning("Binary File", "This file appears to be binary and cannot be previewed.")
                return
            try:
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                # Fallback with replacement to display something
                text = raw.decode('utf-8', errors='replace')
            # Load into editor
            self.editor_text.config(state='normal')
            self.editor_text.delete('1.0', 'end')
            self.editor_text.insert('1.0', text)
            self.editor_text.edit_modified(False)
            self._editor_dirty = False
            self.open_file_path = remote_path
            self._clear_search_highlight()
            self._set_editor_enabled(True)
            self.status_var.set(f"Opened: {remote_path}")
        except Exception as e:
            messagebox.showerror("Open Failed", f"Could not open remote file:\n{e}")

    def save_open_file(self):
        if not self.sftp_client or not self.open_file_path:
            return
        content = self.editor_text.get('1.0', 'end-1c')
        if not messagebox.askyesno("Confirm Save", f"Save changes to {self.open_file_path}?"):
            return
        self.status_var.set("Saving...")
        self._set_editor_enabled(False)
        def _do_save():
            err = None
            try:
                with self.sftp_client.open(self.open_file_path, 'w') as f:
                    f.write(content)
            except Exception as e:
                err = e
            finally:
                try:
                    self.after(0, lambda: self._after_save(err))
                except Exception:
                    pass
        threading.Thread(target=_do_save, daemon=True).start()

    def _after_save(self, err: Optional[Exception]):
        self._set_editor_enabled(True)
        if err is None:
            self._editor_dirty = False
            self.editor_text.edit_modified(False)
            self.status_var.set(f"Saved: {self.open_file_path}")
            # Optionally refresh directory to update size/mtime
            cur = self.current_path.get()
            self.list_directory(cur)
        else:
            self.status_var.set(f"Save failed: {err}")
            messagebox.showerror("Save Failed", f"Could not save file:\n{err}")

    def _clear_search_highlight(self):
        self.editor_text.tag_remove('search_highlight', '1.0', 'end')

    def _highlight_all(self, pattern: str):
        self._clear_search_highlight()
        if not pattern:
            return
        start = '1.0'
        while True:
            idx = self.editor_text.search(pattern, start, stopindex='end')
            if not idx:
                break
            end = f"{idx}+{len(pattern)}c"
            self.editor_text.tag_add('search_highlight', idx, end)
            start = end

    def find_next(self):
        pattern = self.search_var.get()
        if not pattern:
            return
        self._highlight_all(pattern)
        # Find next from current insert position
        start = self.editor_text.index('insert')
        idx = self.editor_text.search(pattern, start, stopindex='end')
        if not idx:
            # Wrap around
            idx = self.editor_text.search(pattern, '1.0', stopindex='end')
            if not idx:
                return
        end = f"{idx}+{len(pattern)}c"
        self.editor_text.see(idx)
        self.editor_text.tag_remove('sel', '1.0', 'end')
        self.editor_text.tag_add('sel', idx, end)

class ServerDialog:
    """Dialog for adding/editing server information."""
    
    def __init__(self, parent, title, server_data=None, server_name=""):
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.setup_dialog_ui(server_data, server_name)
        # Center after layout relative to parent
        try:
            center_window(self.dialog, parent)
        except Exception:
            pass
        
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

class PermissionsDialog:
    """Dialog to change POSIX permissions using checkboxes for user/group/other."""
    def __init__(self, parent, current_mode: int):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Change Permissions")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        frm = ttk.Frame(self.dialog, padding=10)
        frm.grid(row=0, column=0, sticky='nsew')

        self.vars = {
            'ur': tk.BooleanVar(value=bool(current_mode & stat.S_IRUSR)),
            'uw': tk.BooleanVar(value=bool(current_mode & stat.S_IWUSR)),
            'ux': tk.BooleanVar(value=bool(current_mode & stat.S_IXUSR)),
            'gr': tk.BooleanVar(value=bool(current_mode & stat.S_IRGRP)),
            'gw': tk.BooleanVar(value=bool(current_mode & stat.S_IWGRP)),
            'gx': tk.BooleanVar(value=bool(current_mode & stat.S_IXGRP)),
            'or': tk.BooleanVar(value=bool(current_mode & stat.S_IROTH)),
            'ow': tk.BooleanVar(value=bool(current_mode & stat.S_IWOTH)),
            'ox': tk.BooleanVar(value=bool(current_mode & stat.S_IXOTH)),
        }

        def row(y, label, r, w, x):
            ttk.Label(frm, text=label).grid(row=y, column=0, sticky='w', padx=(0,8))
            ttk.Checkbutton(frm, text='r', variable=self.vars[r]).grid(row=y, column=1)
            ttk.Checkbutton(frm, text='w', variable=self.vars[w]).grid(row=y, column=2)
            ttk.Checkbutton(frm, text='x', variable=self.vars[x]).grid(row=y, column=3)

        row(0, 'User', 'ur', 'uw', 'ux')
        row(1, 'Group', 'gr', 'gw', 'gx')
        row(2, 'Other', 'or', 'ow', 'ox')

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=4, pady=(10,0))
        ttk.Button(btns, text='OK', command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text='Cancel', command=self.cancel).pack(side=tk.LEFT, padx=5)
        try:
            center_window(self.dialog, parent)
        except Exception:
            pass
        self.dialog.wait_window()

    def ok(self):
        mode = 0
        if self.vars['ur'].get():
            mode |= stat.S_IRUSR
        if self.vars['uw'].get():
            mode |= stat.S_IWUSR
        if self.vars['ux'].get():
            mode |= stat.S_IXUSR
        if self.vars['gr'].get():
            mode |= stat.S_IRGRP
        if self.vars['gw'].get():
            mode |= stat.S_IWGRP
        if self.vars['gx'].get():
            mode |= stat.S_IXGRP
        if self.vars['or'].get():
            mode |= stat.S_IROTH
        if self.vars['ow'].get():
            mode |= stat.S_IWOTH
        if self.vars['ox'].get():
            mode |= stat.S_IXOTH
        self.result = mode
        self.dialog.destroy()

    def cancel(self):
        self.dialog.destroy()

class OwnerGroupDialog:
    """Dialog to input owner and group names (or numeric IDs)."""
    def __init__(self, parent, owner_initial: str, group_initial: str):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Change Owner/Group")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        frm = ttk.Frame(self.dialog, padding=10)
        frm.grid(row=0, column=0, sticky='nsew')
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text='Owner:').grid(row=0, column=0, sticky='w', padx=(0,8), pady=5)
        self.owner_var = tk.StringVar(value=owner_initial)
        ttk.Entry(frm, textvariable=self.owner_var).grid(row=0, column=1, sticky='ew', pady=5)

        ttk.Label(frm, text='Group:').grid(row=1, column=0, sticky='w', padx=(0,8), pady=5)
        self.group_var = tk.StringVar(value=group_initial)
        ttk.Entry(frm, textvariable=self.group_var).grid(row=1, column=1, sticky='ew', pady=5)

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, pady=(10,0))
        ttk.Button(btns, text='OK', command=self.ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btns, text='Cancel', command=self.cancel).pack(side=tk.LEFT, padx=5)
        try:
            center_window(self.dialog, parent)
        except Exception:
            pass
        self.dialog.wait_window()

    def ok(self):
        self.result = (self.owner_var.get().strip(), self.group_var.get().strip())
        self.dialog.destroy()

    def cancel(self):
        self.dialog.destroy()

def main():
    """Main application entry point."""
    root = tk.Tk()
    # Center main window at 50% of screen size
    try:
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = max(700, int(sw * 0.5))
        h = max(500, int(sh * 0.5))
        x = (sw - w) // 2
        y = (sh - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        root.geometry("900x600")
    
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