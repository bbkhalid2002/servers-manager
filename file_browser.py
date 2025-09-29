import posixpath
import stat
import threading
import time
from pathlib import Path
from typing import Dict, Optional

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import paramiko

from dialogs import PermissionsDialog, OwnerGroupDialog


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

        # Columns: size, type, date, owner, group, perms (name is the tree column #0)
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("size", "type", "date", "owner", "group", "perms"),
            show="tree headings"
        )
        self.tree.heading("size", text="Size")
        self.tree.heading("type", text="Type")
        self.tree.heading("date", text="Date")
        self.tree.heading("owner", text="Owner")
        self.tree.heading("group", text="Group")
        self.tree.heading("perms", text="Permissions")
        self.tree.column("size", width=90, anchor='e')
        self.tree.column("type", width=80, anchor='w')
        self.tree.column("date", width=150, anchor='w')
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

        # Editor toolbar (Save + Search) aligned to the right side
        editor_toolbar = ttk.Frame(self)
        editor_toolbar.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        # Container anchored to the right so controls appear on the right edge
        editor_right = ttk.Frame(editor_toolbar)
        editor_right.pack(side=tk.RIGHT)

        ttk.Label(editor_right, text="Editor:").pack(side=tk.LEFT, padx=(0, 6))
        self.save_button = ttk.Button(editor_right, text="Save", command=self.save_open_file, state='disabled')
        self.save_button.pack(side=tk.LEFT)

        ttk.Label(editor_right, text="Search:").pack(side=tk.LEFT, padx=(10, 6))
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(editor_right, textvariable=self.search_var, state='disabled')
        self.search_entry.pack(side=tk.LEFT)
        # Press Enter in the search box to trigger Find Next
        try:
            self.search_entry.bind('<Return>', lambda e: self.find_next())
        except Exception:
            pass
        self.find_next_button = ttk.Button(editor_right, text="Find Next", command=self.find_next, state='disabled')
        self.find_next_button.pack(side=tk.LEFT, padx=(6, 0))

        # Editor text area
        editor_frame = ttk.Frame(self)
        editor_frame.grid(row=3, column=0, sticky=(tk.N, tk.S, tk.E, tk.W), pady=(5, 0))
        editor_frame.columnconfigure(0, weight=1)
        editor_frame.rowconfigure(0, weight=1)

        self.editor_text = tk.Text(
            editor_frame,
            wrap='none',
            undo=True,
            foreground="#2CFF05",
            background="#000000",
            insertbackground='white'
        )
        self.editor_vscroll = ttk.Scrollbar(editor_frame, orient='vertical', command=self.editor_text.yview)
        self.editor_hscroll = ttk.Scrollbar(editor_frame, orient='horizontal', command=self.editor_text.xview)
        self.editor_text.configure(yscrollcommand=self.editor_vscroll.set, xscrollcommand=self.editor_hscroll.set)
        self.editor_text.grid(row=0, column=0, sticky='nsew')
        self.editor_vscroll.grid(row=0, column=1, sticky='ns')
        self.editor_hscroll.grid(row=1, column=0, sticky='ew')

        # Configure tags and bindings for editor
        self.editor_text.tag_configure('search_highlight', background='yellow', foreground='black')
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
                # Format modification time if available
                try:
                    mtime = getattr(attr, 'st_mtime', None)
                    date_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(mtime)) if isinstance(mtime, (int, float)) else ''
                except Exception:
                    date_str = ''
                entry = (attr.filename, attr.st_size, is_dir, date_str, owner, group, perms)
                (dirs if is_dir else files).append(entry)
            dirs.sort(key=lambda x: x[0].lower())
            files.sort(key=lambda x: x[0].lower())
            for name, size, is_dir, date_str, owner, group, perms in dirs + files:
                values = (size, "Directory" if is_dir else "File", date_str, owner, group, perms)
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
