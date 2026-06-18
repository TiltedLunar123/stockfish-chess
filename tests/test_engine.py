"""Tests for the display-free helpers in chess_gui.engine.

The Engine class talks to a Stockfish subprocess, but the rating-tier map,
the engine-discovery scan, and the various setter clamps are all pure. An
Engine() instance with no started subprocess is enough to exercise them; the
setters guard on self.engine being None, so nothing here launches Stockfish.
"""

import pytest

from chess_gui.engine import (
    ELO_MAX,
    ELO_MIN,
    Engine,
    discover_engines,
    tier_for,
)


@pytest.mark.parametrize(
    "elo,expected",
    [
        (ELO_MIN, "Beginner"),
        (1319, "Beginner"),   # below the first cutoff still labels Beginner
        (1500, "Casual"),
        (1800, "Club player"),
        (2100, "Strong club"),
        (2400, "Expert"),
        (2600, "Master"),
        (2800, "Grandmaster"),
        (3000, "Super GM"),
        (9999, "Super GM"),   # anything past the top cutoff caps at Super GM
        (2099, "Club player"),  # one below a cutoff stays in the lower band
    ],
)
def test_tier_for(elo, expected):
    assert tier_for(elo) == expected


def test_discover_engines_finds_only_stockfish_exes(tmp_path):
    (tmp_path / "stockfish-windows-x86-64-avx2.exe").write_text("x")
    (tmp_path / "Stockfish-Old.exe").write_text("x")   # match is case-insensitive
    (tmp_path / "notes.txt").write_text("x")            # wrong extension
    (tmp_path / "someengine.exe").write_text("x")       # exe but not stockfish
    (tmp_path / "subdir").mkdir()                        # directories are ignored

    found = discover_engines(tmp_path)
    names = {display for display, _path in found}
    assert names == {"stockfish-windows-x86-64-avx2", "Stockfish-Old"}
    # Every returned path points at a real file inside the folder.
    for _display, path in found:
        assert path.endswith(".exe")


def test_discover_engines_missing_folder(tmp_path):
    assert discover_engines(tmp_path / "does-not-exist") == []


def test_set_multi_pv_clamps_to_1_through_4():
    e = Engine()
    e.set_multi_pv(0)
    assert e.multi_pv == 1
    e.set_multi_pv(99)
    assert e.multi_pv == 4
    e.set_multi_pv(3)
    assert e.multi_pv == 3


def test_set_move_time_has_a_floor():
    e = Engine()
    e.set_move_time(10)
    assert e.move_time_ms == 100   # floored
    e.set_move_time(2500)
    assert e.move_time_ms == 2500


def test_set_play_style_ignores_garbage():
    e = Engine()
    e.set_play_style("aggressive")
    assert e.play_style == "aggressive"
    e.set_play_style("reckless")   # not a real style, should be a no-op
    assert e.play_style == "aggressive"


def test_set_use_san_coerces_to_bool():
    e = Engine()
    e.set_use_san(0)
    assert e.use_san is False
    e.set_use_san("yes")
    assert e.use_san is True


def test_set_elo_is_safe_without_a_running_engine():
    # _configure() short-circuits when no subprocess is attached, so setting
    # the elo before start() should just record the value.
    e = Engine()
    e.set_elo(1850)
    assert e.elo == 1850


def test_set_syzygy_path_normalises_none():
    e = Engine()
    e.set_syzygy_path(None)
    assert e.syzygy_path == ""
    e.set_syzygy_path("/tablebases")
    assert e.syzygy_path == "/tablebases"
