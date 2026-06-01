"""Tests for the build-selection logic in chess_gui.installer.

These cover the pure functions only: OS detection, the per-OS build tables,
the CPU-flag recommendation cascade, and the release-asset filename pattern.
Nothing here touches the network or the filesystem.
"""

import pytest

from chess_gui import installer
from chess_gui.installer import (
    asset_name_for,
    available_builds,
    detect_os,
    recommend_build,
)


@pytest.mark.parametrize(
    "system,machine,expected",
    [
        ("Windows", "AMD64", "windows"),
        ("Linux", "x86_64", "ubuntu"),
        ("Darwin", "arm64", "macos-arm"),
        ("Darwin", "aarch64", "macos-arm"),
        ("Darwin", "x86_64", "macos-intel"),
    ],
)
def test_detect_os(monkeypatch, system, machine, expected):
    monkeypatch.setattr(installer.platform, "system", lambda: system)
    monkeypatch.setattr(installer.platform, "machine", lambda: machine)
    assert detect_os() == expected


def test_detect_os_rejects_unknown(monkeypatch):
    monkeypatch.setattr(installer.platform, "system", lambda: "Plan9")
    with pytest.raises(RuntimeError):
        detect_os()


def test_available_builds_known_and_unknown():
    assert available_builds("windows") is installer.WINDOWS_BUILDS
    assert available_builds("ubuntu") is installer.LINUX_BUILDS
    assert available_builds("macos-arm") is installer.MACOS_ARM_BUILDS
    # An unrecognised OS id should give an empty table, not raise.
    assert available_builds("haiku") == []


def test_recommend_build_picks_most_optimised_supported():
    # A CPU with bmi2+avx2 but no AVX-512 should land on the bmi2 build,
    # skipping every AVX-512 entry above it in the table.
    slug, label = recommend_build("windows", {"avx2", "bmi2", "sse4_1", "popcnt"})
    assert slug == "bmi2"
    assert "BMI2" in label


def test_recommend_build_prefers_avx512_when_available():
    flags = {"avx512f", "avx2", "bmi2"}
    slug, _ = recommend_build("windows", flags)
    assert slug == "avx512"


def test_recommend_build_falls_back_to_generic_with_no_flags():
    slug, _ = recommend_build("windows", set())
    assert slug == "x86-64"


def test_recommend_build_unknown_os_returns_generic():
    # No build table means the cascade can't match, so we get the generic
    # fallback rather than an index error.
    slug, label = recommend_build("haiku", {"avx2"})
    assert slug == "x86-64"
    assert label == "Generic"


def test_recommend_build_apple_silicon():
    # Apple Silicon has a single build that requires no flags.
    slug, _ = recommend_build("macos-arm", set())
    assert slug == "m1-apple-silicon"


@pytest.mark.parametrize(
    "os_id,slug,expected",
    [
        ("windows", "bmi2", "stockfish-windows-x86-64-bmi2.zip"),
        ("windows", "x86-64", "stockfish-windows-x86-64.zip"),
        ("ubuntu", "avx2", "stockfish-ubuntu-x86-64-avx2.tar"),
        ("ubuntu", "x86-64", "stockfish-ubuntu-x86-64.tar"),
        ("macos-intel", "avx2", "stockfish-macos-intel-x86-64-avx2.tar"),
        ("macos-arm", "m1-apple-silicon", "stockfish-macos-m1-apple-silicon.tar"),
    ],
)
def test_asset_name_for(os_id, slug, expected):
    assert asset_name_for(os_id, slug) == expected


def test_windows_assets_are_zip_everything_else_is_tar():
    assert asset_name_for("windows", "avx2").endswith(".zip")
    for os_id in ("ubuntu", "macos-intel", "macos-arm"):
        slug = "m1-apple-silicon" if os_id == "macos-arm" else "avx2"
        assert asset_name_for(os_id, slug).endswith(".tar")
