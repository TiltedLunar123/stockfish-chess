"""Top (black) and bottom (white) piece palettes for setup mode and drag-drop."""

import tkinter as tk

import chess

from .theme import BG, PALETTE_HEIGHT, PIECE_TYPES_PALETTE


class Palette:
    """A canvas strip showing 5 pieces of a single color, draggable to the board."""

    PIECE_TYPE_MAP = {
        "p": chess.PAWN, "n": chess.KNIGHT, "b": chess.BISHOP,
        "r": chess.ROOK, "q": chess.QUEEN,
    }

    def __init__(self, parent, pieces, color, on_drag_start=None,
                 on_drag_move=None, on_drag_end=None):
        self.pieces = pieces  # PieceImages
        self.color = color    # chess.WHITE or chess.BLACK
        self.on_drag_start = on_drag_start
        self.on_drag_move = on_drag_move
        self.on_drag_end = on_drag_end

        self.height = PALETTE_HEIGHT
        self.icon_size = int(self.height * 0.78)
        self._cell = 0
        self._start_x = 0
        self._cy = 0
        self._press_piece = None
        self._dragging = False
        self._press_xy = (0, 0)

        self.canvas = tk.Canvas(parent, bg=BG, highlightthickness=0,
                                height=self.height)
        self.canvas.bind("<Configure>", lambda _e: self._redraw())
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def set_icon_size(self, size):
        size = max(20, int(size))
        if size != self.icon_size:
            self.icon_size = size
            self._redraw()

    def _redraw(self):
        c = self.canvas
        c.delete("all")
        w = c.winfo_width()
        h = c.winfo_height()
        if w <= 1 or h <= 1:
            return
        n = len(PIECE_TYPES_PALETTE)
        cell = min(self.icon_size + 8, w // n)
        self._cell = cell
        total = cell * n
        self._start_x = (w - total) // 2
        self._cy = h // 2
        size = min(self.icon_size, cell - 6)
        for i, t in enumerate(PIECE_TYPES_PALETTE):
            symbol = t.upper() if self.color == chess.WHITE else t
            img = self.pieces.get(symbol, size)
            cx = self._start_x + i * cell + cell // 2
            c.create_image(cx, self._cy, image=img)

    def _piece_at(self, x, y):
        if self._cell <= 0:
            return None
        if abs(y - self._cy) > self._cell // 2:
            return None
        rel = x - self._start_x
        if rel < 0:
            return None
        idx = rel // self._cell
        if not (0 <= idx < len(PIECE_TYPES_PALETTE)):
            return None
        ptype = self.PIECE_TYPE_MAP[PIECE_TYPES_PALETTE[idx]]
        return chess.Piece(ptype, self.color)

    def _on_press(self, event):
        self._press_piece = self._piece_at(event.x, event.y)
        self._press_xy = (event.x, event.y)
        self._dragging = False

    def _on_motion(self, event):
        if self._press_piece is None:
            return
        if not self._dragging:
            dx = event.x - self._press_xy[0]
            dy = event.y - self._press_xy[1]
            if dx * dx + dy * dy < 25:
                return
            self._dragging = True
            if self.on_drag_start:
                self.on_drag_start(self._press_piece)
        if self.on_drag_move:
            root_x = self.canvas.winfo_rootx() + event.x
            root_y = self.canvas.winfo_rooty() + event.y
            self.on_drag_move(root_x, root_y)

    def _on_release(self, event):
        if self._dragging and self.on_drag_end:
            root_x = self.canvas.winfo_rootx() + event.x
            root_y = self.canvas.winfo_rooty() + event.y
            self.on_drag_end(root_x, root_y)
        self._press_piece = None
        self._dragging = False
