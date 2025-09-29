import os
import sys
import tkinter as tk
from typing import Optional


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


def resource_path(*relative_parts: str) -> str:
    """Return an absolute path to a resource, working for dev and PyInstaller bundle.

    Example: resource_path('server_manager_icons', 'server.png')
    """
    try:
        base_path = getattr(sys, '_MEIPASS')  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, *relative_parts)
