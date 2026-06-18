"""Tests for Engine._human_style, the human-feel move picker.

_human_style asks Stockfish for a handful of candidate moves and then re-weights
among them so the choice reads as something a person would play, without ever
dropping below the engine's set strength. The real method talks to a Stockfish
subprocess, so here we hand the Engine a stub that returns canned analysis. No
Stockfish is launched, and the inputs are built from python-chess objects.
"""

import random

import chess
import chess.engine

from chess_gui.engine import Engine


def _score(value, turn=chess.WHITE):
    return chess.engine.PovScore(value, turn)


class _PlayResult:
    """Stands in for python-chess's PlayResult (only .move is read)."""

    def __init__(self, move):
        self.move = move


class FakeEngine:
    """Minimal Stockfish stand-in: returns canned analyse() output and tracks
    whether the play() fallback was reached."""

    def __init__(self, infos=None, analyse_raises=False, play_move=None):
        self._infos = infos or []
        self._analyse_raises = analyse_raises
        self._play_move = play_move
        self.play_calls = 0

    def analyse(self, board, limit, multipv=1):
        if self._analyse_raises:
            raise RuntimeError("engine crashed")
        return self._infos

    def play(self, board, limit):
        self.play_calls += 1
        return _PlayResult(self._play_move)


def _limit():
    return chess.engine.Limit(time=0.01)


def test_falls_back_to_play_when_analyse_raises():
    e = Engine()
    fallback = chess.Move.from_uci("e2e4")
    e.engine = FakeEngine(analyse_raises=True, play_move=fallback)
    move = e._human_style(chess.Board(), _limit())
    assert move == fallback
    assert e.engine.play_calls == 1


def test_falls_back_to_play_when_no_usable_candidates():
    # Infos with no pv or no score yield an empty candidate list, so the method
    # has nothing to weight and must defer to a normal engine move.
    e = Engine()
    fallback = chess.Move.from_uci("d2d4")
    infos = [{"score": None}, {"pv": []}]
    e.engine = FakeEngine(infos=infos, play_move=fallback)
    move = e._human_style(chess.Board(), _limit())
    assert move == fallback
    assert e.engine.play_calls == 1


def test_returns_one_of_the_analysed_candidates():
    e = Engine()
    board = chess.Board()
    m1 = chess.Move.from_uci("e2e4")
    m2 = chess.Move.from_uci("d2d4")
    m3 = chess.Move.from_uci("g1f3")
    infos = [
        {"pv": [m1], "score": _score(chess.engine.Cp(30))},
        {"pv": [m2], "score": _score(chess.engine.Cp(20))},
        {"pv": [m3], "score": _score(chess.engine.Cp(10))},
    ]
    e.engine = FakeEngine(infos=infos)
    random.seed(0)
    move = e._human_style(board, _limit())
    assert move in {m1, m2, m3}
    # A real candidate set means the play() fallback is never touched.
    assert e.engine.play_calls == 0


def test_top_move_dominates_when_alternatives_are_much_worse():
    # The weighting tapers hard past an ~80cp drop, so a move 160cp below best
    # should almost never be chosen over the top move.
    e = Engine()
    board = chess.Board()
    top = chess.Move.from_uci("e2e4")
    weak = chess.Move.from_uci("a2a3")
    infos = [
        {"pv": [top], "score": _score(chess.engine.Cp(100))},
        {"pv": [weak], "score": _score(chess.engine.Cp(-60))},
    ]
    e.engine = FakeEngine(infos=infos)
    random.seed(1234)
    picks = [e._human_style(board, _limit()) for _ in range(200)]
    assert picks.count(top) > picks.count(weak)
    assert picks.count(top) > 150
