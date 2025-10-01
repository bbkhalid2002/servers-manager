import tkinter as tk
from tkinter import ttk, messagebox
import os
import threading
from typing import Optional

from utils import center_window, resource_path
from credentials import CredentialManager
from ssh_connection import SSHConnection
from file_browser import RemoteFileBrowserFrame
from dialogs import ServerDialog
from json_viewer import JSONViewerWindow


class ServerManagerGUI:
    """Main GUI application for SSH server management."""

    def __init__(self, root):
        self.root = root
        self.root.title("SSH Server Manager")
        # Geometry is set by the launcher

        self.credential_manager = CredentialManager()
        self.ssh_connection = SSHConnection()
        self.connected_server_name: Optional[str] = None

        self.setup_ui()
        self.refresh_server_list()

    def setup_ui(self):
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
        # Tools menu with JSON Viewer
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="JSON Viewer", command=self.open_json_viewer)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        # Help menu with About
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.config(menu=menubar)

        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

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

        # Load server icon (once)
        self._server_icon = None
        try:
            icon_path = resource_path('server_manager_icons', 'server.png')
            if os.path.exists(icon_path):
                self._server_icon = tk.PhotoImage(file=icon_path)
        except Exception:
            self._server_icon = None

        # Use Treeview to support per-row icons
        self.server_tree = ttk.Treeview(servers_frame, show='tree', style='ServerList.Treeview')
        scrollbar = ttk.Scrollbar(servers_frame, orient='vertical', command=self.server_tree.yview)
        self.server_tree.configure(yscrollcommand=scrollbar.set)
        self.server_tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        # Double-click action on server item
        def _on_server_tree_double_click(event):
            row_id = self.server_tree.identify_row(event.y)
            if not row_id:
                return
            self.server_tree.selection_set(row_id)
            self.server_tree.focus(row_id)
            self.on_server_double_click(event)
        self.server_tree.bind('<Double-1>', _on_server_tree_double_click)

        # Right panel: notebook with tabs (File Management selected, Server empty)
        right_panel = ttk.Frame(paned, padding="5")
        right_panel.columnconfigure(0, weight=1)
        right_panel.rowconfigure(0, weight=1)

        # Style: add padding to tab labels and margins, and spacing between tabs and content; ensure server list row height 16
        try:
            style = ttk.Style(self.root)
            style.configure('Custom.TNotebook.Tab', padding=(12, 6))
            style.configure('Custom.TNotebook', tabmargins=(6, 6, 6, 0))
            style.configure('ServerList.Treeview', rowheight=16)
        except Exception:
            pass

        notebook = ttk.Notebook(right_panel, style='Custom.TNotebook')
        notebook.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # File Management tab
        file_mgmt_tab = ttk.Frame(notebook, padding=(10, 12, 10, 10))
        file_mgmt_tab.columnconfigure(0, weight=1)
        file_mgmt_tab.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(file_mgmt_tab)
        toolbar.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        file_actions_right = ttk.Frame(toolbar)
        file_actions_right.pack(side=tk.RIGHT)
        # Load toolbar icons
        try:
            self._icon_upload = tk.PhotoImage(file=resource_path('server_manager_icons', 'upload.png'))
        except Exception:
            self._icon_upload = None
        try:
            self._icon_download = tk.PhotoImage(file=resource_path('server_manager_icons', 'download.png'))
        except Exception:
            self._icon_download = None
        self.upload_button = ttk.Button(
            file_actions_right,
            text="Upload",
            image=self._icon_upload,
            compound='left',
            command=self.on_upload_click,
            state='disabled'
        )
        self.upload_button.pack(side=tk.LEFT)
        self.download_button = ttk.Button(
            file_actions_right,
            text="Download",
            image=self._icon_download,
            compound='left',
            command=self.on_download_click,
            state='disabled'
        )
        self.download_button.pack(side=tk.LEFT, padx=(5, 0))

        self.file_browser = RemoteFileBrowserFrame(file_mgmt_tab)
        self.file_browser.grid(row=1, column=0, sticky=(tk.N, tk.S, tk.E, tk.W))

        # Server tab - manage favorite services
        server_tab = ttk.Frame(notebook, padding=(10, 12, 10, 10))
        server_tab.columnconfigure(0, weight=1)
        server_tab.rowconfigure(1, weight=1)
        server_tab.rowconfigure(3, weight=19)

        # Top actions toolbar
        top_actions = ttk.Frame(server_tab)
        top_actions.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 8))
        actions_right = ttk.Frame(top_actions)
        actions_right.pack(side=tk.RIGHT)
        # Load action icons
        try:
            self._icon_start = tk.PhotoImage(file=resource_path('server_manager_icons', 'start.png'))
        except Exception:
            self._icon_start = None
        try:
            self._icon_stop = tk.PhotoImage(file=resource_path('server_manager_icons', 'stop.png'))
        except Exception:
            self._icon_stop = None
        try:
            self._icon_status = tk.PhotoImage(file=resource_path('server_manager_icons', 'status.png'))
        except Exception:
            self._icon_status = None
        try:
            self._icon_add_service = tk.PhotoImage(file=resource_path('server_manager_icons', 'add_service.png'))
        except Exception:
            self._icon_add_service = None
        try:
            self._icon_remove_service = tk.PhotoImage(file=resource_path('server_manager_icons', 'remove_service.png'))
        except Exception:
            self._icon_remove_service = None

        self.svc_start_btn = ttk.Button(actions_right, text='Start', image=self._icon_start, compound='left', command=lambda: self._svc_action('start'), state='disabled')
        self.svc_start_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.svc_stop_btn = ttk.Button(actions_right, text='Stop', image=self._icon_stop, compound='left', command=lambda: self._svc_action('stop'), state='disabled')
        self.svc_stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.svc_status_btn = ttk.Button(actions_right, text='Status', image=self._icon_status, compound='left', command=lambda: self._svc_action('status'), state='disabled')
        self.svc_status_btn.pack(side=tk.LEFT, padx=(0, 6))
        sep = ttk.Separator(actions_right, orient='vertical')
        sep.pack(side=tk.LEFT, fill='y', padx=8)
        self.svc_add_btn = ttk.Button(actions_right, text='Add Service', image=self._icon_add_service, compound='left', command=self._on_add_service_popup, state='disabled')
        self.svc_add_btn.pack(side=tk.LEFT)
        self.remove_service_btn = ttk.Button(actions_right, text='Remove Service', image=self._icon_remove_service, compound='left', command=self._remove_selected_service, state='disabled')
        self.remove_service_btn.pack(side=tk.LEFT, padx=(6, 0))

        # Services list
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
        def _on_services_double_click(event):
            row_id = self.services_tree.identify_row(event.y)
            if not row_id:
                return
            self.services_tree.selection_set(row_id)
            self.services_tree.focus(row_id)
            vals = self.services_tree.item(row_id).get('values') or []
            service = vals[0] if vals else ''
            if service:
                self._fetch_service_logs_async(service)
        self.services_tree.bind('<Double-1>', _on_services_double_click)

        self._services_menu = tk.Menu(server_tab, tearoff=0)
        self._services_menu.add_command(label='Start', command=lambda: self._svc_action('start'))
        self._services_menu.add_command(label='Stop', command=lambda: self._svc_action('stop'))
        self._services_menu.add_command(label='Status', command=lambda: self._svc_action('status'))
        def _on_services_right_click(event):
            row_id = self.services_tree.identify_row(event.y)
            if row_id:
                self.services_tree.selection_set(row_id)
                self.services_tree.focus(row_id)
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

        # Logs area below services
        logs_frame = ttk.Frame(server_tab)
        logs_frame.grid(row=3, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(8, 0))
        logs_frame.columnconfigure(0, weight=1)
        logs_frame.rowconfigure(1, weight=1)
        logs_header = ttk.Frame(logs_frame)
        logs_header.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 4))
        ttk.Label(logs_header, text="Logs").pack(side=tk.LEFT)
        self._logs_find_var = tk.StringVar()
        find_bar = ttk.Frame(logs_header)
        find_bar.pack(side=tk.RIGHT)
        ttk.Label(find_bar, text="Find:").pack(side=tk.LEFT)
        self._logs_find_entry = ttk.Entry(find_bar, textvariable=self._logs_find_var, width=28)
        self._logs_find_entry.pack(side=tk.LEFT, padx=(4, 4))
        self._logs_find_entry.bind('<Return>', lambda e: self._find_next_in_logs())
        ttk.Button(find_bar, text="Find Next", command=self._find_next_in_logs).pack(side=tk.LEFT)
        self.svc_logs_text = tk.Text(
            logs_frame,
            height=10,
            wrap='word',
            state='disabled',
            foreground="#2CFF05",
            background="#000000",
            insertbackground='white'
        )
        try:
            self.svc_logs_text.tag_config('find_highlight', background='yellow', foreground='black')
        except Exception:
            pass
        logs_scroll = ttk.Scrollbar(logs_frame, orient='vertical', command=self.svc_logs_text.yview)
        self.svc_logs_text.configure(yscrollcommand=logs_scroll.set)
        self.svc_logs_text.grid(row=1, column=0, sticky='nsew')
        logs_scroll.grid(row=1, column=1, sticky='ns')

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

        try:
            self.root.after(150, self._set_initial_sash)
        except Exception:
            pass

    def _set_initial_sash(self):
        try:
            self.root.update_idletasks()
            pw = self.paned.winfo_width()
            if pw <= 1:
                self.root.after(150, self._set_initial_sash)
                return
            desired_left = int(pw * 0.25)
            min_side = 150
            max_left = max(min_side, pw - min_side)
            pos = max(min_side, min(desired_left, max_left))
            try:
                self.paned.sashpos(0, pos)
            except Exception:
                self.root.after(150, lambda: self._safe_set_sash(pos))
        except Exception:
            pass

    def _safe_set_sash(self, pos: int):
        try:
            self.paned.sashpos(0, pos)
        except Exception:
            pass

    def set_controls_enabled(self, enabled: bool):
        try:
            self.server_tree.configure(selectmode='browse' if enabled else 'none')
        except Exception:
            pass

    def refresh_server_list(self):
        try:
            for iid in self.server_tree.get_children(''):
                self.server_tree.delete(iid)
        except Exception:
            pass
        for server_name in self.credential_manager.list_servers():
            try:
                self.server_tree.insert('', 'end', text=server_name, image=self._server_icon)
            except Exception:
                self.server_tree.insert('', 'end', text=server_name)

    def add_server_dialog(self):
        dialog = ServerDialog(self.root, "Add Server")
        if dialog.result:
            name, host, username, password, port = dialog.result
            self.credential_manager.add_server(name, host, username, password, port)
            self.refresh_server_list()
            self.status_var.set(f"Added server: {name}")

    def edit_server_dialog(self):
        server_name = self._get_selected_server_name()
        if not server_name:
            messagebox.showwarning("Warning", "Please select a server to edit")
            return
        server_data = self.credential_manager.get_server(server_name)
        dialog = ServerDialog(self.root, "Edit Server", server_data, server_name)
        if dialog.result:
            new_name, host, username, password, port = dialog.result
            self.credential_manager.add_server(new_name, host, username, password, port)
            if new_name != server_name:
                self.credential_manager.delete_server(server_name)
            self.refresh_server_list()
            self.status_var.set(f"Updated server: {new_name}")

    def delete_server(self):
        server_name = self._get_selected_server_name()
        if not server_name:
            messagebox.showwarning("Warning", "Please select a server to delete")
            return
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete server '{server_name}'?"):
            self.credential_manager.delete_server(server_name)
            self.refresh_server_list()
            self.status_var.set(f"Deleted server: {server_name}")

    def on_server_double_click(self, event):
        row_id = self.server_tree.identify_row(event.y)
        if not row_id:
            return
        self.server_tree.selection_set(row_id)
        self.server_tree.focus(row_id)
        server_name = self.server_tree.item(row_id).get('text')
        if not self.ssh_connection.is_connected() or self.connected_server_name != server_name:
            self.connect_to_server_by_name(server_name)
        else:
            self.file_browser.attach_client(self.ssh_connection.client)

    def connect_to_server(self):
        server_name = self._get_selected_server_name()
        if not server_name:
            messagebox.showwarning("Warning", "Please select a server to connect to")
            return
        self.connect_to_server_by_name(server_name)

    def _get_selected_server_name(self) -> Optional[str]:
        try:
            sel = self.server_tree.selection()
            if not sel:
                return None
            return self.server_tree.item(sel[0]).get('text') or None
        except Exception:
            return None

    def connect_to_server_by_name(self, server_name: str):
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
        self.set_controls_enabled(True)
        self.status_var.set(message)
        if success:
            self.connected_server_name = server_name
            self.file_browser.attach_client(self.ssh_connection.client)
            self.upload_button.config(state='normal')
            self.download_button.config(state='normal')
            self._load_services_for_connected()
        else:
            self.connected_server_name = None
            self.file_browser.attach_client(None)
            self.upload_button.config(state='disabled')
            self.download_button.config(state='disabled')
            messagebox.showerror("Connection Failed", message)

    def disconnect_from_server(self):
        if self.ssh_connection.is_connected():
            self.ssh_connection.disconnect()
            self.connected_server_name = None
            self.file_browser.attach_client(None)
            self.upload_button.config(state='disabled')
            self.download_button.config(state='disabled')
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
        self.file_browser.prompt_and_upload()

    def on_download_click(self):
        self.file_browser.prompt_and_download()

    def _load_services_for_connected(self):
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
        self._refresh_services_status_async()

    def _set_services_ui_enabled(self, enabled: bool):
        state = 'normal' if enabled else 'disabled'
        for w in (self.remove_service_btn, self.svc_start_btn, self.svc_stop_btn, self.svc_status_btn, getattr(self, 'svc_add_btn', None)):
            try:
                if w is not None:
                    w.config(state=state)
            except Exception:
                pass
        try:
            self.services_tree.configure(selectmode='browse' if enabled else 'none')
        except Exception:
            pass
        self._update_service_actions_state()

    def _update_service_actions_state(self):
        enabled = self.ssh_connection.is_connected()
        sel = self.services_tree.selection()
        is_sel = bool(sel)
        for b in (self.remove_service_btn, self.svc_start_btn, self.svc_stop_btn, self.svc_status_btn):
            b.config(state='normal' if (enabled and is_sel) else 'disabled')
        try:
            self.svc_add_btn.config(state='normal' if enabled else 'disabled')
        except Exception:
            pass

    def _on_add_service_popup(self):
        if not self.ssh_connection.is_connected():
            messagebox.showwarning('Not Connected', 'Connect to a server first.')
            return
        dlg = tk.Toplevel(self.root)
        dlg.title('Add Service')
        dlg.transient(self.root)
        dlg.grab_set()
        frm = ttk.Frame(dlg, padding=10)
        frm.grid(row=0, column=0, sticky='nsew')
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)
        ttk.Label(frm, text='Service name:').grid(row=0, column=0, sticky='w')
        name_var = tk.StringVar()
        entry = ttk.Entry(frm, textvariable=name_var, width=40)
        entry.grid(row=1, column=0, sticky='ew', pady=(4, 8))
        entry.focus_set()
        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, sticky='e')
        def _save():
            val = (name_var.get() or '').strip()
            if not val:
                messagebox.showwarning('Validation', 'Please enter a service name.')
                return
            existing = []
            try:
                for iid in self.services_tree.get_children():
                    vals = self.services_tree.item(iid).get('values') or []
                    if vals:
                        existing.append(str(vals[0]))
            except Exception:
                pass
            if val in existing:
                messagebox.showinfo('Service Exists', f"'{val}' is already in favorites.")
                return
            self.services_tree.insert('', 'end', values=(val, ''))
            self._persist_services()
            self._refresh_services_status_async()
            try:
                dlg.destroy()
            except Exception:
                pass
        ttk.Button(btns, text='Save', command=_save).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(btns, text='Cancel', command=dlg.destroy).pack(side=tk.LEFT)
        try:
            center_window(dlg, self.root)
        except Exception:
            pass

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
        cmd = None
        if action in ('start', 'stop', 'status'):
            if action == 'status':
                cmd = f"systemctl status --no-pager {service}"
            else:
                cmd = f"sudo -n systemctl {action} {service} || systemctl {action} {service}"
        if not cmd:
            return
        if action in ('start', 'stop'):
            try:
                self.ssh_connection.client.exec_command(cmd)
            except Exception as e:
                messagebox.showerror('SSH Error', f"Failed to execute command:\n{e}")
                return
            self.root.after(500, self._refresh_services_status_async)
            self.root.after(600, lambda s=service: self._fetch_service_logs_async(s))
        elif action == 'status':
            self._run_remote_cmd(cmd, title=f"systemctl {action} {service}")

    def _run_remote_cmd(self, cmd: str, title: str = 'Command Output'):
        try:
            stdin, stdout, stderr = self.ssh_connection.client.exec_command(cmd)
            out = stdout.read().decode('utf-8', errors='replace')
            err = stderr.read().decode('utf-8', errors='replace')
        except Exception as e:
            messagebox.showerror('SSH Error', f"Failed to execute command:\n{e}")
            return
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

    def _refresh_services_status_async(self):
        if not self.ssh_connection.is_connected():
            return
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
            def update_ui():
                try:
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

    def _fetch_service_logs_async(self, service: str):
        if not self.ssh_connection.is_connected() or not service:
            return
        def worker():
            try:
                cmd = f"journalctl -u {service} -n 100 --no-pager --output=short-iso"
                stdin, stdout, stderr = self.ssh_connection.client.exec_command(cmd)
                out = stdout.read().decode('utf-8', errors='replace')
                err = stderr.read().decode('utf-8', errors='replace')
                text = out if out.strip() else err
            except Exception as e:
                text = f"Failed to fetch logs: {e}"
            def update_ui():
                try:
                    self.svc_logs_text.config(state='normal')
                    self.svc_logs_text.delete('1.0', 'end')
                    self.svc_logs_text.insert('1.0', text)
                    try:
                        self.svc_logs_text.see('end')
                    except Exception:
                        pass
                    self.svc_logs_text.config(state='disabled')
                except Exception:
                    pass
            try:
                self.root.after(0, update_ui)
            except Exception:
                pass
        threading.Thread(target=worker, daemon=True).start()

    def _find_next_in_logs(self):
        try:
            query = (self._logs_find_var.get() or '').strip()
        except Exception:
            query = ''
        if not query:
            return
        try:
            prev_state = str(self.svc_logs_text.cget('state'))
            self.svc_logs_text.config(state='normal')
            try:
                self.svc_logs_text.tag_remove('find_highlight', '1.0', 'end')
            except Exception:
                pass
            start_index = self.svc_logs_text.index('insert')
            pos = self.svc_logs_text.search(query, start_index, nocase=True, stopindex='end')
            if not pos:
                pos = self.svc_logs_text.search(query, '1.0', nocase=True, stopindex='end')
            if pos:
                end_pos = f"{pos}+{len(query)}c"
                self.svc_logs_text.tag_add('find_highlight', pos, end_pos)
                try:
                    self.svc_logs_text.mark_set('insert', end_pos)
                except Exception:
                    pass
                try:
                    self.svc_logs_text.see(pos)
                except Exception:
                    pass
            self.svc_logs_text.config(state=prev_state)
        except Exception:
            try:
                self.svc_logs_text.config(state='disabled')
            except Exception:
                pass

    def show_about(self):
        try:
            dlg = tk.Toplevel(self.root)
            dlg.title("About")
            dlg.transient(self.root)
            dlg.grab_set()
            frm = ttk.Frame(dlg, padding=12)
            frm.grid(row=0, column=0, sticky='nsew')
            dlg.columnconfigure(0, weight=1)
            dlg.rowconfigure(0, weight=1)
            msg = ("Developed in 2025 for a great team!")
            ttk.Label(frm, text=msg, wraplength=420, justify='center').grid(row=0, column=0, pady=(0, 10))
            ttk.Button(frm, text="OK", command=dlg.destroy).grid(row=1, column=0, sticky='e')
            try:
                center_window(dlg, self.root)
            except Exception:
                pass
        except Exception:
            try:
                messagebox.showinfo("About", "Developed in 2025 for a great team!")
            except Exception:
                pass

    def open_json_viewer(self):
        try:
            JSONViewerWindow(self.root)
        except Exception as e:
            messagebox.showerror("JSON Viewer", f"Failed to open JSON Viewer: {e}")
