"""Colors, fonts, and layout constants."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = ROOT / "stockfish"

# Where we look before falling back to scanning the folder. The name has to
# match what the installer actually drops for this platform, otherwise the
# "Stockfish not found" error quotes a Windows exe at a Linux user.
_DEFAULT_ENGINE_NAME = {
    "win32": "stockfish-windows-x86-64-avxvnni.exe",
    "darwin": "stockfish-macos-m1-apple-silicon",
}.get(sys.platform, "stockfish-ubuntu-x86-64-avx2")

ENGINE_PATH = ENGINE_DIR / _DEFAULT_ENGINE_NAME

BG = "#1A1A1A"
PANEL_BG = "#1A1A1A"
CARD_BG = "#262626"

LIGHT_SQ = "#EEEED2"
DARK_SQ = "#769656"
SELECT = "#F6F669"
LEGAL_DOT = "#00000066"
LAST_MOVE_LIGHT = "#F7F783"
LAST_MOVE_DARK = "#BACA2B"
CHECK_RED = "#E04444"

COORD_FG = "#9AA39B"
TEXT_FG = "#ECECEC"
TEXT_DIM = "#A0A0A0"
TEXT_FAINT = "#6B6B6B"
ACCENT = "#94C758"
ACCENT_HOVER = "#A9D86C"
LINK = "#5BA0DC"
LINK_HOVER = "#7AB6E8"
BTN_BG = "#2B2B2B"
BTN_BORDER = "#3F3F3F"
BTN_HOVER = "#363636"
DIVIDER = "#2A2A2A"
MOVE_BOX_BG = "#262626"
MOVE_BOX_BORDER = "#4A4A4A"
ENGINE_NAME_FG = "#5BA0DC"
ENGINE_NAME_HOVER = "#7AB6E8"
SPINNER_FG = "#94C758"

FONT_FAMILY = "Segoe UI"
FONT_BODY = (FONT_FAMILY, 10)
FONT_BODY_BOLD = (FONT_FAMILY, 10, "bold")
FONT_LABEL = (FONT_FAMILY, 11, "bold")
FONT_HEADER = (FONT_FAMILY, 12, "bold")
FONT_TITLE = (FONT_FAMILY, 18, "bold")
FONT_LINK = (FONT_FAMILY, 11, "bold")
FONT_LINK_SMALL = (FONT_FAMILY, 10, "bold")
FONT_COORD = (FONT_FAMILY, 10, "bold")
FONT_MONO = ("Consolas", 10)
FONT_STATUS = (FONT_FAMILY, 11, "bold")
FONT_MOVE_BOX = ("Segoe UI", 11, "bold")
FONT_SCORE = ("Segoe UI", 11)
FONT_PROGRESS = ("Segoe UI", 10)
FONT_HINT = (FONT_FAMILY, 9)

BOARD_BORDER = 1
BOARD_BORDER_COLOR = "#3A3A3A"
COORD_MARGIN_LEFT = 22
COORD_MARGIN_BOTTOM = 20
PALETTE_HEIGHT = 56
SIDEBAR_WIDTH = 320
SETTINGS_PANEL_WIDTH = 360

PIECE_TYPES_PALETTE = ("q", "r", "b", "n", "p")
