"""Bottom FEN bar: 'FEN [pencil] <fen string>' with click-to-edit."""

import tkinter as tk
from tkinter import simpledialog

import chess

from .theme import ACCENT, ACCENT_HOVER, BG, FONT_HEADER, FONT_MONO, TEXT_FG


class FenBar:
    def __init__(self, parent, on_fen_change=None):
        self.on_fen_change = on_fen_change
        self.frame = tk.Frame(parent, bg=BG)
        tk.Label(
            self.frame, text="FEN", bg=BG, fg=TEXT_FG, font=FONT_HEADER,
        ).pack(side="left", padx=(0, 6))
        pencil = tk.Label(
            self.frame, text="✎", bg=BG, fg=ACCENT, font=FONT_HEADER,
            cursor="hand2",
        )
        pencil.pack(side="left", padx=(0, 8))
        pencil.bind("<Button-1>", lambda _e: self._edit())
        pencil.bind("<Enter>", lambda _e: pencil.configure(fg=ACCENT_HOVER))
        pencil.bind("<Leave>", lambda _e: pencil.configure(fg=ACCENT))

        self.fen_var = tk.StringVar(value=chess.STARTING_FEN)
        self.label = tk.Label(
            self.frame, textvariable=self.fen_var, bg=BG, fg=ACCENT,
            font=FONT_MONO, anchor="w", cursor="hand2",
        )
        self.label.pack(side="left", fill="x", expand=True)
        self.label.bind("<Button-1>", lambda _e: self._edit())

    def pack(self, **kw):
        self.frame.pack(**kw)

    def set_fen(self, fen):
        self.fen_var.set(fen)

    def _edit(self):
        current = self.fen_var.get()
        new = simpledialog.askstring(
            "Edit FEN", "Enter a FEN position:",
            initialvalue=current, parent=self.frame.winfo_toplevel(),
        )
        if not new:
            return
        new = new.strip()
        try:
            chess.Board(new)
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror("Invalid FEN", str(e), parent=self.frame.winfo_toplevel())
            return
        if self.on_fen_change:
            self.on_fen_change(new)
