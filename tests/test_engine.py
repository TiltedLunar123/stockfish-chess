"""Tests for the display-free helpers in chess_gui.engine.

The Engine class talks to a Stockfish subprocess, but the rating-tier map,
the engine-discovery scan, and the various setter clamps are all pure. An
Engine() instance with no started subprocess is enough to exercise them; the
setters guard on self.engine being None, so nothing here launches Stockfish.
"""

import os
import sys
from pathlib import Path

import pytest

from chess_gui import engine as engine_mod
from chess_gui import theme
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


def _force_platform(monkeypatch, value):
    """Pin sys.platform so the discovery rules for every OS run on any runner."""
    monkeypatch.setattr(engine_mod.sys, "platform", value)


def test_discover_engines_finds_only_stockfish_exes(tmp_path, monkeypatch):
    _force_platform(monkeypatch, "win32")
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


def test_discover_engines_ignores_extensionless_binary_on_windows(tmp_path,
                                                                  monkeypatch):
    # The Windows builds are always .exe, so a bare name there is not an engine.
    _force_platform(monkeypatch, "win32")
    (tmp_path / "stockfish-ubuntu-x86-64-avx2").write_text("x")

    assert discover_engines(tmp_path) == []


@pytest.mark.parametrize("plat,binary", [
    ("linux", "stockfish-ubuntu-x86-64-avx2"),
    ("darwin", "stockfish-macos-m1-apple-silicon"),
])
def test_discover_engines_finds_extensionless_binary_off_windows(
    tmp_path, monkeypatch, plat, binary,
):
    # This is the case that was broken: the installer unpacks these out of the
    # .tar and chmods them +x, but the old .exe-only rule never saw them.
    _force_platform(monkeypatch, plat)
    path = tmp_path / binary
    path.write_text("x")
    path.chmod(0o755)

    found = discover_engines(tmp_path)
    assert [display for display, _p in found] == [binary]


def test_discover_engines_skips_archive_leftovers_off_windows(tmp_path,
                                                              monkeypatch):
    _force_platform(monkeypatch, "linux")
    binary = tmp_path / "stockfish-ubuntu-x86-64-avx2"
    binary.write_text("x")
    binary.chmod(0o755)
    # Same stem, still sitting in the folder if cleanup was interrupted.
    for leftover in ("stockfish-ubuntu-x86-64-avx2.tar",
                     "stockfish-windows-x86-64-avx2.zip",
                     "stockfish.nnue",
                     "stockfish-readme.txt"):
        p = tmp_path / leftover
        p.write_text("x")
        p.chmod(0o755)

    found = discover_engines(tmp_path)
    assert [display for display, _p in found] == ["stockfish-ubuntu-x86-64-avx2"]


def test_discover_engines_requires_exec_bit_off_windows(tmp_path, monkeypatch):
    # os.access(X_OK) is always true on Windows, so fake it rather than rely on
    # the runner's filesystem semantics.
    _force_platform(monkeypatch, "linux")
    runnable = tmp_path / "stockfish-ubuntu-x86-64-avx2"
    runnable.write_text("x")
    not_runnable = tmp_path / "stockfish-ubuntu-x86-64-bmi2"
    not_runnable.write_text("x")

    real_access = engine_mod.os.access

    def fake_access(path, mode):
        if mode == os.X_OK:
            return Path(path).name != not_runnable.name
        return real_access(path, mode)

    monkeypatch.setattr(engine_mod.os, "access", fake_access)

    found = discover_engines(tmp_path)
    assert [display for display, _p in found] == ["stockfish-ubuntu-x86-64-avx2"]


def test_discover_engines_missing_folder(tmp_path):
    assert discover_engines(tmp_path / "does-not-exist") == []


def test_default_engine_path_matches_this_platform():
    # Engine.start() quotes this name when nothing is installed, and it feeds
    # the folder every caller scans, so a Windows exe name on Linux is wrong in
    # both places.
    name = Path(theme.ENGINE_PATH).name
    assert Path(theme.ENGINE_PATH).parent == theme.ENGINE_DIR
    assert "stockfish" in name
    if sys.platform == "win32":
        assert name.endswith(".exe")
    else:
        assert not name.endswith(".exe")


def test_engine_defaults_to_the_platform_path():
    assert Engine().path == str(theme.ENGINE_PATH)


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
