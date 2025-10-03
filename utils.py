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


def bring_window_to_front(win: tk.Tk | tk.Toplevel | tk.Misc):
    """Best-effort: bring a Tk window to the foreground and focus it.

    This toggles the always-on-top attribute briefly and focuses the window.
    On macOS, it also asks the app to become active, which prevents new
    windows from appearing behind other apps.
    """
    try:
        try:
            win.update_idletasks()
        except Exception:
            pass
        try:
            win.lift()
        except Exception:
            pass
        try:
            # Briefly set always-on-top to raise above others, then turn off
            win.attributes('-topmost', True)
            # Use a short delay to allow the window manager to process
            win.after(200, lambda: _clear_topmost_safely(win))
        except Exception:
            pass
        try:
            win.focus_force()
        except Exception:
            # Fall back to focus_set
            try:
                win.focus_set()
            except Exception:
                pass
        # macOS: request app activation so windows don't open behind
        if sys.platform == 'darwin':
            try:
                win.tk.call('::tk::mac::ReopenApplication')
            except Exception:
                pass
    except Exception:
        # Best effort; ignore if the platform/wm doesn't support this
        pass


def _clear_topmost_safely(win: tk.Misc):
    try:
        win.attributes('-topmost', False)
    except Exception:
        pass


def load_icon(max_size: int, *relative_parts: str) -> Optional[tk.PhotoImage]:
    """Load a PNG icon via Tk PhotoImage and scale it down if larger than max_size.

    Args:
        max_size: Maximum width/height in pixels for the returned image.
        *relative_parts: Path parts relative to the application resources.

    Returns:
        A PhotoImage instance or None if the file doesn't exist or fails to load.
    """
    try:
        path = resource_path(*relative_parts)
        if not os.path.exists(path):
            return None
        img = tk.PhotoImage(file=path)
        try:
            w = int(img.width())
            h = int(img.height())
        except Exception:
            return img
        # Only subsample (integer downscale) if larger than desired size
        if max(w, h) > max_size:
            # Compute integer factor to bring max dimension <= max_size
            # Ensure factor >= 1
            factor = max(1, int((max(w, h) + max_size - 1) // max_size))
            try:
                img = img.subsample(factor, factor)
            except Exception:
                # If subsample fails, return original
                return img
        return img
    except Exception:
        return None
