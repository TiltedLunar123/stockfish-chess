"""Tests for score formatting and play-style re-ranking in chess_gui.engine.

_score_str turns a python-chess PovScore into the text shown in the UI, and
_rank_by_style re-orders the engine's candidate moves to bias toward an
aggressive or defensive feel without ever promoting a clearly worse move.
Both are pure: the inputs are built from python-chess objects, no Stockfish.
"""

import chess
import chess.engine

from chess_gui.engine import Engine


def _score(value, turn=chess.WHITE):
    return chess.engine.PovScore(value, turn)


def test_score_str_formats_centipawns_with_sign():
    e = Engine()
    assert e._score_str(_score(chess.engine.Cp(50))) == "+0.50"
    assert e._score_str(_score(chess.engine.Cp(-120))) == "-1.20"
    assert e._score_str(_score(chess.engine.Cp(0))) == "+0.00"


def test_score_str_formats_mate():
    e = Engine()
    assert e._score_str(_score(chess.engine.Mate(3))) == "#3"
    assert e._score_str(_score(chess.engine.Mate(-2))) == "#-2"


def test_score_str_handles_none():
    assert Engine()._score_str(None) == ""


def test_rank_by_style_balanced_keeps_order():
    e = Engine()
    e.play_style = "balanced"
    board = chess.Board()
    scored = [(chess.Move.from_uci("g1f3"), 20, {}),
              (chess.Move.from_uci("b1c3"), 18, {})]
    # The method is only meant to reorder for aggressive/defensive; balanced
    # callers never reach it, but it should still leave its input untouched.
    assert e._rank_by_style(board, scored) == scored


def test_rank_by_style_aggressive_promotes_capture():
    e = Engine()
    e.play_style = "aggressive"
    # White pawn on e4, black pawn on d5: e4xd5 is a capture of equal eval to
    # a quiet developing move, so the aggressive bias should float it to top.
    board = chess.Board(
        "rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2"
    )
    capture = chess.Move.from_uci("e4d5")
    quiet = chess.Move.from_uci("g1f3")
    assert board.is_capture(capture)
    ranked = e._rank_by_style(board, [(capture, 10, {}), (quiet, 10, {})])
    assert ranked[0][0] == capture


def test_rank_by_style_never_promotes_a_move_far_below_best():
    e = Engine()
    e.play_style = "aggressive"
    board = chess.Board()
    strong_quiet = chess.Move.from_uci("g1f3")   # best, cp 100
    weak_quiet = chess.Move.from_uci("b1a3")      # cp 0, more than 80 below best
    ranked = e._rank_by_style(board, [(strong_quiet, 100, {}), (weak_quiet, 0, {})])
    # The 80cp guard means the weaker move can't be biased ahead of the best.
    assert ranked[-1][0] == weak_quiet


def test_rank_by_style_defensive_prefers_castling():
    e = Engine()
    e.play_style = "defensive"
    # White can castle kingside here; castling carries the largest defensive
    # bias, so it should outrank an equally-rated quiet move.
    board = chess.Board(
        "rnbqk2r/pppp1ppp/5n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
    )
    castle = chess.Move.from_uci("e1g1")
    quiet = chess.Move.from_uci("d2d3")
    assert board.is_castling(castle)
    ranked = e._rank_by_style(board, [(castle, 5, {}), (quiet, 5, {})])
    assert ranked[0][0] == castle
