"""Right sidebar: active color, castling, elo, action links, calc button."""

import tkinter as tk

import chess

from .engine import ELO_MAX, ELO_MIN, tier_for
from .theme import (
    ACCENT, ACCENT_HOVER, BG, BTN_BG, CARD_BG, ENGINE_NAME_FG,
    ENGINE_NAME_HOVER, FONT_BODY, FONT_HEADER, FONT_MOVE_BOX, FONT_PROGRESS,
    FONT_SCORE, MOVE_BOX_BG, MOVE_BOX_BORDER, PANEL_BG, SIDEBAR_WIDTH,
    SPINNER_FG, TEXT_DIM, TEXT_FG,
)
from .widgets import Check, Radio, header, link, styled_button


SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class ResultPanel:
    """Shows analysis output: spinner+stats while analyzing, move boxes + engine after."""

    def __init__(self, parent):
        self.frame = tk.Frame(parent, bg=PANEL_BG)
        self._spin_idx = 0
        self._spinning = False
        self._spin_job = None
        self._engine_name = "Stockfish 18"
        self.on_move_click = None  # callback(move_label) when user clicks a box
        self.on_cancel = None      # callback() when user clicks Cancel while spinning

        # Progress row (spinner + depth/knps + cancel link)
        self.progress_row = tk.Frame(self.frame, bg=PANEL_BG)
        self.spinner_lbl = tk.Label(
            self.progress_row, text="", bg=PANEL_BG, fg=SPINNER_FG,
            font=("Segoe UI Symbol", 14),
        )
        self.spinner_lbl.pack(side="left", padx=(0, 8))
        self.progress_lbl = tk.Label(
            self.progress_row, text="", bg=PANEL_BG, fg=TEXT_DIM,
            font=FONT_PROGRESS, anchor="w",
        )
        self.progress_lbl.pack(side="left")
        self.cancel_lbl = tk.Label(
            self.progress_row, text="Cancel", bg=PANEL_BG, fg=ACCENT,
            font=(FONT_BODY[0], FONT_BODY[1], "bold"), cursor="hand2",
        )
        self.cancel_lbl.pack(side="left", padx=(14, 0))
        self.cancel_lbl.bind(
            "<Button-1>",
            lambda _e: self.on_cancel() if self.on_cancel else None,
        )
        self.cancel_lbl.bind(
            "<Enter>", lambda _e: self.cancel_lbl.configure(fg=ACCENT_HOVER),
        )
        self.cancel_lbl.bind(
            "<Leave>", lambda _e: self.cancel_lbl.configure(fg=ACCENT),
        )

        # Move boxes container
        self.moves_frame = tk.Frame(self.frame, bg=PANEL_BG)

        # Engine name footer
        self.engine_lbl = tk.Label(
            self.frame, text="", bg=PANEL_BG, fg=ENGINE_NAME_FG,
            font=FONT_BODY, anchor="w", cursor="hand2",
        )

    def pack(self, **kw):
        self.frame.pack(**kw)

    def clear(self):
        self._stop_spinner()
        self.progress_row.pack_forget()
        self.moves_frame.pack_forget()
        self.engine_lbl.pack_forget()
        for w in self.moves_frame.winfo_children():
            w.destroy()
        self.progress_lbl.config(text="")

    def start_calc(self):
        self.clear()
        self._start_spinner()
        self.progress_lbl.config(text="depth 0    knps 0")
        self.progress_row.pack(anchor="w", pady=(4, 0))

    def update_progress(self, depth, nps):
        if not self._spinning:
            return
        knps = int((nps or 0) / 1000)
        self.progress_lbl.config(text=f"depth {depth or 0}    knps {knps}")

    def show_results(self, results, depth, nps):
        """results: list of (move_label, score_str)."""
        self._stop_spinner()
        self.progress_row.pack_forget()
        for w in self.moves_frame.winfo_children():
            w.destroy()
        if not results:
            self.engine_lbl.pack_forget()
            return
        for move_label, score_str in results:
            row = tk.Frame(self.moves_frame, bg=PANEL_BG)
            row.pack(anchor="w", pady=(0, 4))
            box_border = tk.Frame(row, bg=MOVE_BOX_BORDER, padx=1, pady=1)
            box_border.pack(side="left")
            box_lbl = tk.Label(
                box_border, text=move_label, bg=MOVE_BOX_BG, fg=TEXT_FG,
                font=FONT_MOVE_BOX, padx=10, pady=3, cursor="hand2",
            )
            box_lbl.pack()

            def _play(label=move_label):
                if self.on_move_click:
                    self.on_move_click(label)

            box_border.bind("<Button-1>", lambda _e, p=_play: p())
            box_lbl.bind("<Button-1>", lambda _e, p=_play: p())
            box_lbl.bind("<Enter>", lambda _e, w=box_lbl, b=box_border:
                         (w.configure(bg=ACCENT, fg="#0F0F0F"),
                          b.configure(bg=ACCENT)))
            box_lbl.bind("<Leave>", lambda _e, w=box_lbl, b=box_border:
                         (w.configure(bg=MOVE_BOX_BG, fg=TEXT_FG),
                          b.configure(bg=MOVE_BOX_BORDER)))

            if score_str:
                tk.Label(
                    row, text=score_str, bg=PANEL_BG, fg=TEXT_FG,
                    font=FONT_SCORE,
                ).pack(side="left", padx=(10, 0))
        self.moves_frame.pack(anchor="w", pady=(6, 4))
        self.engine_lbl.config(text=self._engine_name)
        self.engine_lbl.pack(anchor="w", pady=(2, 0))

    def show_error(self, msg):
        self._stop_spinner()
        self.progress_row.pack_forget()
        for w in self.moves_frame.winfo_children():
            w.destroy()
        tk.Label(
            self.moves_frame, text=msg, bg=PANEL_BG, fg="#E04444",
            font=FONT_BODY, anchor="w", wraplength=SIDEBAR_WIDTH - 8,
            justify="left",
        ).pack(anchor="w")
        self.moves_frame.pack(anchor="w", pady=(6, 0))
        self.engine_lbl.pack_forget()

    def _start_spinner(self):
        self._spinning = True
        self._spin_idx = 0
        self._tick()

    def _stop_spinner(self):
        self._spinning = False
        if self._spin_job is not None:
            self.frame.after_cancel(self._spin_job)
            self._spin_job = None
        self.spinner_lbl.config(text="")

    def _tick(self):
        if not self._spinning:
            return
        self.spinner_lbl.config(text=SPINNER_CHARS[self._spin_idx])
        self._spin_idx = (self._spin_idx + 1) % len(SPINNER_CHARS)
        self._spin_job = self.frame.after(90, self._tick)


class Sidebar:
    def __init__(self, parent, callbacks, initial_elo=ELO_MAX):
        """callbacks: dict with keys
            on_color_change(value 'white'|'black')
            on_castling_change(key 'K'|'Q'|'k'|'q', value bool)
            on_elo_change(elo int)
            on_reset, on_capture_all, on_flip, on_pgn, on_settings,
            on_back, on_forward, on_calculate
        """
        self.cb = callbacks
        self.parent = parent
        # `frame` is the container packed in the sidebar; `main` holds the
        # normal controls and can be hidden when the settings panel is shown.
        self.frame = tk.Frame(parent, bg=PANEL_BG)
        self.main = tk.Frame(self.frame, bg=PANEL_BG)
        self.main.pack(fill="both", expand=True)

        # Active color
        header(self.main, "Active Color").pack(anchor="w", pady=(0, 4))
        self.color_var = tk.StringVar(value="white")
        Radio(
            self.main, self.color_var,
            [("White to move", "white"), ("Black to move", "black")],
            command=self._on_color,
        ).pack(fill="x", pady=(0, 14))

        # Castling
        header(self.main, "Castling Availability").pack(anchor="w", pady=(0, 4))
        self.cast_vars = {}
        cast_frame = tk.Frame(self.main, bg=PANEL_BG)
        cast_frame.pack(fill="x", pady=(0, 14))
        for key, label in [("K", "White/kingside"), ("Q", "White/queenside"),
                           ("k", "Black/kingside"), ("q", "Black/queenside")]:
            v = tk.BooleanVar(value=True)
            Check(cast_frame, label, v,
                  command=lambda k=key, var=v: self._on_castling(k, var)).pack(anchor="w")
            self.cast_vars[key] = v

        # Engine strength (ELO slider)
        header(self.main, "Engine Strength").pack(anchor="w", pady=(0, 4))
        self.elo_var = tk.IntVar(value=initial_elo)
        tk.Scale(
            self.main, from_=ELO_MIN, to=ELO_MAX, orient="horizontal",
            variable=self.elo_var, resolution=10, length=SIDEBAR_WIDTH - 12,
            bg=ACCENT, fg=TEXT_FG, troughcolor="#3A3A3A",
            activebackground=ACCENT_HOVER, highlightthickness=0,
            sliderrelief="raised", sliderlength=26, width=16, showvalue=0,
            borderwidth=0, command=self._on_elo,
        ).pack(fill="x")
        self.elo_label = tk.Label(
            self.main, bg=PANEL_BG, fg=TEXT_DIM, font=FONT_BODY, anchor="w",
        )
        self.elo_label.pack(anchor="w", pady=(2, 14))
        self._update_elo_label(initial_elo)

        # Action links row 1
        actions_row = tk.Frame(self.main, bg=PANEL_BG)
        actions_row.pack(anchor="w", fill="x", pady=(0, 4))
        link(actions_row, "Reset", self.cb["on_reset"]).pack(side="left", padx=(0, 14))
        link(actions_row, "Capture All", self.cb["on_capture_all"]).pack(side="left", padx=(0, 14))
        link(actions_row, "Flip", self.cb["on_flip"]).pack(side="left")

        # Action links row 2
        row2 = tk.Frame(self.main, bg=PANEL_BG)
        row2.pack(anchor="w", fill="x", pady=(2, 14))
        link(row2, "PGN", self.cb["on_pgn"]).pack(side="left", padx=(0, 10))
        gear = tk.Label(row2, text="⚙", bg=PANEL_BG, fg=ACCENT,
                        font=("Segoe UI", 13), cursor="hand2")
        gear.pack(side="left", padx=(0, 12))
        gear.bind("<Button-1>", lambda _e: self.cb["on_settings"]())
        gear.bind("<Enter>", lambda _e: gear.configure(fg=ACCENT_HOVER))
        gear.bind("<Leave>", lambda _e: gear.configure(fg=ACCENT))
        back = tk.Label(row2, text="◀", bg=PANEL_BG, fg=ACCENT,
                        font=("Segoe UI", 11), cursor="hand2")
        back.pack(side="left", padx=(0, 8))
        back.bind("<Button-1>", lambda _e: self.cb["on_back"]())
        back.bind("<Enter>", lambda _e: back.configure(fg=ACCENT_HOVER))
        back.bind("<Leave>", lambda _e: back.configure(fg=ACCENT))
        fwd = tk.Label(row2, text="▶", bg=PANEL_BG, fg=ACCENT,
                       font=("Segoe UI", 11), cursor="hand2")
        fwd.pack(side="left")
        fwd.bind("<Button-1>", lambda _e: self.cb["on_forward"]())
        fwd.bind("<Enter>", lambda _e: fwd.configure(fg=ACCENT_HOVER))
        fwd.bind("<Leave>", lambda _e: fwd.configure(fg=ACCENT))

        # Calculate next move button
        self.calc_btn_wrap = styled_button(
            self.main, "Calculate Next Move", self.cb["on_calculate"],
        )
        self.calc_btn_wrap.pack(anchor="w", pady=(4, 4))

        # Result panel (spinner + stats during, move boxes + engine after)
        self.result = ResultPanel(self.main)
        self.result.pack(anchor="w", fill="x")

        # Transient game-state messages (in-check, game over, PGN copied)
        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(
            self.main, textvariable=self.status_var, bg=PANEL_BG, fg=TEXT_DIM,
            font=FONT_BODY, anchor="w", wraplength=SIDEBAR_WIDTH - 8,
            justify="left",
        )
        self.status_lbl.pack(anchor="w", fill="x", pady=(8, 0))

        self._settings_panel = None

    def pack(self, **kw):
        self.frame.pack(**kw)

    # ---------------- page toggling ----------------

    def show_settings(self, panel):
        """Hide main controls and show the given settings panel."""
        self.main.pack_forget()
        self._settings_panel = panel
        panel.pack(fill="both", expand=True)

    def show_main(self):
        """Hide settings panel and show main controls."""
        if self._settings_panel is not None:
            self._settings_panel.destroy()
            self._settings_panel = None
        self.main.pack(fill="both", expand=True)

    # ---------------- callbacks ----------------

    def _on_color(self, val):
        self.cb["on_color_change"](val)

    def _on_castling(self, key, var):
        self.cb["on_castling_change"](key, var.get())

    def _on_elo(self, val):
        elo = int(float(val))
        self._update_elo_label(elo)
        if "on_elo_change" in self.cb:
            self.cb["on_elo_change"](elo)

    def _update_elo_label(self, elo):
        if elo >= ELO_MAX:
            self.elo_label.config(text="Maximum strength")
        else:
            self.elo_label.config(text=f"{elo} ELO · {tier_for(elo)}")

    # ---------------- state sync ----------------

    def sync_from_board(self, board):
        # NOTE: color_var is intentionally NOT synced. It represents the side
        # the user is analyzing for and is sticky until they click it.
        self.cast_vars["K"].set(bool(board.castling_rights & chess.BB_H1))
        self.cast_vars["Q"].set(bool(board.castling_rights & chess.BB_A1))
        self.cast_vars["k"].set(bool(board.castling_rights & chess.BB_H8))
        self.cast_vars["q"].set(bool(board.castling_rights & chess.BB_A8))

    def active_color(self):
        """Return chess.WHITE or chess.BLACK based on the radio selection."""
        return chess.WHITE if self.color_var.get() == "white" else chess.BLACK

    def set_status(self, text, color=None):
        self.status_var.set(text or "")
        self.status_lbl.config(fg=color if color else TEXT_DIM)
