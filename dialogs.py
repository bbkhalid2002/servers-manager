import stat
import tkinter as tk
from tkinter import ttk, messagebox

from utils import center_window


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
            ttk.Label(frm, text=label).grid(row=y, column=0, sticky='w', padx=(0, 8))
            ttk.Checkbutton(frm, text='r', variable=self.vars[r]).grid(row=y, column=1)
            ttk.Checkbutton(frm, text='w', variable=self.vars[w]).grid(row=y, column=2)
            ttk.Checkbutton(frm, text='x', variable=self.vars[x]).grid(row=y, column=3)

        row(0, 'User', 'ur', 'uw', 'ux')
        row(1, 'Group', 'gr', 'gw', 'gx')
        row(2, 'Other', 'or', 'ow', 'ox')

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, columnspan=4, pady=(10, 0))
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

        ttk.Label(frm, text='Owner:').grid(row=0, column=0, sticky='w', padx=(0, 8), pady=5)
        self.owner_var = tk.StringVar(value=owner_initial)
        ttk.Entry(frm, textvariable=self.owner_var).grid(row=0, column=1, sticky='ew', pady=5)

        ttk.Label(frm, text='Group:').grid(row=1, column=0, sticky='w', padx=(0, 8), pady=5)
        self.group_var = tk.StringVar(value=group_initial)
        ttk.Entry(frm, textvariable=self.group_var).grid(row=1, column=1, sticky='ew', pady=5)

        btns = ttk.Frame(frm)
        btns.grid(row=2, column=0, columnspan=2, pady=(10, 0))
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
