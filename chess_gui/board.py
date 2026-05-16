"""Chess board canvas: squares, coords, pieces, drag/drop.

Optimised redraw model:
- Static layer (border, squares, coords) is built once and reused.
- Square colours are updated via itemconfigure (cheap) on highlight changes.
- Pieces and legal-target dots are tracked individually so we can update only
  what changed instead of nuking the whole canvas.
"""

import tkinter as tk

import chess

from .pieces import PieceImages
from .theme import (
    BG, BOARD_BORDER, BOARD_BORDER_COLOR, CHECK_RED, COORD_FG, COORD_MARGIN_BOTTOM,
    COORD_MARGIN_LEFT, DARK_SQ, FONT_COORD, LAST_MOVE_DARK, LAST_MOVE_LIGHT,
    LIGHT_SQ, SELECT,
)


class BoardView:
    """A tk.Canvas chess board with drag/drop. Owns no game logic."""

    _SENTINEL = object()

    def __init__(self, parent, pieces, on_press=None, on_drag=None,
                 on_release=None, on_right_click=None):
        self.parent = parent
        self.pieces = pieces  # PieceImages instance
        self.on_press = on_press
        self.on_drag = on_drag
        self.on_release = on_release
        self.on_right_click = on_right_click

        self.board = chess.Board()
        self.flipped = False
        self.last_move = None
        self.selected = None
        self.legal_targets = []
        self.SQ = 64
        self.drag_enabled = True
        self._drag_active = False
        self._drag_src_square = None
        self._drag_piece = None  # chess.Piece (palette pieces too)
        self._drag_item = None
        self._press_xy = (0, 0)
        self._anim_active = False
        self._anim_src_square = None
        self._anim_item = None

        # Persistent canvas items
        self._border_item = None
        self._square_items = {}  # chess square -> rectangle id
        self._coord_items = []   # text ids
        self._piece_items = {}   # chess square -> image id
        self._dot_items = []     # legal-target circle ids
        self._needs_static_rebuild = True

        self.canvas = tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._on_right_click)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)
        self.on_double_click = None

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def grid(self, **kw):
        self.canvas.grid(**kw)

    def width_for(self, sq):
        return sq * 8 + COORD_MARGIN_LEFT + 2 * BOARD_BORDER

    def height_for(self, sq):
        return sq * 8 + COORD_MARGIN_BOTTOM + 2 * BOARD_BORDER

    def set_square_size(self, sq):
        sq = max(20, int(sq))
        if sq == self.SQ:
            return False
        self.SQ = sq
        self.canvas.config(width=self.width_for(sq), height=self.height_for(sq))
        self.pieces.evict_other_sizes([sq])
        self._needs_static_rebuild = True
        return True

    def set_state(self, board=_SENTINEL, flipped=_SENTINEL, last_move=_SENTINEL,
                  selected=_SENTINEL, legal_targets=_SENTINEL):
        if board is not BoardView._SENTINEL:
            self.board = board
        if flipped is not BoardView._SENTINEL and flipped != self.flipped:
            self.flipped = flipped
            self._needs_static_rebuild = True
        if last_move is not BoardView._SENTINEL:
            self.last_move = last_move
        if selected is not BoardView._SENTINEL:
            self.selected = selected
        if legal_targets is not BoardView._SENTINEL:
            self.legal_targets = legal_targets or []

    def begin_external_drag(self, piece):
        """Start a drag from outside the board (palette). x,y will arrive via on_drag."""
        self._drag_active = True
        self._drag_src_square = None
        self._drag_piece = piece
        self._draw_drag_piece(self._press_xy[0], self._press_xy[1])

    def update_external_drag(self, x, y):
        self._press_xy = (x, y)
        self._draw_drag_piece(x, y)

    def end_external_drag(self):
        self._drag_active = False
        self._drag_piece = None
        if self._drag_item is not None:
            self.canvas.delete(self._drag_item)
            self._drag_item = None

    # ---------------- geometry ----------------

    def origin(self):
        return COORD_MARGIN_LEFT + BOARD_BORDER, BOARD_BORDER

    def xy_to_square(self, x, y):
        ox, oy = self.origin()
        col = (x - ox) // self.SQ
        row = (y - oy) // self.SQ
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        if self.flipped:
            return chess.square(7 - int(col), int(row))
        return chess.square(int(col), 7 - int(row))

    def square_to_xy(self, square):
        f = chess.square_file(square)
        r = chess.square_rank(square)
        if self.flipped:
            col, row = 7 - f, r
        else:
            col, row = f, 7 - r
        ox, oy = self.origin()
        return ox + col * self.SQ, oy + row * self.SQ

    def square_center(self, square):
        x, y = self.square_to_xy(square)
        return x + self.SQ // 2, y + self.SQ // 2

    # ---------------- drawing ----------------

    def redraw(self):
        if self._needs_static_rebuild or not self._square_items:
            self._build_static_layer()
            self._needs_static_rebuild = False
        self._update_square_colors()
        self._draw_pieces_and_dots()

    def _build_static_layer(self):
        c = self.canvas
        c.delete("all")
        self._square_items = {}
        self._coord_items = []
        self._piece_items = {}
        self._dot_items = []
        self._border_item = None
        self._drag_item = None
        self._anim_item = None

        SQ = self.SQ
        ox, oy = self.origin()

        if BOARD_BORDER > 0:
            self._border_item = c.create_rectangle(
                ox - BOARD_BORDER, oy - BOARD_BORDER,
                ox + 8 * SQ + BOARD_BORDER, oy + 8 * SQ + BOARD_BORDER,
                fill=BOARD_BORDER_COLOR, outline="",
            )

        # Squares with default colours; _update_square_colors paints highlights.
        for canvas_row in range(8):
            for canvas_col in range(8):
                if self.flipped:
                    sq = chess.square(7 - canvas_col, canvas_row)
                else:
                    sq = chess.square(canvas_col, 7 - canvas_row)
                light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
                base = LIGHT_SQ if light else DARK_SQ
                x1 = ox + canvas_col * SQ
                y1 = oy + canvas_row * SQ
                item = c.create_rectangle(
                    x1, y1, x1 + SQ, y1 + SQ, fill=base, outline="",
                )
                self._square_items[sq] = item

        # Coordinates
        for r in range(8):
            rank_num = (r + 1) if self.flipped else (8 - r)
            self._coord_items.append(c.create_text(
                ox - COORD_MARGIN_LEFT // 2,
                oy + r * SQ + SQ // 2,
                text=str(rank_num), fill=COORD_FG, font=FONT_COORD,
            ))
        for col in range(8):
            file_char = chr(ord('a') + (7 - col if self.flipped else col))
            self._coord_items.append(c.create_text(
                ox + col * SQ + SQ // 2,
                oy + 8 * SQ + COORD_MARGIN_BOTTOM // 2 + 1,
                text=file_char, fill=COORD_FG, font=FONT_COORD,
            ))

    def _update_square_colors(self):
        """Re-tint squares for last move / selection / check via itemconfigure."""
        c = self.canvas
        check_sq = self.board.king(self.board.turn) if self.board.is_check() else None
        for sq, item in self._square_items.items():
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            color = LIGHT_SQ if light else DARK_SQ
            if self.last_move and sq in (
                self.last_move.from_square, self.last_move.to_square
            ):
                color = LAST_MOVE_LIGHT if light else LAST_MOVE_DARK
            if self.selected == sq:
                color = SELECT
            if sq == check_sq:
                color = CHECK_RED
            c.itemconfigure(item, fill=color)

    def _draw_pieces_and_dots(self):
        """Re-create pieces and legal-target dots. Static layer is preserved."""
        c = self.canvas
        # Wipe previous pieces + dots
        for item in self._piece_items.values():
            c.delete(item)
        self._piece_items = {}
        for item in self._dot_items:
            c.delete(item)
        self._dot_items = []

        SQ = self.SQ

        # Legal-move dots
        for tgt in self.legal_targets:
            cx, cy = self.square_center(tgt)
            if self.board.piece_at(tgt):
                item = c.create_oval(
                    cx - SQ // 2 + 4, cy - SQ // 2 + 4,
                    cx + SQ // 2 - 4, cy + SQ // 2 - 4,
                    outline="#1F1F1F", width=4,
                )
            else:
                r = max(6, SQ // 7)
                item = c.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill="#1F1F1F", outline="",
                )
            self._dot_items.append(item)

        # Pieces (skip drag source and animation source)
        for sq in chess.SQUARES:
            if self._drag_active and self._drag_src_square == sq:
                continue
            if self._anim_active and self._anim_src_square == sq:
                continue
            piece = self.board.piece_at(sq)
            if not piece:
                continue
            cx, cy = self.square_center(sq)
            img = self.pieces.get(piece.symbol(), SQ)
            self._piece_items[sq] = c.create_image(cx, cy, image=img)

        # Drag + animation items live above pieces
        if self._drag_active and self._drag_piece is not None:
            self._draw_drag_piece(*self._press_xy)
        if self._anim_active and self._anim_item is not None:
            c.tag_raise(self._anim_item)

    def animate_move(self, src, dst, on_complete, duration_ms=220):
        """Animate piece sliding from src to dst, then call on_complete()."""
        # If an animation is already running, snap it to its end so we don't
        # end up with two floating pieces or a dropped callback.
        if self._anim_active:
            self.cancel_animation()
        piece = self.board.piece_at(src)
        if piece is None or src == dst:
            on_complete()
            return
        sx, sy = self.square_center(src)
        dx, dy = self.square_center(dst)
        img = self.pieces.get(piece.symbol(), self.SQ)

        # Delete only what changes; keep the static layer.
        src_item = self._piece_items.pop(src, None)
        if src_item is not None:
            self.canvas.delete(src_item)
        for item in self._dot_items:
            self.canvas.delete(item)
        self._dot_items = []
        # Restore source square color if it was the selected square.
        if self.selected is not None:
            prev_sel = self.selected
            self.selected = None
            self.legal_targets = []
            self._update_square_colors()
            # Also clear any other highlights we don't want during animation
            _ = prev_sel  # already cleared

        self._anim_src_square = src
        self._anim_active = True
        self._anim_item = self.canvas.create_image(sx, sy, image=img)
        self.canvas.tag_raise(self._anim_item)

        STEPS = 16
        interval = max(8, duration_ms // STEPS)

        def step(i):
            if not self._anim_active:
                return
            if i >= STEPS:
                if self._anim_item is not None:
                    self.canvas.delete(self._anim_item)
                self._anim_item = None
                self._anim_active = False
                self._anim_src_square = None
                on_complete()
                return
            t = (i + 1) / STEPS
            t = 1 - (1 - t) ** 3  # ease-out cubic
            x = sx + (dx - sx) * t
            y = sy + (dy - sy) * t
            self.canvas.coords(self._anim_item, x, y)
            self.canvas.after(interval, lambda: step(i + 1))

        step(0)

    def cancel_animation(self):
        if self._anim_item is not None:
            self.canvas.delete(self._anim_item)
        self._anim_item = None
        self._anim_active = False
        self._anim_src_square = None

    def _draw_drag_piece(self, x, y):
        if not self._drag_active or self._drag_piece is None:
            return
        img = self.pieces.get(self._drag_piece.symbol(), self.SQ)
        if self._drag_item is None:
            self._drag_item = self.canvas.create_image(x, y, image=img)
        else:
            self.canvas.coords(self._drag_item, x, y)
            self.canvas.tag_raise(self._drag_item)

    # ---------------- event handlers ----------------

    def _on_press(self, event):
        sq = self.xy_to_square(event.x, event.y)
        self._press_xy = (event.x, event.y)
        self._drag_src_square = sq
        self._drag_active = False
        self._drag_piece = self.board.piece_at(sq) if sq is not None else None
        if self.on_press:
            self.on_press(event, sq)

    def _on_drag(self, event):
        if not self.drag_enabled:
            return
        if self._drag_src_square is None and not self._drag_active:
            return
        if not self._drag_active:
            dx = event.x - self._press_xy[0]
            dy = event.y - self._press_xy[1]
            if dx * dx + dy * dy < 25:
                return
            self._drag_active = True
            piece = self.board.piece_at(self._drag_src_square)
            self._drag_piece = piece
            # Hide source piece without redrawing the whole board
            src_item = self._piece_items.pop(self._drag_src_square, None)
            if src_item is not None:
                self.canvas.delete(src_item)
            self._press_xy = (event.x, event.y)
            self._draw_drag_piece(event.x, event.y)
        else:
            self._press_xy = (event.x, event.y)
            self._draw_drag_piece(event.x, event.y)
        if self.on_drag:
            self.on_drag(event)

    def _on_release(self, event):
        target_sq = self.xy_to_square(event.x, event.y)
        was_drag = self._drag_active
        src = self._drag_src_square
        self._drag_active = False
        self._drag_piece = None
        if self._drag_item is not None:
            self.canvas.delete(self._drag_item)
            self._drag_item = None
        self._drag_src_square = None
        if self.on_release:
            self.on_release(event, src, target_sq, was_drag)

    def _on_right_click(self, event):
        sq = self.xy_to_square(event.x, event.y)
        if self.on_right_click:
            self.on_right_click(event, sq)

    def _on_double_click(self, event):
        sq = self.xy_to_square(event.x, event.y)
        if self.on_double_click and sq is not None:
            self.on_double_click(event, sq)
