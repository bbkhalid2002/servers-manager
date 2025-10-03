import tkinter as tk
from tkinter import ttk
from utils import bring_window_to_front
import difflib

class TextDiffWindow:
    """
    A simple two-pane text diff tool.
    - Left and right text areas
    - Typing/pasting in either pane triggers a line-based diff
    - Highlights:
        * Added lines (present in right, not in left) -> green background
        * Removed lines (present in left, not in right) -> red background
        * Changed lines (replace operations) -> mark removed in left as red and added in right as green
    """
    def __init__(self, parent: tk.Tk | tk.Toplevel):
        self.parent = parent
        self.top = tk.Toplevel(parent)
        self.top.title("Text Diff")
        self.top.transient(parent)
        self.top.grab_set()

        # Layout
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(0, weight=1)

        paned = ttk.Panedwindow(self.top, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        # Left pane
        left = ttk.Frame(paned, padding=6)
        left.columnconfigure(0, weight=1)
        # Make the text area (row=1) expand, not the header (row=0)
        left.rowconfigure(1, weight=1)
        left_header = ttk.Frame(left)
        left_header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(left_header, text="Left (base)").pack(side=tk.LEFT)
        self.left_text = tk.Text(left, wrap='none', undo=True)
        self.left_text.grid(row=1, column=0, sticky='nsew')
        self.left_text_scroll_y = ttk.Scrollbar(left, orient='vertical', command=self.left_text.yview)
        self.left_text_scroll_y.grid(row=1, column=1, sticky='ns')
        self.left_text.configure(yscrollcommand=self.left_text_scroll_y.set)
        self.left_text_scroll_x = ttk.Scrollbar(left, orient='horizontal', command=self.left_text.xview)
        self.left_text_scroll_x.grid(row=2, column=0, sticky='ew')
        self.left_text.configure(xscrollcommand=self.left_text_scroll_x.set)

        # Right pane
        right = ttk.Frame(paned, padding=6)
        right.columnconfigure(0, weight=1)
        # Make the text area (row=1) expand, not the header (row=0)
        right.rowconfigure(1, weight=1)
        right_header = ttk.Frame(right)
        right_header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(right_header, text="Right (changed)").pack(side=tk.LEFT)
        self.right_text = tk.Text(right, wrap='none', undo=True)
        self.right_text.grid(row=1, column=0, sticky='nsew')
        self.right_text_scroll_y = ttk.Scrollbar(right, orient='vertical', command=self.right_text.yview)
        self.right_text_scroll_y.grid(row=1, column=1, sticky='ns')
        self.right_text.configure(yscrollcommand=self.right_text_scroll_y.set)
        self.right_text_scroll_x = ttk.Scrollbar(right, orient='horizontal', command=self.right_text.xview)
        self.right_text_scroll_x.grid(row=2, column=0, sticky='ew')
        self.right_text.configure(xscrollcommand=self.right_text_scroll_x.set)

        paned.add(left, weight=1)
        paned.add(right, weight=1)

        # Tags for highlighting
        self.left_text.tag_configure('removed', background='#ffecec', foreground='#a40000')  # light red
        self.right_text.tag_configure('added', background='#eaffea', foreground='#006400')   # light green

        # Bind parse on changes (both panes) with debouncing
        self._after_id = None
        for widget in (self.left_text, self.right_text):
            widget.bind('<<Paste>>', self._schedule_diff)
            widget.bind('<KeyRelease>', self._schedule_diff)

        # Keep scrolls roughly in sync vertically when user scrolls
        self.left_text.bind('<MouseWheel>', self._sync_scroll)
        self.right_text.bind('<MouseWheel>', self._sync_scroll)

        # Geometry: use 60% of screen width and 50% height, center
        try:
            self.top.update_idletasks()
            sw = self.top.winfo_screenwidth()
            sh = self.top.winfo_screenheight()
            w = max(900, int(sw * 0.6))
            h = max(600, int(sh * 0.5))
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.top.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.top.geometry("1200x700")
        # Ensure on top/front, especially on macOS
        try:
            bring_window_to_front(self.top)
        except Exception:
            pass

    def _schedule_diff(self, event=None):
        if self._after_id:
            try:
                self.top.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.top.after(250, self._compute_and_highlight)

    def _compute_and_highlight(self):
        self._after_id = None
        left_lines = self.left_text.get('1.0', 'end').splitlines()
        right_lines = self.right_text.get('1.0', 'end').splitlines()

        # Clear previous tags
        try:
            self.left_text.tag_remove('removed', '1.0', 'end')
            self.right_text.tag_remove('added', '1.0', 'end')
        except Exception:
            pass

        sm = difflib.SequenceMatcher(a=left_lines, b=right_lines)
        # Track current 1-based line numbers for Text indices
        l_row = 1
        r_row = 1
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                # advance both sides
                l_row += (i2 - i1)
                r_row += (j2 - j1)
            elif tag == 'delete':
                # lines removed from left
                for _ in range(i1, i2):
                    self._mark_line(self.left_text, l_row, 'removed')
                    l_row += 1
            elif tag == 'insert':
                # lines added to right
                for _ in range(j1, j2):
                    self._mark_line(self.right_text, r_row, 'added')
                    r_row += 1
            elif tag == 'replace':
                # mark removed on left and added on right
                for _ in range(i1, i2):
                    self._mark_line(self.left_text, l_row, 'removed')
                    l_row += 1
                for _ in range(j1, j2):
                    self._mark_line(self.right_text, r_row, 'added')
                    r_row += 1

    def _mark_line(self, text_widget: tk.Text, line_number: int, tag: str):
        try:
            start = f"{line_number}.0"
            end = f"{line_number}.0 lineend"
            text_widget.tag_add(tag, start, end)
        except Exception:
            pass

    def _sync_scroll(self, event):
        # Rough sync: when one scrolls, move the other similarly
        try:
            delta = -1 if event.delta > 0 else 1
            if event.widget is self.left_text:
                self.right_text.yview_scroll(delta, 'units')
            else:
                self.left_text.yview_scroll(delta, 'units')
        except Exception:
            pass
