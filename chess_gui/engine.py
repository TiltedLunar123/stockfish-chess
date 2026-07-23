"""Stockfish wrapper. Threads engine calls so the UI stays responsive."""

import os
import random
import sys
import threading
import time
from pathlib import Path

import chess
import chess.engine

from .theme import ENGINE_PATH

ELO_MIN = 1320
ELO_MAX = 3200

# Things the installer leaves in the engine folder that are never the engine.
# Only consulted off Windows, where the binary itself has no extension and so
# can't be told apart from its neighbours by suffix alone.
_NON_ENGINE_SUFFIXES = {".tar", ".zip", ".gz", ".nnue", ".txt", ".md", ".json"}


def _is_engine_file(path):
    """True if path looks like a runnable Stockfish binary for this platform.

    Windows builds ship as .exe. The Linux and macOS builds come out of the .tar
    with no extension at all (stockfish-ubuntu-x86-64-avx2), which is why the
    suffix check has to be platform-specific: applying the Windows rule
    everywhere hid every engine the installer produced off Windows.
    """
    name = path.name.lower()
    if "stockfish" not in name:
        return False
    if sys.platform == "win32":
        return name.endswith(".exe")
    if path.suffix.lower() in _NON_ENGINE_SUFFIXES:
        return False
    return os.access(path, os.X_OK)


def discover_engines(folder=None):
    """Find Stockfish executables in folder. Returns list of (display, path)."""
    if folder is None:
        folder = Path(ENGINE_PATH).parent
    folder = Path(folder)
    if not folder.exists():
        return []
    results = []
    for p in sorted(folder.iterdir()):
        if not p.is_file():
            continue
        if _is_engine_file(p):
            display = p.stem
            results.append((display, str(p)))
    return results


class Engine:
    def __init__(self):
        self.engine = None
        self.path = str(ENGINE_PATH)
        self.elo = ELO_MAX
        self.move_time_ms = 1000
        self.human_mode = False
        self.multi_pv = 1
        self.use_san = True
        self.syzygy_path = ""
        self.play_style = "balanced"  # "aggressive" | "balanced" | "defensive"
        self._current_analysis = None  # the live analysis context, if any
        self._analysis_gen = 0  # bumped on cancel; stale workers must check

    def set_play_style(self, style):
        if style in ("aggressive", "balanced", "defensive"):
            self.play_style = style

    def cancel(self):
        """Tell Stockfish to stop the current analysis and invalidate any
        callbacks the in-flight worker would otherwise fire."""
        self._analysis_gen += 1
        analysis = self._current_analysis
        if analysis is None:
            return
        try:
            analysis.stop()
        except Exception:
            pass

    def restart(self):
        """Kill the engine process and start a fresh one. Settings re-applied."""
        self._analysis_gen += 1
        self._current_analysis = None
        self.stop()
        self.start()
        if self.syzygy_path:
            try:
                self.engine.configure({"SyzygyPath": self.syzygy_path})
            except Exception:
                pass

    def switch_engine(self, new_path):
        """Stop current engine and start the one at new_path."""
        if not new_path or not Path(new_path).exists():
            raise FileNotFoundError(f"Engine not found: {new_path}")
        self.stop()
        self.path = new_path
        self.engine = chess.engine.SimpleEngine.popen_uci(new_path)
        self._configure()
        if self.syzygy_path:
            try:
                self.engine.configure({"SyzygyPath": self.syzygy_path})
            except Exception:
                pass

    def set_multi_pv(self, n):
        self.multi_pv = max(1, min(4, int(n)))

    def set_use_san(self, on):
        self.use_san = bool(on)

    def set_syzygy_path(self, path):
        self.syzygy_path = path or ""
        if not self.engine:
            return
        try:
            self.engine.configure({"SyzygyPath": self.syzygy_path})
        except Exception:
            pass

    def start(self):
        # If the default path doesn't exist, fall back to whatever Stockfish
        # binary is sitting in the folder (the installer drops it there with
        # whatever build slug the user picked).
        if not Path(self.path).exists():
            engines = discover_engines(Path(self.path).parent)
            if engines:
                self.path = engines[0][1]
            else:
                raise FileNotFoundError(f"Stockfish not found: {self.path}")
        self.engine = chess.engine.SimpleEngine.popen_uci(self.path)
        self._configure()

    def stop(self):
        try:
            if self.engine:
                self.engine.quit()
        except Exception:
            pass
        self.engine = None

    def set_elo(self, elo):
        self.elo = int(elo)
        self._configure()

    def set_human_mode(self, on):
        self.human_mode = bool(on)

    def set_move_time(self, ms):
        self.move_time_ms = max(100, int(ms))

    def _configure(self):
        if not self.engine:
            return
        try:
            if self.elo >= ELO_MAX:
                self.engine.configure({
                    "UCI_LimitStrength": False,
                    "Skill Level": 20,
                })
            else:
                self.engine.configure({
                    "UCI_LimitStrength": True,
                    "UCI_Elo": int(self.elo),
                })
        except Exception:
            pass

    def play_async(self, board, on_done, on_error):
        def worker():
            try:
                move = self._choose_move(board)
                on_done(move)
            except Exception as e:
                on_error(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def analyse_async(self, board, on_progress, on_done, on_error):
        """Run streaming analysis. on_progress(depth, nps) called as info arrives.
        on_done(results, depth, nps) called with list of (san_or_uci, score_str) tuples."""
        my_gen = self._analysis_gen

        def fresh():
            return my_gen == self._analysis_gen

        def worker():
            try:
                limit = chess.engine.Limit(time=self.move_time_ms / 1000)
                latest = {}  # multipv idx -> info dict
                last_depth = 0
                last_nps = 0
                last_progress_t = 0.0
                # Stockfish streams many infos per second. Cap UI updates to
                # ~12/s so we don't flood the tk event loop and cause stutter.
                progress_interval = 0.08
                # When biasing by play style we need extra candidates so the
                # re-ranking step has something to work with.
                display_mpv = max(1, self.multi_pv)
                internal_mpv = max(display_mpv,
                                   3 if self.play_style != "balanced" else 1)
                with self.engine.analysis(
                    board, limit, multipv=internal_mpv
                ) as analysis:
                    self._current_analysis = analysis
                    for info in analysis:
                        d = info.get("depth")
                        n = info.get("nps")
                        if d is not None:
                            last_depth = d
                        if n is not None:
                            last_nps = n
                        mpv = info.get("multipv", 1)
                        if "pv" in info and "score" in info:
                            latest[mpv] = info
                        if d is not None or n is not None:
                            now = time.monotonic()
                            if now - last_progress_t >= progress_interval:
                                if fresh():
                                    on_progress(last_depth, last_nps)
                                last_progress_t = now
                self._current_analysis = None
                if not fresh():
                    return
                # Collect (move, cp, info) for re-ranking
                scored = []
                for idx in sorted(latest.keys()):
                    info = latest[idx]
                    pv = info.get("pv")
                    score_obj = info.get("score")
                    if not pv or score_obj is None:
                        continue
                    cp = score_obj.relative.score(mate_score=100000)
                    if cp is None:
                        continue
                    scored.append((pv[0], cp, info))
                if self.play_style != "balanced" and scored:
                    scored = self._rank_by_style(board, scored)
                results = []
                for move, _cp, info in scored[:display_mpv]:
                    label = board.san(move) if self.use_san else move.uci()
                    score_str = self._score_str(info.get("score"))
                    results.append((label, score_str))
                on_done(results, last_depth, last_nps)
            except Exception as e:
                self._current_analysis = None
                if fresh():
                    on_error(str(e))

        threading.Thread(target=worker, daemon=True).start()

    def _choose_move(self, board):
        limit = chess.engine.Limit(time=self.move_time_ms / 1000)
        if self.human_mode:
            return self._human_style(board, limit)
        return self.engine.play(board, limit).move

    def _human_style(self, board, limit):
        """Pick a move that feels like a human chose it, WITHOUT making the
        engine weaker than its set ELO. Stockfish is already configured at
        the chosen ELO via UCI_Elo, so the analyse() call below returns
        candidates that an ~elo player would find. We only re-weight among
        those candidates by human-feel features (development, recapture,
        check, castling). We never bias against the engine's top move when
        the alternatives are objectively worse, and we never artificially
        drop the top move.

        Strength comes from UCI_Elo; flavour comes from this function.
        """
        try:
            infos = self.engine.analyse(board, limit, multipv=4)
        except Exception:
            return self.engine.play(board, limit).move

        scored = []
        for info in infos:
            pv = info.get("pv")
            score_obj = info.get("score")
            if not pv or score_obj is None:
                continue
            cp = score_obj.relative.score(mate_score=100000)
            if cp is None:
                continue
            scored.append((pv[0], cp))

        if not scored:
            return self.engine.play(board, limit).move

        scored.sort(key=lambda x: -x[1])
        best_cp = scored[0][1]
        move_num = board.fullmove_number
        last_move = board.peek() if board.move_stack else None

        weights = []
        for move, cp in scored:
            diff = best_cp - cp

            # Score-diff base weighting. Top move dominates. Worse moves
            # taper off so we don't throw away points: a >80cp drop is rare,
            # >150cp is almost never picked.
            if diff <= 10:
                w = 1.0
            elif diff <= 30:
                w = 0.55
            elif diff <= 60:
                w = 0.18
            elif diff <= 100:
                w = 0.05
            else:
                w = 0.01

            piece = board.piece_at(move.from_square)
            to_file = chess.square_file(move.to_square)

            # Opening behaviour (only when the move is already close to the
            # engine's top, so we never trade real evaluation for style.
            if move_num <= 10 and piece is not None and diff <= 30:
                pt = piece.piece_type
                if pt in (chess.KNIGHT, chess.BISHOP):
                    from_rank = chess.square_rank(move.from_square)
                    if board.turn == chess.WHITE and from_rank == 0:
                        w *= 1.18
                    elif board.turn == chess.BLACK and from_rank == 7:
                        w *= 1.18
                    if pt == chess.KNIGHT and to_file in (0, 7):
                        w *= 0.55  # knight on the rim looks engine-y
                if pt == chess.PAWN:
                    f = chess.square_file(move.from_square)
                    if f in (3, 4):
                        w *= 1.08
                    elif f in (0, 7):
                        w *= 0.75
                if pt == chess.QUEEN:
                    w *= 0.80  # early queen sortie is an engine tell

            # Recapture: gated on being among the top moves so we don't
            # recapture when the engine has spotted a stronger intermezzo.
            if (last_move is not None and board.is_capture(move)
                    and move.to_square == last_move.to_square
                    and diff <= 30):
                w *= 1.5

            # Slight check bias when the move is genuinely competitive
            if diff <= 25:
                board.push(move)
                try:
                    gives_check = board.is_check()
                finally:
                    board.pop()
                if gives_check:
                    w *= 1.1

            # Castling is always popular for humans, but only when it's
            # roughly as good as the best move.
            if board.is_castling(move) and diff <= 30:
                w *= 1.25

            weights.append(w)

        moves = [m for m, _ in scored]
        return random.choices(moves, weights=weights, k=1)[0]

    def _rank_by_style(self, board, scored):
        """Re-order top moves by play style, biasing aggressive/defensive moves.
        scored: list of (move, cp_relative, info).
        Moves more than 80 cp below the best stay last regardless of bias."""
        if not scored:
            return scored
        best_cp = scored[0][1]
        style = self.play_style

        def adjusted(item):
            move, cp, _info = item
            # Don't promote a move that's strictly worse by a lot
            if cp < best_cp - 80:
                return cp
            bias = 0
            captures = board.is_capture(move)
            board.push(move)
            try:
                gives_check = board.is_check()
            finally:
                board.pop()
            if style == "aggressive":
                if captures:
                    bias += 25
                if gives_check:
                    bias += 30
                # Slight bonus for pushing pawns forward (king-side attack feel)
                piece = board.piece_at(move.from_square)
                if piece and piece.piece_type == chess.PAWN:
                    bias += 5
            elif style == "defensive":
                if not captures:
                    bias += 15
                if not gives_check:
                    bias += 8
                # Castling is the most defensive thing you can do
                if board.is_castling(move):
                    bias += 25
            return cp + bias

        return sorted(scored, key=adjusted, reverse=True)

    def _score_str(self, score):
        if score is None:
            return ""
        s = score.white()
        if s.is_mate():
            return f"#{s.mate()}"
        cp = s.score()
        return f"{cp / 100:+.2f}" if cp is not None else ""


def tier_for(elo):
    tiers = [
        (1320, "Beginner"), (1500, "Casual"), (1800, "Club player"),
        (2100, "Strong club"), (2400, "Expert"), (2600, "Master"),
        (2800, "Grandmaster"), (3000, "Super GM"),
    ]
    label = tiers[0][1]
    for cutoff, name in tiers:
        if elo >= cutoff:
            label = name
    return label
