"""Render python-chess SVG pieces to tkinter PhotoImages at any size, cached."""

import io

import chess
import chess.svg
import resvg_py
from PIL import Image, ImageTk

_SYMBOLS = ("P", "N", "B", "R", "Q", "K", "p", "n", "b", "r", "q", "k")


class PieceImages:
    """Cache of PhotoImage objects keyed by (symbol, size)."""

    # 12 piece symbols × a few simultaneous sizes (board, palettes)
    MAX_CACHE_ENTRIES = 120

    def __init__(self):
        self._cache = {}

    def get(self, symbol, size):
        size = max(8, int(size))
        key = (symbol, size)
        img = self._cache.get(key)
        if img is None:
            if len(self._cache) >= self.MAX_CACHE_ENTRIES:
                # Hard cap: a rapid resize storm shouldn't leak. Keep the
                # most-recently-used sizes by clearing anything we haven't
                # touched this round (simple all-clear is fine; renders are
                # cheap enough).
                self._cache.clear()
            img = self._render(symbol, size)
            self._cache[key] = img
        return img

    def warm(self, size):
        for s in _SYMBOLS:
            self.get(s, size)

    def evict_other_sizes(self, keep_sizes):
        keep = set(int(s) for s in keep_sizes)
        for key in list(self._cache):
            if key[1] not in keep:
                del self._cache[key]

    def _render(self, symbol, size):
        piece = chess.Piece.from_symbol(symbol)
        svg = chess.svg.piece(piece)
        png_bytes = resvg_py.svg_to_bytes(
            svg_string=svg, width=size, height=size
        )
        png_data = bytes(png_bytes) if not isinstance(png_bytes, bytes) else png_bytes
        pil = Image.open(io.BytesIO(png_data)).convert("RGBA")
        if pil.size != (size, size):
            pil = pil.resize((size, size), Image.LANCZOS)
        return ImageTk.PhotoImage(pil)
