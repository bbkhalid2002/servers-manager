#!/usr/bin/env python3
"""
Secure SSH Server Manager
A cross-platform GUI application for managing SSH server connections.
"""

import sys
import tkinter as tk
from tkinter import messagebox
from utils import bring_window_to_front

# Paramiko dependency is required; it's imported in ssh_connection module.
from main_window import ServerManagerGUI

def main():
    """Main application entry point."""
    root = tk.Tk()
    # Center main window at 80% of screen size
    try:
        root.update_idletasks()
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        w = int(sw * 0.8)
        h = int(sh * 0.8)
        x = (sw - w) // 2
        y = (sh - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        root.geometry("1280x800")
    # Ensure the main window is brought to the front (esp. on macOS)
    try:
        bring_window_to_front(root)
    except Exception:
        pass
    
    def on_closing():
        if messagebox.askokcancel("Quit", "Do you want to quit?"):
            root.destroy()
    
    root.protocol("WM_DELETE_WINDOW", on_closing)
    
    try:
        ServerManagerGUI(root)
        try:
            bring_window_to_front(root)
        except Exception:
            pass
        root.mainloop()
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
        sys.exit(0)
    except Exception as e:
        messagebox.showerror("Fatal Error", f"A fatal application error occurred: {e}\n\nThe application will now close.")
        sys.exit(1)

if __name__ == "__main__":
    main()