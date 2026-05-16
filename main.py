"""Stockfish Chess: entry point.

First-run flow:
  1. Set Windows DPI awareness (so the UI doesn't render blurry on HiDPI).
  2. Try to find a Stockfish binary in ./stockfish/.
  3. If none found, show the install dialog. User picks a build, we download
     it from the official Stockfish releases on GitHub.
  4. Launch the main chess GUI.
"""

import sys
import tkinter as tk
from pathlib import Path

# DPI awareness MUST happen before tk.Tk() is created.
if sys.platform == "win32":
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from chess_gui.app import ChessApp
from chess_gui.engine import discover_engines
from chess_gui.install_dialog import InstallDialog
from chess_gui.theme import ENGINE_PATH


def _engine_folder():
    return Path(ENGINE_PATH).parent


def _ensure_engine(root):
    """Return True if a Stockfish engine is available. May prompt the user."""
    if discover_engines(_engine_folder()):
        return True

    # No engine found, show the install dialog
    installed = {"path": None}

    def on_done(path):
        installed["path"] = path

    dlg = InstallDialog(root, _engine_folder(), on_done, first_run=True)
    root.wait_window(dlg)
    return installed["path"] is not None or bool(discover_engines(_engine_folder()))


def main():
    root = tk.Tk()
    root.title("Stockfish Chess")
    # If we already have an engine, hide root immediately and go straight to
    # the main UI. Otherwise leave it visible so the install dialog has a
    # parent the user can actually see + interact with.
    if discover_engines(_engine_folder()):
        root.withdraw()
    else:
        # Give root a sensible position/size so the install dialog has
        # something to anchor onto.
        root.geometry("600x400+200+200")
        root.configure(bg="#1A1A1A")
        if not _ensure_engine(root):
            root.destroy()
            sys.exit(0)
        root.withdraw()

    root.deiconify()
    app = ChessApp(root)
    root.protocol("WM_DELETE_WINDOW", app.quit)
    root.mainloop()


if __name__ == "__main__":
    main()
