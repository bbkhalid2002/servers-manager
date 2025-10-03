import json
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Optional, Tuple
from utils import bring_window_to_front


class JSONViewerWindow:
    """
    Popup window that lets users paste arbitrary text on the right, extracts/cleans JSON from it,
    and renders the JSON as a tree on the left with a search field.
    """

    def __init__(self, parent: tk.Tk | tk.Toplevel):
        self.parent = parent
        self.top = tk.Toplevel(parent)
        self.top.title("JSON Viewer")
        self.top.transient(parent)
        self.top.grab_set()

        # Layout root
        self.top.columnconfigure(0, weight=1)
        self.top.rowconfigure(0, weight=1)

        paned = ttk.Panedwindow(self.top, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        # Left: search + tree
        left = ttk.Frame(paned, padding=6)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)

        search_row = ttk.Frame(left)
        search_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Label(search_row, text="Search:").pack(side=tk.LEFT)
        self._search_var = tk.StringVar()
        self._search_entry = ttk.Entry(search_row, textvariable=self._search_var)
        self._search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 6))
        self._search_entry.bind('<Return>', lambda e: self._find_next())
        ttk.Button(search_row, text="Expand All", command=self._expand_all).pack(side=tk.LEFT)
        ttk.Button(search_row, text="Collapse All", command=self._collapse_all).pack(side=tk.LEFT, padx=(6, 0))

        self.tree = ttk.Treeview(left, columns=("value",), show="tree headings")
        self.tree.heading("#0", text="Key / Index")
        self.tree.heading("value", text="Value")
        self.tree.column("#0", width=240, anchor="w")
        self.tree.column("value", width=300, anchor="w")
        tree_scroll = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.grid(row=1, column=0, sticky='nsew')
        tree_scroll.grid(row=1, column=1, sticky='ns')
        # Zebra striping for light row separation
        self.tree.tag_configure('even', background='#FFFFFF')
        self.tree.tag_configure('odd', background='#F2F2F2')

        # Right: text area to paste
        right = ttk.Frame(paned, padding=6)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        right_header = ttk.Frame(right)
        right_header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        right_header.columnconfigure(0, weight=1)
        ttk.Label(right_header, text="Paste text here (JSON will be auto-extracted):").grid(row=0, column=0, sticky="w")
        ttk.Button(right_header, text="Format JSON", command=self._format_json_in_text).grid(row=0, column=1, sticky="e")
        self.text = tk.Text(right, wrap='word', width=60)
        self.text.grid(row=1, column=0, sticky='nsew')
        text_scroll = ttk.Scrollbar(right, orient='vertical', command=self.text.yview)
        self.text.configure(yscrollcommand=text_scroll.set)
        text_scroll.grid(row=1, column=1, sticky='ns')

        # Status bar
        self.status_var = tk.StringVar(value="Paste text to parse JSON…")
        status = ttk.Label(self.top, textvariable=self.status_var, relief=tk.SUNKEN, anchor='w')
        status.grid(row=1, column=0, sticky='ew')

    # Prepare context menu early
        self._tree_menu = tk.Menu(self.top, tearoff=0)
        self._tree_menu.add_command(label="Copy Value", command=self._copy_selected_value)

        paned.add(left, weight=1)
        paned.add(right, weight=1)

        # Parse triggers
        self._parse_after_id: Optional[str] = None
        self.text.bind('<<Paste>>', self._schedule_parse)
        # Fallback: handle Ctrl+V and general typing
        self.text.bind('<Control-v>', self._schedule_parse)
        self.text.bind('<KeyRelease>', self._schedule_parse)
        # Treeview bindings for context menu and copy
        self.tree.bind('<Button-3>', self._on_tree_right_click)
        self.tree.bind('<Control-c>', self._on_ctrl_c)

        # Keep state for search
        self._last_search = ""
        self._last_found_iids: list[str] = []
        self._last_found_index = -1
        # Map tree item IDs to the underlying Python value for copy operations
        self._node_value: dict[str, Any] = {}

        # Size to one-third of the screen and center on the screen
        try:
            self.top.update_idletasks()
            sw = self.top.winfo_screenwidth()
            sh = self.top.winfo_screenheight()
            w = sw // 3
            h = sh // 3
            x = (sw - w) // 2
            y = (sh - h) // 2
            self.top.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            # Fallback if screen metrics are unavailable
            self.top.geometry("800x500")
        # Ensure on top/front, especially on macOS
        try:
            bring_window_to_front(self.top)
        except Exception:
            pass

    # ---------------- Parsing & Cleaning -----------------
    def _schedule_parse(self, event=None):
        if self._parse_after_id:
            try:
                self.top.after_cancel(self._parse_after_id)
            except Exception:
                pass
        # Debounce parse to avoid excessive work while typing/pasting
        self._parse_after_id = self.top.after(400, self._parse_and_render)

    def _parse_and_render(self):
        self._parse_after_id = None
        raw = self.text.get('1.0', 'end').strip()
        if not raw:
            self._set_status("Paste text to parse JSON…")
            self._clear_tree()
            return
        cleaned_str, data, error = self._extract_and_load_json(raw)
        if error:
            self._set_status(f"Parse failed: {error}")
            self._clear_tree()
            return
        self._set_status("Parsed JSON successfully")
        self._populate_tree(data)

    def _extract_and_load_json(self, text: str) -> Tuple[str, Optional[Any], Optional[str]]:
        # Try to locate the first valid JSON object or array in the text
        cand = self._extract_json_block(text)
        if cand is None:
            return text, None, "No JSON object/array found"

        # Try direct parse
        for s in self._candidate_variants(cand):
            try:
                data = json.loads(s)
                return s, data, None
            except Exception:
                continue

        # If still failing, try aggressive unescape pass
        try:
            s2 = cand
            # If quoted JSON string (e.g., "{\"a\":1}")
            if s2.startswith('"') and s2.endswith('"'):
                s2 = json.loads(s2)  # unescape via json
            # Replace escaped backslashes first, then try loads again
            s3 = s2.encode('utf-8').decode('unicode_escape')
            data = json.loads(s3)
            return s3, data, None
        except Exception as e:
            return cand, None, str(e)

    def _extract_json_block(self, text: str) -> Optional[str]:
        # Scan for object or array block and return the first valid complete block
        obj = self._scan_for_balanced_block(text, '{', '}')
        arr = self._scan_for_balanced_block(text, '[', ']')
        if obj is None and arr is None:
            return None
        if obj is None:
            return arr
        if arr is None:
            return obj
        # Prefer the earliest occurrence
        oidx = text.find(obj)
        aidx = text.find(arr)
        return obj if (oidx >= 0 and (aidx < 0 or oidx < aidx)) else arr

    def _scan_for_balanced_block(self, text: str, open_ch: str, close_ch: str) -> Optional[str]:
        i = 0
        n = len(text)
        while i < n:
            if text[i] == open_ch:
                end = self._find_matching(text, i, open_ch, close_ch)
                if end is not None:
                    return text[i:end + 1]
            i += 1
        return None

    def _find_matching(self, s: str, start: int, open_ch: str, close_ch: str) -> Optional[int]:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(s)):
            ch = s[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == '\\':
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            else:
                if ch == '"':
                    in_str = True
                    continue
                if ch == open_ch:
                    depth += 1
                elif ch == close_ch:
                    depth -= 1
                    if depth == 0:
                        return i
        return None

    def _candidate_variants(self, s: str):
        # Try the string as-is
        yield s
        # If it looks like a quoted JSON string, unescape via json to inner value
        if s.startswith('"') and s.endswith('"'):
            try:
                inner = json.loads(s)
                yield inner
            except Exception:
                pass
        # Try with backslashes collapsed (helpful for double-escaped content)
        try:
            yield s.replace('\\\\', '\\')
        except Exception:
            pass

    # ---------------- Tree Rendering -----------------
    def _clear_tree(self):
        try:
            self.tree.delete(*self.tree.get_children())
        except Exception:
            pass

    def _populate_tree(self, data: Any):
        self._clear_tree()
        # Reset zebra index counter
        self._row_index = 0
        self._insert_node('', 'root', data)
        # Expand the top-level node for visibility
        try:
            first = self.tree.get_children('')
            if first:
                self.tree.item(first[0], open=True)
        except Exception:
            pass

    def _insert_node(self, parent: str, key: str, value: Any):
        # Determine how to display
        if isinstance(value, dict):
            tag = 'even' if (getattr(self, '_row_index', 0) % 2 == 0) else 'odd'
            node = self.tree.insert(parent, 'end', text=str(key), values=("{…}",), tags=(tag,))
            self._row_index = getattr(self, '_row_index', 0) + 1
            self._node_value[node] = value
            for k, v in value.items():
                self._insert_node(node, str(k), v)
        elif isinstance(value, list):
            tag = 'even' if (getattr(self, '_row_index', 0) % 2 == 0) else 'odd'
            node = self.tree.insert(parent, 'end', text=str(key), values=("[ … ]",), tags=(tag,))
            self._row_index = getattr(self, '_row_index', 0) + 1
            self._node_value[node] = value
            for idx, item in enumerate(value):
                self._insert_node(node, f"[{idx}]", item)
        else:
            # Primitive
            disp = self._primitive_to_str(value)
            tag = 'even' if (getattr(self, '_row_index', 0) % 2 == 0) else 'odd'
            node = self.tree.insert(parent, 'end', text=str(key), values=(disp,), tags=(tag,))
            self._row_index = getattr(self, '_row_index', 0) + 1
            self._node_value[node] = value

    def _primitive_to_str(self, v: Any) -> str:
        try:
            if isinstance(v, str):
                return v
            return json.dumps(v, ensure_ascii=False)
        except Exception:
            return str(v)

    def _format_json_in_text(self):
        raw = self.text.get('1.0', 'end').strip()
        if not raw:
            messagebox.showerror("Format JSON", "The provided JSON is invalid or empty.")
            return
        cleaned, data, error = self._extract_and_load_json(raw)
        if error or data is None:
            messagebox.showerror("Format JSON", "The provided JSON is invalid.")
            return
        try:
            pretty = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            messagebox.showerror("Format JSON", "The provided JSON is invalid.")
            return
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', pretty)
        self._set_status("Formatted JSON")
        self._populate_tree(data)

    # ---------------- Search -----------------
    def _find_next(self):
        query = (self._search_var.get() or '').strip().lower()
        if not query:
            return
        # Build list of matching node ids if query changed
        if query != self._last_search:
            self._last_search = query
            self._last_found_iids = self._collect_matches(query)
            self._last_found_index = -1
        if not self._last_found_iids:
            self._set_status("No matches")
            return
        self._last_found_index = (self._last_found_index + 1) % len(self._last_found_iids)
        iid = self._last_found_iids[self._last_found_index]
        try:
            # Expand ancestors
            self._expand_to(iid)
            self.tree.selection_set(iid)
            self.tree.focus(iid)
            self.tree.see(iid)
            self._set_status(f"Match {self._last_found_index + 1}/{len(self._last_found_iids)}")
        except Exception:
            pass

    def _collect_matches(self, query: str) -> list[str]:
        matches: list[str] = []
        def visit(iid: str):
            try:
                text = (self.tree.item(iid).get('text') or '').lower()
                vals = self.tree.item(iid).get('values') or []
                val = (str(vals[0]) if vals else '').lower()
                if query in text or query in val:
                    matches.append(iid)
                for child in self.tree.get_children(iid):
                    visit(child)
            except Exception:
                pass
        for root_iid in self.tree.get_children(''):
            visit(root_iid)
        return matches

    def _expand_to(self, iid: str):
        # Expand ancestor nodes to reveal iid
        try:
            parent = self.tree.parent(iid)
            while parent:
                self.tree.item(parent, open=True)
                parent = self.tree.parent(parent)
        except Exception:
            pass

    # ---------------- Expand / Collapse All -----------------
    def _expand_all(self):
        try:
            for root_iid in self.tree.get_children(''):
                self._set_open_recursive(root_iid, True)
            self._set_status("Expanded all")
        except Exception:
            pass

    def _collapse_all(self):
        try:
            for root_iid in self.tree.get_children(''):
                self._set_open_recursive(root_iid, False)
            self._set_status("Collapsed all")
        except Exception:
            pass

    def _set_open_recursive(self, iid: str, open_flag: bool):
        try:
            self.tree.item(iid, open=open_flag)
            for child in self.tree.get_children(iid):
                self._set_open_recursive(child, open_flag)
        except Exception:
            pass

    # ---------------- Copy Value -----------------
    def _on_tree_right_click(self, event):
        try:
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
                try:
                    self._tree_menu.tk_popup(event.x_root, event.y_root)
                finally:
                    self._tree_menu.grab_release()
        except Exception:
            pass

    def _on_ctrl_c(self, event):
        self._copy_selected_value()
        return 'break'

    def _copy_selected_value(self):
        try:
            sel = self.tree.selection()
            if not sel:
                return
            iid = sel[0]
            value = self._node_value.get(iid, None)
            if value is None:
                # Fallback to displayed value text
                vals = self.tree.item(iid).get('values') or []
                text = str(vals[0]) if vals else ''
            else:
                # Containers pretty-printed; primitives raw or JSON-encoded
                if isinstance(value, (dict, list)):
                    text = json.dumps(value, ensure_ascii=False, indent=2)
                elif isinstance(value, str):
                    text = value
                else:
                    text = json.dumps(value, ensure_ascii=False)
            self.top.clipboard_clear()
            self.top.clipboard_append(text)
            self._set_status("Copied value to clipboard")
        except Exception:
            pass

    # ---------------- Utils -----------------
    def _set_status(self, msg: str):
        try:
            self.status_var.set(msg)
        except Exception:
            pass
