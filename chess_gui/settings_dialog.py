"""Settings popup: engine strength, think time, multi-pv, behavior toggles."""

import tkinter as tk
from tkinter import filedialog, messagebox

from .engine import ELO_MAX, ELO_MIN, tier_for
from .theme import (
    ACCENT, ACCENT_HOVER, BG, BTN_BG, BTN_BORDER, BTN_HOVER, CARD_BG,
    FONT_BODY, FONT_HINT, FONT_HEADER, FONT_LABEL, FONT_LINK_SMALL,
    PANEL_BG, TEXT_DIM, TEXT_FAINT, TEXT_FG,
)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, engine, settings, on_change=None):
        """settings: dict with keys move_auto, click_to_move (mutable, updated in place)
           on_change(key, value) called when a setting changes."""
        super().__init__(parent)
        self.engine = engine
        self.settings = settings
        self.on_change = on_change
        self.title("Engine Settings")
        self.configure(bg=PANEL_BG, padx=22, pady=18)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._section("Engine strength")
        self.elo_var = tk.IntVar(value=engine.elo)
        self._slider(self.elo_var, ELO_MIN, ELO_MAX, 10, self._on_elo)
        self.elo_label = tk.Label(self, bg=PANEL_BG, fg=TEXT_DIM, font=FONT_BODY)
        self.elo_label.pack(anchor="w", pady=(2, 4))
        self._on_elo(self.elo_var.get())
        self._hint("Lower ELO makes Stockfish play weaker. Slide to the right for full strength.")

        self._section("Think time")
        self.time_var = tk.IntVar(value=engine.move_time_ms)
        self._slider(self.time_var, 100, 5000, 100, self._on_time)
        self.time_label = tk.Label(self, bg=PANEL_BG, fg=TEXT_DIM, font=FONT_BODY)
        self.time_label.pack(anchor="w", pady=(2, 4))
        self._on_time(self.time_var.get())
        self._hint(
            "Engines calculate by searching ahead several moves \"deep\" to figure out "
            "which move yields the strongest position. The more time the engine has to "
            "calculate, the deeper it can search, and the more likely it is to find a "
            "stronger move."
        )

        self._section("Multi-PV")
        self.mpv_var = tk.IntVar(value=engine.multi_pv)
        self._slider(self.mpv_var, 1, 4, 1, self._on_mpv)
        self.mpv_label = tk.Label(self, bg=PANEL_BG, fg=TEXT_DIM, font=FONT_BODY)
        self.mpv_label.pack(anchor="w", pady=(2, 4))
        self._on_mpv(self.mpv_var.get())
        self._hint(
            "Multi-PV (\"principal variation\") instructs the engine to return up to "
            "four moves corresponding to the 1st, 2nd, 3rd, and 4th best moves it can "
            "find. This is great for finding alternate moves, but it comes at the cost "
            "of slowing the engine's depth progression."
        )

        self._divider()

        self.san_var = tk.BooleanVar(value=engine.use_san)
        self._check("Use SAN notation", self.san_var, self._on_san)
        self._hint("Display moves using standard algebraic notation: e.g., Nf3 instead of g1f3.")

        self.auto_var = tk.BooleanVar(value=settings.get("move_auto", False))
        self._check("Move automatically", self.auto_var, self._on_auto)
        self._hint("Automatically execute the suggested move after calculating.")

        self.click_var = tk.BooleanVar(value=settings.get("click_to_move", False))
        self._check("Click to move", self.click_var, self._on_click_mode)
        self._hint(
            "Click to move pieces instead of dragging. Double-click a piece to remove it. "
            "Only legal moves are allowed."
        )

        self.human_var = tk.BooleanVar(value=engine.human_mode)
        self._check("Human mode", self.human_var, self._on_human)
        self._hint(
            "Off: plays the strongest move every time. On: varies between top moves so it "
            "doesn't feel like a robot."
        )

        # Syzygy tablebases (toggle + folder picker)
        syz_row = tk.Frame(self, bg=PANEL_BG)
        syz_row.pack(anchor="w", fill="x", pady=(2, 0))
        self.syz_var = tk.BooleanVar(value=bool(engine.syzygy_path))
        tk.Checkbutton(
            syz_row, text="Syzygy tablebases", variable=self.syz_var,
            command=self._on_syzygy, bg=PANEL_BG, fg=TEXT_FG,
            activebackground=PANEL_BG, activeforeground=TEXT_FG,
            selectcolor=CARD_BG, font=FONT_LABEL, anchor="w",
            borderwidth=0, highlightthickness=0, cursor="hand2",
        ).pack(side="left")
        self.syz_browse = tk.Label(
            syz_row, text="Choose folder…", bg=PANEL_BG, fg=ACCENT,
            font=FONT_LINK_SMALL, cursor="hand2",
        )
        self.syz_browse.pack(side="left", padx=(10, 0))
        self.syz_browse.bind("<Button-1>", lambda _e: self._pick_syzygy_folder())
        self.syz_browse.bind("<Enter>", lambda _e: self.syz_browse.configure(fg=ACCENT_HOVER))
        self.syz_browse.bind("<Leave>", lambda _e: self.syz_browse.configure(fg=ACCENT))
        self.syz_path_lbl = tk.Label(
            self, text="", bg=PANEL_BG, fg=TEXT_DIM, font=FONT_BODY,
            anchor="w", wraplength=380, justify="left",
        )
        self.syz_path_lbl.pack(anchor="w")
        self._update_syz_path_label()
        self._hint(
            "Syzygy tablebases contain huge amounts of precomputed data which strengthens "
            "the engine and allows it to achieve perfect play with 6 or fewer pieces on the "
            "board."
        )

        # Close button
        btn_wrap = tk.Frame(self, bg=BTN_BORDER, padx=1, pady=1)
        tk.Button(
            btn_wrap, text="Close", command=self._close, bg=BTN_BG, fg=TEXT_FG,
            relief="flat", font=FONT_LABEL, padx=20, pady=6, borderwidth=0,
            activebackground=BTN_HOVER, activeforeground=TEXT_FG, cursor="hand2",
        ).pack()
        btn_wrap.pack(anchor="e", pady=(14, 0))

        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())

    # ---------------- widgets ----------------

    def _section(self, text):
        tk.Label(self, text=text, bg=PANEL_BG, fg=TEXT_FG,
                 font=FONT_HEADER, anchor="w").pack(anchor="w", pady=(0, 6))

    def _hint(self, text, pad_top=0):
        tk.Label(
            self, text=text, bg=PANEL_BG, fg=TEXT_FAINT, font=FONT_HINT,
            anchor="w", wraplength=380, justify="left",
        ).pack(anchor="w", pady=(pad_top, 14))

    def _slider(self, var, lo, hi, resolution, cmd):
        tk.Scale(
            self, from_=lo, to=hi, orient="horizontal", variable=var,
            resolution=resolution, length=380,
            bg=ACCENT, fg=TEXT_FG, troughcolor="#3A3A3A",
            highlightthickness=0, sliderrelief="raised",
            sliderlength=26, width=14, showvalue=0, borderwidth=0,
            command=cmd,
        ).pack(fill="x")

    def _check(self, label, var, cmd):
        cb = tk.Checkbutton(
            self, text=label, variable=var, command=cmd,
            bg=PANEL_BG, fg=TEXT_FG, activebackground=PANEL_BG,
            activeforeground=TEXT_FG, selectcolor=CARD_BG,
            font=FONT_LABEL, anchor="w", borderwidth=0, highlightthickness=0,
            cursor="hand2",
        )
        cb.pack(anchor="w", pady=(2, 0))

    def _divider(self):
        tk.Frame(self, bg="#2A2A2A", height=1).pack(fill="x", pady=(2, 14))

    # ---------------- handlers ----------------

    def _on_elo(self, _val):
        elo = int(self.elo_var.get())
        self.engine.set_elo(elo)
        self.elo_label.config(
            text="Maximum strength" if elo >= ELO_MAX
            else f"{elo} ELO · {tier_for(elo)}"
        )
        self._notify("elo", elo)

    def _on_time(self, _val):
        ms = int(self.time_var.get())
        self.engine.set_move_time(ms)
        self.time_label.config(text=f"{ms / 1000:.1f} seconds")
        self._notify("move_time_ms", ms)

    def _on_mpv(self, _val):
        n = int(self.mpv_var.get())
        self.engine.set_multi_pv(n)
        self.mpv_label.config(text=f"{n} line{'s' if n != 1 else ''}")
        self._notify("multi_pv", n)

    def _on_san(self):
        v = bool(self.san_var.get())
        self.engine.set_use_san(v)
        self._notify("use_san", v)

    def _on_auto(self):
        v = bool(self.auto_var.get())
        self.settings["move_auto"] = v
        self._notify("move_auto", v)

    def _on_click_mode(self):
        v = bool(self.click_var.get())
        self.settings["click_to_move"] = v
        self._notify("click_to_move", v)

    def _on_human(self):
        v = bool(self.human_var.get())
        self.engine.set_human_mode(v)
        self._notify("human_mode", v)

    def _on_syzygy(self):
        if self.syz_var.get():
            if not self.engine.syzygy_path:
                if not self._pick_syzygy_folder():
                    self.syz_var.set(False)
                    return
        else:
            self.engine.set_syzygy_path("")
            self._update_syz_path_label()
            self._notify("syzygy_path", "")

    def _pick_syzygy_folder(self):
        path = filedialog.askdirectory(
            title="Select Syzygy tablebase folder",
            parent=self,
        )
        if not path:
            return False
        self.engine.set_syzygy_path(path)
        self.syz_var.set(True)
        self._update_syz_path_label()
        self._notify("syzygy_path", path)
        return True

    def _update_syz_path_label(self):
        path = self.engine.syzygy_path
        if path:
            display = path if len(path) <= 60 else "…" + path[-58:]
            self.syz_path_lbl.config(text=display)
        else:
            self.syz_path_lbl.config(text="No folder selected")

    def _notify(self, key, value):
        if self.on_change:
            self.on_change(key, value)

    def _close(self):
        self.destroy()
