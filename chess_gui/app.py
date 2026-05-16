"""Stockfish Chess: orchestrator. Glues board, palettes, sidebar, engine."""

import sys
import tkinter as tk
from tkinter import messagebox

import chess
import chess.pgn

from .board import BoardView
from .engine import Engine
from .fen_bar import FenBar
from .palette import Palette
from .pieces import PieceImages
from .settings_panel import SettingsPanel
from .sidebar import Sidebar
from .theme import (
    ACCENT, BG, COORD_MARGIN_BOTTOM, COORD_MARGIN_LEFT, FONT_HEADER,
    PALETTE_HEIGHT, PANEL_BG, SIDEBAR_WIDTH,
)


class ChessApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Stockfish Chess")
        self.root.configure(bg=BG)
        self._configure_dpi()

        self.engine = Engine()
        try:
            self.engine.start()
        except Exception as e:
            messagebox.showerror("Stockfish not available", str(e))
            sys.exit(1)

        self.pieces = PieceImages()
        self.board = chess.Board()
        self.last_move = None
        self.flipped = False
        self.selected = None
        self.legal_targets = []
        self.resigned = False
        self.thinking = False
        self.auto_play = False  # engine responds to user drag moves
        self.settings = {
            "move_auto": False,    # play suggested move after Calculate
            "click_to_move": False,  # disable drag; click-click only
        }
        self._undo_stack = []  # for forward navigation
        self.SQ = 70
        self._resize_job = None

        self._build_window_geometry()
        self._build_ui()
        self._refresh_all()

    # ---------------- window setup ----------------

    def _configure_dpi(self):
        if sys.platform == "win32":
            try:
                from ctypes import windll
                windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                try:
                    windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
        try:
            self._dpi = max(1.0, self.root.winfo_fpixels("1i") / 96.0)
        except Exception:
            self._dpi = 1.0

    def _build_window_geometry(self):
        s = self._dpi
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        W = min(int(1140 * s), sw - 80)
        H = min(int(820 * s), sh - 100)
        x = max(0, (sw - W) // 2)
        y = max(0, (sh - H) // 2 - 30)
        self.root.geometry(f"{W}x{H}+{x}+{y}")
        self.root.minsize(int(980 * s), int(740 * s))

    # ---------------- ui ----------------

    def _build_ui(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)
        self._outer = outer

        # Inner container holds board + sidebar, centered horizontally
        inner = tk.Frame(outer, bg=BG)
        inner.pack(expand=True, fill="y")
        inner.grid_rowconfigure(0, weight=1)
        inner.grid_columnconfigure(0, weight=0)
        inner.grid_columnconfigure(1, weight=0, minsize=SIDEBAR_WIDTH)
        self._inner = inner

        # Board column (left of inner)
        board_col = tk.Frame(inner, bg=BG)
        board_col.grid(row=0, column=0, sticky="n", padx=(0, 28))
        self._board_col = board_col

        # Top palette (black pieces)
        self.top_palette = Palette(
            board_col, self.pieces, chess.BLACK,
            on_drag_start=self._palette_drag_start,
            on_drag_move=self._palette_drag_move,
            on_drag_end=self._palette_drag_end,
        )
        self.top_palette.pack(fill="x", padx=(COORD_MARGIN_LEFT, 0))

        # Board
        self.board_view = BoardView(
            board_col, self.pieces,
            on_press=self._on_board_press,
            on_release=self._on_board_release,
            on_right_click=self._on_board_right_click,
        )
        self.board_view.canvas.pack(anchor="w")

        # Bottom palette (white pieces)
        self.bot_palette = Palette(
            board_col, self.pieces, chess.WHITE,
            on_drag_start=self._palette_drag_start,
            on_drag_move=self._palette_drag_move,
            on_drag_end=self._palette_drag_end,
        )
        self.bot_palette.pack(fill="x", padx=(COORD_MARGIN_LEFT, 0), pady=(4, 0))

        # FEN bar
        self.fen_bar = FenBar(board_col, on_fen_change=self._on_fen_change)
        self.fen_bar.pack(fill="x", padx=(COORD_MARGIN_LEFT, 0), pady=(10, 0))

        # Sidebar (right of inner): sticky ns so it fills row height
        self._sidebar_wrap = tk.Frame(inner, bg=PANEL_BG)
        self._sidebar_wrap.grid(row=0, column=1, sticky="nws")
        sidebar_wrap = self._sidebar_wrap
        self.sidebar = Sidebar(sidebar_wrap, {
            "on_color_change": self._on_color_change,
            "on_castling_change": self._on_castling_change,
            "on_elo_change": self._on_elo_change,
            "on_reset": self._on_reset,
            "on_capture_all": self._on_capture_all,
            "on_flip": self._on_flip,
            "on_pgn": self._on_pgn,
            "on_settings": self._on_settings,
            "on_back": self._on_back,
            "on_forward": self._on_forward,
            "on_calculate": self._on_calculate,
        }, initial_elo=self.engine.elo)
        self.sidebar.pack(fill="both", expand=True)
        self.sidebar.result.on_move_click = self._play_suggested
        self.sidebar.result.on_cancel = self._cancel_calc

        # Window resize → recompute square size
        self.root.bind("<Configure>", self._on_window_resize)

    def _on_window_resize(self, event):
        # Only react to root-level resizes; debounce so we don't re-render
        # the board for every intermediate width during a drag-resize.
        if event.widget is not self.root:
            return
        if self._resize_job is not None:
            self.root.after_cancel(self._resize_job)
        self._resize_job = self.root.after(80, self._apply_resize)

    def _apply_resize(self):
        self._resize_job = None
        avail_w = self.root.winfo_width() - SIDEBAR_WIDTH - 60 - COORD_MARGIN_LEFT
        avail_h = (self.root.winfo_height() - 2 * PALETTE_HEIGHT
                   - COORD_MARGIN_BOTTOM - 70)
        sq = max(40, min(96, avail_w // 8, avail_h // 8))
        if abs(sq - self.SQ) >= 3:
            self.SQ = sq
            if self.board_view.set_square_size(sq):
                self.board_view.redraw()
                self.top_palette.set_icon_size(int(sq * 0.62))
                self.bot_palette.set_icon_size(int(sq * 0.62))

    # ---------------- board events ----------------

    def _on_board_press(self, event, sq):
        if sq is None:
            self.selected = None
            self.legal_targets = []
            self._refresh_board()
            return
        piece = self.board.piece_at(sq)
        # Click-click move: previously selected, this is the destination
        if (self.selected is not None and self.selected != sq
                and not self.thinking and not self.resigned
                and not self.board.is_game_over()):
            move = self._resolve_user_move(self.selected, sq)
            if move:
                self._make_human_move(move)
                return
        # Select piece if it belongs to side to move
        if piece is not None and piece.color == self.board.turn:
            self.selected = sq
            self.legal_targets = [
                m.to_square for m in self.board.legal_moves if m.from_square == sq
            ]
            self._refresh_board()
        else:
            self.selected = None
            self.legal_targets = []
            self._refresh_board()

    def _on_board_release(self, event, src, target_sq, was_drag):
        if not was_drag:
            return
        if src is None:
            return
        piece = self.board.piece_at(src)
        if piece is None:
            return
        # Drag off-board → remove piece (setup convenience)
        if target_sq is None:
            self.board.remove_piece_at(src)
            self.last_move = None
            self.selected = None
            self.legal_targets = []
            self._refresh_all()
            return
        if target_sq == src:
            self._refresh_board()
            return
        # Try as a legal move
        if (not self.thinking and not self.resigned
                and not self.board.is_game_over()
                and piece.color == self.board.turn):
            move = self._resolve_user_move(src, target_sq)
            if move:
                # Drag already moved the piece visually, skip animation
                self._make_human_move(move, animate=False)
                return
        # Free placement (setup-style drop on a non-legal target)
        self.board.remove_piece_at(src)
        self.board.set_piece_at(target_sq, piece)
        self.last_move = None
        self.selected = None
        self.legal_targets = []
        self._refresh_all()

    def _on_board_right_click(self, event, sq):
        if sq is None:
            return
        self.board.remove_piece_at(sq)
        self._refresh_all()

    def _resolve_user_move(self, src, dst):
        """Find a legal move from src to dst. If multiple promotion choices
        exist, prompt the user. Returns a chess.Move or None."""
        non_promo = None
        promos = []
        for m in self.board.legal_moves:
            if m.from_square == src and m.to_square == dst:
                if m.promotion:
                    promos.append(m)
                else:
                    non_promo = m
        if non_promo is not None:
            return non_promo
        if promos:
            return self._ask_promotion(promos)
        return None

    def _find_legal_move(self, src, dst):
        """Used by suggestion-click: prefers queen-promotion silently."""
        for m in self.board.legal_moves:
            if m.from_square == src and m.to_square == dst:
                if m.promotion and m.promotion != chess.QUEEN:
                    continue
                return m
        return None

    def _ask_promotion(self, promos):
        from tkinter import font as tkfont
        from .theme import (BTN_BG, BTN_BORDER, BTN_HOVER, FONT_LABEL,
                            PANEL_BG, TEXT_FG)
        chosen = [None]
        dlg = tk.Toplevel(self.root)
        dlg.title("Promote pawn")
        dlg.configure(bg=PANEL_BG, padx=22, pady=18)
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        tk.Label(dlg, text="Promote pawn to:", bg=PANEL_BG, fg=TEXT_FG,
                 font=FONT_LABEL).pack(pady=(0, 12))
        row = tk.Frame(dlg, bg=PANEL_BG)
        row.pack()
        choices = [
            ("Queen",  chess.QUEEN),
            ("Rook",   chess.ROOK),
            ("Bishop", chess.BISHOP),
            ("Knight", chess.KNIGHT),
        ]
        for label, pt in choices:
            def pick(pt=pt):
                for m in promos:
                    if m.promotion == pt:
                        chosen[0] = m
                        break
                dlg.destroy()
            wrap = tk.Frame(row, bg=BTN_BORDER, padx=1, pady=1)
            wrap.pack(side="left", padx=4)
            tk.Button(
                wrap, text=label, command=pick, bg=BTN_BG, fg=TEXT_FG,
                relief="flat", font=FONT_LABEL, padx=14, pady=6, borderwidth=0,
                activebackground=BTN_HOVER, activeforeground=TEXT_FG,
                cursor="hand2",
            ).pack()
        dlg.bind("<Escape>", lambda _e: dlg.destroy())
        # Keyboard shortcuts (q/r/b/n)
        for key, pt in [("q", chess.QUEEN), ("r", chess.ROOK),
                        ("b", chess.BISHOP), ("n", chess.KNIGHT)]:
            dlg.bind(key, lambda _e, pt=pt: (
                [chosen.__setitem__(0, m) for m in promos if m.promotion == pt],
                dlg.destroy(),
            ))
        # Center on the parent window
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() // 2) - 130
        y = self.root.winfo_rooty() + (self.root.winfo_height() // 2) - 60
        dlg.geometry(f"+{x}+{y}")
        dlg.wait_window()
        return chosen[0]

    def _make_human_move(self, move, animate=True):
        if animate:
            self.selected = None
            self.legal_targets = []
            self.board_view.animate_move(
                move.from_square, move.to_square,
                lambda: self._finalize_move(move, then_engine=self.auto_play),
            )
        else:
            self._finalize_move(move, then_engine=self.auto_play)

    def _finalize_move(self, move, then_engine=False):
        self.board.push(move)
        self._undo_stack.clear()
        self.last_move = move
        self.selected = None
        self.legal_targets = []
        self._refresh_all()
        if then_engine and not self.board.is_game_over():
            self.root.after(140, self._engine_play)

    # ---------------- palette drag ----------------

    def _palette_drag_start(self, piece):
        self.board_view.begin_external_drag(piece)

    def _palette_drag_move(self, root_x, root_y):
        bx = root_x - self.board_view.canvas.winfo_rootx()
        by = root_y - self.board_view.canvas.winfo_rooty()
        self.board_view.update_external_drag(bx, by)

    def _palette_drag_end(self, root_x, root_y):
        bx = root_x - self.board_view.canvas.winfo_rootx()
        by = root_y - self.board_view.canvas.winfo_rooty()
        target_sq = self.board_view.xy_to_square(bx, by)
        piece = self.board_view._drag_piece
        self.board_view.end_external_drag()
        if target_sq is not None and piece is not None:
            self.board.set_piece_at(target_sq, piece)
            self.last_move = None
            self.selected = None
            self.legal_targets = []
            self._refresh_all()
        else:
            self._refresh_board()

    # ---------------- sidebar callbacks ----------------

    def _on_color_change(self, val):
        new_turn = chess.WHITE if val == "white" else chess.BLACK
        if self.board.turn == new_turn:
            return
        # Cancel any in-flight engine work; flipping turn while Stockfish is
        # analysing the OLD side leaves the result stale.
        if self.thinking:
            self._cancel_calc()
        self.board.turn = new_turn
        self.last_move = None
        self.selected = None
        self.legal_targets = []
        self._refresh_all()

    def _on_elo_change(self, elo):
        self.engine.set_elo(elo)

    def _on_castling_change(self, key, value):
        bit_map = {
            "K": chess.BB_H1, "Q": chess.BB_A1,
            "k": chess.BB_H8, "q": chess.BB_A8,
        }
        bit = bit_map[key]
        if value:
            self.board.castling_rights |= bit
        else:
            self.board.castling_rights &= ~bit
        self._refresh_fen()

    def _on_reset(self):
        if self.thinking:
            return
        self.board = chess.Board()
        self.last_move = None
        self.selected = None
        self.legal_targets = []
        self.resigned = False
        self._undo_stack.clear()
        self.sidebar.color_var.set("white")
        self._refresh_all()

    def _on_capture_all(self):
        self.board.clear()
        self.board.set_piece_at(chess.E1, chess.Piece(chess.KING, chess.WHITE))
        self.board.set_piece_at(chess.E8, chess.Piece(chess.KING, chess.BLACK))
        self.board.castling_rights = 0
        self.last_move = None
        self.selected = None
        self.legal_targets = []
        self._undo_stack.clear()
        self.sidebar.color_var.set("white")
        self._refresh_all()

    def _on_flip(self):
        self.flipped = not self.flipped
        self._refresh_board()

    def _on_pgn(self):
        game = chess.pgn.Game()
        game.headers["Event"] = "Stockfish Chess"
        node = game
        b = chess.Board()
        for m in self.board.move_stack:
            node = node.add_variation(m)
            b.push(m)
        pgn_text = str(game)
        self.root.clipboard_clear()
        self.root.clipboard_append(pgn_text)
        self.sidebar.set_status("PGN copied to clipboard", ACCENT)
        self.root.after(2500, lambda: self.sidebar.set_status("", None))

    def _on_settings(self):
        # Hide the board column and let the sidebar stretch across the
        # whole window so the settings panel has real estate to work with.
        self._board_col.grid_remove()
        self._inner.pack_forget()
        self._inner.pack(expand=True, fill="both")
        self._inner.grid_columnconfigure(1, minsize=0, weight=1)
        self._sidebar_wrap.grid_configure(sticky="nsew")
        panel = SettingsPanel(
            self.sidebar.frame,
            self.engine,
            self.settings,
            on_close=self._close_settings,
            on_change=self._on_setting_change,
            on_engine_changed=self._on_engine_changed,
        )
        self.sidebar.show_settings(panel)

    def _close_settings(self):
        self.sidebar.show_main()
        self._board_col.grid()
        self._inner.pack_forget()
        self._inner.pack(expand=True, fill="y")
        self._inner.grid_columnconfigure(1, minsize=SIDEBAR_WIDTH, weight=0)
        self._sidebar_wrap.grid_configure(sticky="nws")

    def _on_setting_change(self, key, value):
        if key == "click_to_move":
            self.board_view.drag_enabled = not value

    def _on_engine_changed(self, new_path):
        # New engine loaded; settings re-applied automatically by switch_engine
        pass

    def _on_back(self):
        if self.thinking or not self.board.move_stack:
            return
        m = self.board.pop()
        self._undo_stack.append(m)
        self.last_move = self.board.move_stack[-1] if self.board.move_stack else None
        self.selected = None
        self.legal_targets = []
        self.resigned = False
        self._refresh_all()

    def _on_forward(self):
        if self.thinking or not self._undo_stack:
            return
        m = self._undo_stack.pop()
        self.board.push(m)
        self.last_move = m
        self.selected = None
        self.legal_targets = []
        self._refresh_all()

    def _on_calculate(self):
        if self.thinking or not self.engine.engine:
            return
        # Active Color radio is the source of truth for whose move we analyse.
        # Force board.turn to match so a chain of clicked suggestions stays on
        # the side the user picked; the other side is manual input.
        wanted_turn = self.sidebar.active_color()
        if self.board.turn != wanted_turn:
            self.board.turn = wanted_turn
            self._refresh_fen()
        # Strict validation. Sending Stockfish a malformed position (e.g. a
        # king is missing because the user dragged it off the board) is a
        # great way to hang the engine. Catch everything up front.
        msg = self._position_problem()
        if msg:
            self.sidebar.result.show_error(msg)
            return
        self.thinking = True
        self.sidebar.set_status("")
        self.sidebar.result.start_calc()

        def progress(depth, nps):
            self.root.after(0, lambda d=depth, n=nps:
                            self.sidebar.result.update_progress(d, n))

        def done(results, depth, nps):
            self.root.after(0, lambda r=results, d=depth, n=nps:
                            self._calc_done(r, d, n))

        def err(msg):
            self.root.after(0, lambda: self._calc_err(msg))

        self.engine.analyse_async(self.board, progress, done, err)

    def _calc_done(self, results, depth, nps):
        if not results:
            self.thinking = False
            self.sidebar.result.show_error("No legal moves")
            return
        self.sidebar.result.show_results(results, depth, nps)
        # Move automatically: play the top-PV move (with animation).
        # Keep thinking=True throughout so a stray click can't kick off a
        # second engine call that corrupts the UCI stream.
        if self.settings.get("move_auto") and results:
            top_label = results[0][0]
            move = self._move_from_label(top_label)
            if move:
                self.board_view.animate_move(
                    move.from_square, move.to_square,
                    lambda m=move: self._finalize_after_engine(m),
                )
                return
        self.thinking = False

    def _finalize_after_engine(self, move):
        self._finalize_move(move)
        self.thinking = False

    def _play_suggested(self, label):
        if self.thinking or self.board.is_game_over():
            return
        move = self._move_from_label(label)
        if move is None:
            return
        self.thinking = True
        self.sidebar.result.clear()
        self.board_view.animate_move(
            move.from_square, move.to_square,
            lambda m=move: self._finalize_after_engine(m),
        )

    def _cancel_calc(self):
        if not self.thinking:
            return
        # Tell the engine to abort and invalidate any pending callbacks from
        # the in-flight worker. Then proactively restart the engine so a bad
        # position or a hung Stockfish can't poison the next Calculate.
        self.engine.cancel()
        self.thinking = False
        self.sidebar.result.clear()
        try:
            self.engine.restart()
        except Exception as e:
            messagebox.showerror("Engine restart failed", str(e))

    def _position_problem(self):
        """Return a user-facing reason the position can't be analysed, or None."""
        try:
            if self.board.king(chess.WHITE) is None:
                return "White is missing a king"
            if self.board.king(chess.BLACK) is None:
                return "Black is missing a king"
            if not self.board.is_valid():
                return "Position isn't legal (kings adjacent, pawn on back rank, etc.)"
            if not any(self.board.legal_moves):
                if self.board.is_checkmate():
                    return "Checkmate, no moves"
                return "No legal moves in this position"
        except Exception as e:
            return f"Invalid position: {e}"
        return None

    def _move_from_label(self, label):
        for m in self.board.legal_moves:
            if self.engine.use_san:
                if self.board.san(m) == label:
                    return m
            else:
                if m.uci() == label:
                    return m
        return None

    def _calc_err(self, msg):
        self.thinking = False
        self.sidebar.result.show_error(f"Error: {msg[:80]}")

    def _on_fen_change(self, fen):
        try:
            self.board = chess.Board(fen)
        except Exception as e:
            messagebox.showerror("Invalid FEN", str(e))
            return
        self.last_move = None
        self.selected = None
        self.legal_targets = []
        self._undo_stack.clear()
        self.resigned = False
        self.sidebar.color_var.set(
            "white" if self.board.turn == chess.WHITE else "black"
        )
        self._refresh_all()

    # ---------------- engine play ----------------

    def _engine_play(self):
        if self.board.is_game_over() or self.resigned:
            return
        self.thinking = True
        self.sidebar.set_status("Stockfish thinking…")

        def done(move):
            self.root.after(0, lambda: self._engine_done(move))

        def err(msg):
            self.root.after(0, lambda: self._engine_err(msg))

        self.engine.play_async(self.board, done, err)

    def _engine_done(self, move):
        if move is None:
            self.thinking = False
            self.sidebar.set_status("")
            return
        self.board_view.animate_move(
            move.from_square, move.to_square,
            lambda m=move: self._finalize_after_engine(m),
        )

    def _engine_err(self, msg):
        self.thinking = False
        self.sidebar.set_status(f"Engine error: {msg[:60]}", "#FF6B6B")

    # ---------------- refresh ----------------

    def _refresh_all(self):
        self._refresh_board()
        self.sidebar.sync_from_board(self.board)
        self._refresh_fen()
        self._update_status()

    def _refresh_board(self):
        self.board_view.set_state(
            board=self.board, flipped=self.flipped, last_move=self.last_move,
            selected=self.selected, legal_targets=self.legal_targets,
        )
        self.board_view.redraw()

    def _refresh_fen(self):
        self.fen_bar.set_fen(self.board.fen())

    def _update_status(self):
        if self.resigned:
            return
        if self.board.is_checkmate():
            winner = "Black" if self.board.turn == chess.WHITE else "White"
            self.sidebar.set_status(f"Checkmate. {winner} wins.")
        elif self.board.is_stalemate():
            self.sidebar.set_status("Draw: stalemate")
        elif self.board.is_insufficient_material():
            self.sidebar.set_status("Draw: insufficient material")
        elif self.board.can_claim_threefold_repetition():
            self.sidebar.set_status("Draw: threefold repetition")
        elif self.board.can_claim_fifty_moves():
            self.sidebar.set_status("Draw: fifty-move rule")
        elif self.board.is_check():
            who = "White" if self.board.turn == chess.WHITE else "Black"
            self.sidebar.set_status(f"{who} is in check")
        else:
            if not self.thinking:
                self.sidebar.set_status("")

    # ---------------- lifecycle ----------------

    def quit(self):
        # Stop any pending animation and engine work before tearing down,
        # so the Stockfish subprocess gets cleanly killed and no after()
        # callback fires on a destroyed widget.
        try:
            self.board_view.cancel_animation()
        except Exception:
            pass
        try:
            self.engine.cancel()
        except Exception:
            pass
        try:
            self.engine.stop()
        except Exception:
            pass
        self.root.destroy()
