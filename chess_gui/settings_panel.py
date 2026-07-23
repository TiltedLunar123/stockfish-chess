"""Inline settings panel: replaces sidebar contents when gear is clicked.

When the panel is shown the board column is hidden, so this panel uses the
full window width. Layout is 2-column (sections side by side) to take
advantage of the horizontal space and minimise scrolling.
"""

import os
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .engine import ELO_MAX, ELO_MIN, discover_engines, tier_for
from .theme import (
    ACCENT, ACCENT_HOVER, BG, BTN_BG, BTN_BORDER, BTN_HOVER, CARD_BG,
    DIVIDER, FONT_BODY, FONT_HEADER, FONT_HINT, FONT_LABEL, FONT_LINK_SMALL,
    PANEL_BG, SIDEBAR_WIDTH, TEXT_DIM, TEXT_FAINT, TEXT_FG,
)

STOCKFISH_DOWNLOAD_URL = "https://stockfishchess.org/download/"
SYZYGY_DOWNLOAD_URL = "https://syzygy-tables.info/"

MAX_PANEL_WIDTH = 880
COL_GUTTER = 28
SIDE_PADDING = 24


class SettingsPanel:
    """Two-column inline settings panel."""

    def __init__(self, parent, engine, settings, on_close,
                 on_change=None, on_engine_changed=None):
        self.engine = engine
        self.settings = settings
        self.on_close = on_close
        self.on_change = on_change
        self.on_engine_changed = on_engine_changed
        self._hint_labels = []  # tracked for wraplength updates
        self.frame = tk.Frame(parent, bg=PANEL_BG)

        # Scrollable area
        self.canvas = tk.Canvas(self.frame, bg=PANEL_BG, highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(
            self.frame, orient="vertical", command=self.canvas.yview,
            bg=PANEL_BG, troughcolor=BG, borderwidth=0,
            activebackground=ACCENT, width=10,
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=PANEL_BG)
        self._inner_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw",
        )
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self._build()
        self._bind_wheel_recursive(self.inner)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)

    def pack(self, **kw):
        self.frame.pack(**kw)

    def destroy(self):
        self.frame.destroy()

    # ---------------- scrolling / resize ----------------

    def _on_inner_configure(self, _e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        usable = min(e.width, MAX_PANEL_WIDTH)
        # Center the inner frame within the canvas if the window is wider
        # than MAX_PANEL_WIDTH so the content doesn't sprawl.
        x_off = max(0, (e.width - usable) // 2)
        self.canvas.coords(self._inner_id, x_off, 0)
        self.canvas.itemconfig(self._inner_id, width=usable)
        # Re-flow hint wraplengths based on actual column width
        col_w = max(180, (usable - 2 * SIDE_PADDING - COL_GUTTER) // 2)
        for lbl in self._hint_labels:
            lbl.configure(wraplength=col_w)

    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        return "break"

    def _bind_wheel_recursive(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)

    # ---------------- content ----------------

    def _build(self):
        # Top bar: back link on the left, "Settings" title on the right
        top = tk.Frame(self.inner, bg=PANEL_BG)
        top.pack(anchor="w", fill="x",
                 padx=SIDE_PADDING, pady=(SIDE_PADDING, 10))

        back = tk.Label(
            top, text="←  Back", bg=PANEL_BG, fg=ACCENT,
            font=FONT_LINK_SMALL, cursor="hand2", anchor="w",
        )
        back.pack(side="left")
        back.bind("<Button-1>", lambda _e: self.on_close())
        back.bind("<Enter>", lambda _e: back.configure(fg=ACCENT_HOVER))
        back.bind("<Leave>", lambda _e: back.configure(fg=ACCENT))

        tk.Label(top, text="Settings", bg=PANEL_BG, fg=TEXT_FG,
                 font=(FONT_HEADER[0], 14, "bold")).pack(side="right")

        tk.Frame(self.inner, bg=DIVIDER, height=1).pack(
            fill="x", padx=SIDE_PADDING, pady=(0, 16),
        )

        # 2-column body
        body = tk.Frame(self.inner, bg=PANEL_BG)
        body.pack(anchor="nw", fill="both", expand=True,
                  padx=SIDE_PADDING, pady=(0, SIDE_PADDING))
        body.grid_columnconfigure(0, weight=1, uniform="col")
        body.grid_columnconfigure(1, weight=1, uniform="col")

        left = tk.Frame(body, bg=PANEL_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, COL_GUTTER // 2))
        right = tk.Frame(body, bg=PANEL_BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(COL_GUTTER // 2, 0))

        # LEFT column
        self._build_engine_section(left)
        self._build_strength_section(left)
        self._build_time_section(left)

        # RIGHT column
        self._build_mpv_section(right)
        self._build_style_section(right)
        self._build_toggles_section(right)
        self._build_syzygy_section(right)

    # ---------------- sections ----------------

    def _build_engine_section(self, parent):
        self._section(parent, "Engine")
        engines = discover_engines()
        self._engine_paths = {self._short_engine_name(p): p for _, p in engines}
        names = list(self._engine_paths.keys()) or ["(none found)"]
        current = next(
            (n for n, p in self._engine_paths.items()
             if os.path.abspath(p) == os.path.abspath(self.engine.path)),
            names[0],
        )
        self.engine_var = tk.StringVar(value=current)
        self.engine_combo = ttk.Combobox(
            parent, textvariable=self.engine_var, values=names,
            state="readonly", font=FONT_BODY,
        )
        self.engine_combo.pack(fill="x")
        self.engine_combo.bind("<<ComboboxSelected>>", self._on_engine_select)

        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(anchor="w", fill="x", pady=(8, 0))
        self._link(row, "Install", self._install_engine).pack(side="left", padx=(0, 16))
        self._link(row, "Uninstall", self._uninstall_engine,
                   color="#E07070", hover="#F38888").pack(side="left")
        self._hint(parent,
                   "Install opens the Stockfish download page in your browser. "
                   "Drop the binary into the stockfish folder and it shows up "
                   "in the dropdown.")
        self._spacer(parent)

    def _build_strength_section(self, parent):
        self._section(parent, "Engine strength")
        self.elo_var = tk.IntVar(value=self.engine.elo)
        self._slider(parent, self.elo_var, ELO_MIN, ELO_MAX, 10, self._on_elo)
        self.elo_label = tk.Label(parent, bg=PANEL_BG, fg=TEXT_DIM,
                                  font=FONT_BODY, anchor="w")
        self.elo_label.pack(anchor="w", pady=(4, 0))
        self._on_elo(self.elo_var.get())
        self._hint(parent, "Lower ELO makes Stockfish play weaker.")
        self._spacer(parent)

    def _build_time_section(self, parent):
        self._section(parent, "Think time")
        seconds = self.engine.move_time_ms / 1000
        self.time_secs_var = tk.DoubleVar(value=seconds)

        slider = tk.Scale(
            parent, from_=0.1, to=5.0, orient="horizontal",
            variable=self.time_secs_var, resolution=0.1,
            bg=ACCENT, fg=TEXT_FG, troughcolor="#3A3A3A",
            highlightthickness=0, sliderrelief="raised",
            sliderlength=26, width=14, showvalue=0, borderwidth=0,
            command=self._on_time_slider,
        )
        slider.pack(fill="x")

        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(anchor="w", pady=(6, 0))
        self.time_spin = tk.Spinbox(
            row, from_=0.1, to=60.0, increment=0.1, format="%.1f",
            textvariable=self.time_secs_var, width=6,
            bg=CARD_BG, fg=TEXT_FG, insertbackground=TEXT_FG,
            buttonbackground=CARD_BG, readonlybackground=CARD_BG,
            highlightthickness=0, relief="flat", borderwidth=2,
            font=FONT_BODY, command=self._on_time_spin,
        )
        self.time_spin.pack(side="left")
        self.time_spin.bind("<Return>", lambda _e: self._on_time_spin())
        self.time_spin.bind("<FocusOut>", lambda _e: self._on_time_spin())
        tk.Label(row, text="seconds", bg=PANEL_BG,
                 fg=TEXT_DIM, font=FONT_BODY).pack(side="left", padx=(10, 0))
        self._hint(parent,
                   "Slider for 0.1–5s, or click the number to type any value "
                   "(up to 60). More time = deeper search = stronger play.")

    def _build_mpv_section(self, parent):
        self._section(parent, "Multi-PV")
        self.mpv_var = tk.IntVar(value=self.engine.multi_pv)
        self._slider(parent, self.mpv_var, 1, 4, 1, self._on_mpv)
        self.mpv_label = tk.Label(parent, bg=PANEL_BG, fg=TEXT_DIM,
                                  font=FONT_BODY, anchor="w")
        self.mpv_label.pack(anchor="w", pady=(4, 0))
        self._on_mpv(self.mpv_var.get())
        self._hint(parent,
                   "Show the top 1–4 candidate moves. Higher values slow "
                   "the engine's depth progression.")
        self._spacer(parent)

    def _build_style_section(self, parent):
        self._section(parent, "Play style")
        self.style_var = tk.StringVar(value=self.engine.play_style)
        for label, value in [
            ("Aggressive", "aggressive"),
            ("Balanced", "balanced"),
            ("Defensive", "defensive"),
        ]:
            tk.Radiobutton(
                parent, text=label, variable=self.style_var, value=value,
                command=self._on_style,
                bg=PANEL_BG, fg=TEXT_FG, activebackground=PANEL_BG,
                activeforeground=TEXT_FG, selectcolor=CARD_BG,
                font=FONT_LABEL, anchor="w", borderwidth=0,
                highlightthickness=0, cursor="hand2", pady=2,
            ).pack(anchor="w", pady=(2, 0))
        self._hint(parent,
                   "Aggressive favors captures and checks. Defensive prefers "
                   "quiet moves and castling. Balanced just plays the top "
                   "engine move. Style only kicks in for moves within ~0.8 "
                   "of the best evaluation, so it never gives up real points.")
        self._spacer(parent)

    def _build_toggles_section(self, parent):
        self._section(parent, "Options")
        self.san_var = tk.BooleanVar(value=self.engine.use_san)
        self._check(parent, "Use SAN notation", self.san_var, self._on_san)
        self._hint(parent, "Display moves as Nf3 instead of g1f3.")

        self.auto_var = tk.BooleanVar(value=self.settings.get("move_auto", False))
        self._check(parent, "Move automatically", self.auto_var, self._on_auto)
        self._hint(parent, "Auto-play the suggested move after calculating.")

        self.click_var = tk.BooleanVar(value=self.settings.get("click_to_move", False))
        self._check(parent, "Click to move", self.click_var, self._on_click_mode)
        self._hint(parent,
                   "Click to move pieces instead of dragging. Right-click "
                   "removes a piece.")

        self.human_var = tk.BooleanVar(value=self.engine.human_mode)
        self._check(parent, "Human mode", self.human_var, self._on_human)
        self._hint(parent,
                   "Varies between top moves so it doesn't feel like a robot.")
        self._spacer(parent)

    def _build_syzygy_section(self, parent):
        self._section(parent, "Syzygy tablebases")
        self.syz_var = tk.BooleanVar(value=bool(self.engine.syzygy_path))
        tk.Checkbutton(
            parent, text="Enabled", variable=self.syz_var,
            command=self._on_syzygy, bg=PANEL_BG, fg=TEXT_FG,
            activebackground=PANEL_BG, activeforeground=TEXT_FG,
            selectcolor=CARD_BG, font=FONT_LABEL, anchor="w",
            borderwidth=0, highlightthickness=0, cursor="hand2",
        ).pack(anchor="w")
        self.syz_path_lbl = tk.Label(
            parent, text="", bg=PANEL_BG, fg=TEXT_DIM, font=FONT_BODY,
            anchor="w", justify="left",
        )
        self.syz_path_lbl.pack(anchor="w", pady=(2, 6), fill="x")
        self._update_syz_path_label()

        row = tk.Frame(parent, bg=PANEL_BG)
        row.pack(anchor="w", fill="x")
        self._link(row, "Install", self._install_syzygy).pack(side="left", padx=(0, 14))
        self._link(row, "Choose folder", self._pick_syzygy_folder).pack(side="left", padx=(0, 14))
        self._link(row, "Uninstall", self._uninstall_syzygy,
                   color="#E07070", hover="#F38888").pack(side="left")
        self._hint(parent,
                   "Perfect play with 6 or fewer pieces on the board. Install "
                   "opens the download page; Choose folder points at "
                   ".rtbw/.rtbz files.")

    # ---------------- widget helpers ----------------

    def _section(self, parent, text):
        tk.Label(parent, text=text.upper(), bg=PANEL_BG, fg=TEXT_DIM,
                 font=(FONT_HEADER[0], 9, "bold"), anchor="w"
                 ).pack(anchor="w", pady=(0, 6))

    def _hint(self, parent, text):
        lbl = tk.Label(
            parent, text=text, bg=PANEL_BG, fg=TEXT_FAINT, font=FONT_HINT,
            anchor="w", wraplength=300, justify="left",
        )
        lbl.pack(anchor="w", pady=(4, 0), fill="x")
        self._hint_labels.append(lbl)

    def _spacer(self, parent, height=18):
        tk.Frame(parent, bg=PANEL_BG, height=height).pack(fill="x")

    def _slider(self, parent, var, lo, hi, resolution, cmd):
        tk.Scale(
            parent, from_=lo, to=hi, orient="horizontal", variable=var,
            resolution=resolution,
            bg=ACCENT, fg=TEXT_FG, troughcolor="#3A3A3A",
            highlightthickness=0, sliderrelief="raised",
            sliderlength=26, width=14, showvalue=0, borderwidth=0,
            command=cmd,
        ).pack(fill="x")

    def _check(self, parent, label, var, cmd):
        tk.Checkbutton(
            parent, text=label, variable=var, command=cmd,
            bg=PANEL_BG, fg=TEXT_FG, activebackground=PANEL_BG,
            activeforeground=TEXT_FG, selectcolor=CARD_BG,
            font=FONT_LABEL, anchor="w", borderwidth=0, highlightthickness=0,
            cursor="hand2", pady=2,
        ).pack(anchor="w", pady=(6, 0))

    def _link(self, parent, text, cmd, color=ACCENT, hover=ACCENT_HOVER):
        lbl = tk.Label(parent, text=text, bg=PANEL_BG, fg=color,
                       font=FONT_LINK_SMALL, cursor="hand2")
        lbl.bind("<Button-1>", lambda _e: cmd())
        lbl.bind("<Enter>", lambda _e: lbl.configure(fg=hover))
        lbl.bind("<Leave>", lambda _e: lbl.configure(fg=color))
        return lbl

    def _short_engine_name(self, path):
        name = Path(path).stem
        # "ubuntu" is what installer.detect_os() returns for Linux, so that's
        # the prefix the release assets actually carry.
        for prefix in ("stockfish-windows-", "stockfish-macos-",
                       "stockfish-ubuntu-", "stockfish-linux-", "stockfish-"):
            if name.startswith(prefix):
                return name[len(prefix):]
        return name

    # ---------------- handlers ----------------

    def _on_elo(self, _val):
        elo = int(self.elo_var.get())
        self.engine.set_elo(elo)
        self.elo_label.config(
            text="Maximum strength" if elo >= ELO_MAX
            else f"{elo} ELO · {tier_for(elo)}"
        )
        self._notify("elo", elo)

    def _on_time_slider(self, _val):
        secs = float(self.time_secs_var.get())
        ms = int(secs * 1000)
        self.engine.set_move_time(ms)
        self._notify("move_time_ms", ms)

    def _on_time_spin(self):
        try:
            secs = float(self.time_secs_var.get())
        except (tk.TclError, ValueError):
            return
        secs = max(0.1, min(60.0, secs))
        if self.time_secs_var.get() != secs:
            self.time_secs_var.set(secs)
        ms = int(secs * 1000)
        self.engine.set_move_time(ms)
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

    def _on_style(self):
        style = self.style_var.get()
        self.engine.set_play_style(style)
        self._notify("play_style", style)

    def _on_engine_select(self, _e):
        short = self.engine_var.get()
        path = self._engine_paths.get(short)
        if not path:
            return
        try:
            self.engine.switch_engine(path)
        except Exception as e:
            messagebox.showerror("Engine switch failed", str(e), parent=self.frame)
            return
        if self.on_engine_changed:
            self.on_engine_changed(path)

    def _install_engine(self):
        # Launch the in-app installer instead of just opening the browser.
        from .install_dialog import InstallDialog
        target_dir = Path(self.engine.path).parent

        def on_installed(path):
            try:
                self.engine.switch_engine(path)
            except Exception as e:
                messagebox.showerror("Engine switch failed", str(e),
                                     parent=self.frame)
                return
            # Refresh the engine dropdown so the new build shows up
            from .engine import discover_engines
            engines = discover_engines(target_dir)
            self._engine_paths = {self._short_engine_name(p): p
                                  for _, p in engines}
            names = list(self._engine_paths.keys()) or ["(none found)"]
            self.engine_combo["values"] = names
            current = next(
                (n for n, p in self._engine_paths.items()
                 if os.path.abspath(p) == os.path.abspath(self.engine.path)),
                names[0],
            )
            self.engine_var.set(current)
            if self.on_engine_changed:
                self.on_engine_changed(path)

        InstallDialog(self.frame.winfo_toplevel(), target_dir,
                      on_installed, first_run=False)

    def _uninstall_engine(self):
        short = self.engine_var.get()
        path = self._engine_paths.get(short)
        if not path:
            return
        if os.path.abspath(path) == os.path.abspath(self.engine.path):
            messagebox.showwarning(
                "In use", "This engine is currently running. Switch to another first.",
                parent=self.frame,
            )
            return
        if not messagebox.askyesno(
            "Delete engine?", f"Permanently delete:\n{path}", parent=self.frame,
        ):
            return
        try:
            os.remove(path)
        except Exception as e:
            messagebox.showerror("Delete failed", str(e), parent=self.frame)
            return
        engines = discover_engines()
        self._engine_paths = {self._short_engine_name(p): p for _, p in engines}
        names = list(self._engine_paths.keys()) or ["(none found)"]
        self.engine_combo["values"] = names
        current = next(
            (n for n, p in self._engine_paths.items()
             if os.path.abspath(p) == os.path.abspath(self.engine.path)),
            names[0],
        )
        self.engine_var.set(current)

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

    def _install_syzygy(self):
        webbrowser.open(SYZYGY_DOWNLOAD_URL)

    def _pick_syzygy_folder(self):
        path = filedialog.askdirectory(
            title="Select Syzygy tablebase folder", parent=self.frame,
        )
        if not path:
            return False
        self.engine.set_syzygy_path(path)
        self.syz_var.set(True)
        self._update_syz_path_label()
        self._notify("syzygy_path", path)
        return True

    def _uninstall_syzygy(self):
        if not self.engine.syzygy_path:
            return
        if not messagebox.askyesno(
            "Disable tablebases?",
            "Clears the tablebase folder setting (does NOT delete files).",
            parent=self.frame,
        ):
            return
        self.engine.set_syzygy_path("")
        self.syz_var.set(False)
        self._update_syz_path_label()
        self._notify("syzygy_path", "")

    def _update_syz_path_label(self):
        path = self.engine.syzygy_path
        if path:
            display = path if len(path) <= 60 else "…" + path[-58:]
            self.syz_path_lbl.config(text=display, fg=TEXT_DIM)
        else:
            self.syz_path_lbl.config(text="No folder selected", fg=TEXT_FAINT)

    def _notify(self, key, value):
        if self.on_change:
            self.on_change(key, value)
