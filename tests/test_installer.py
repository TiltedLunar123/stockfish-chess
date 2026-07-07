"""Tests for the logic in chess_gui.installer.

Most of these cover the pure functions: OS detection, the per-OS build tables,
the CPU-flag recommendation cascade, the release-asset filename pattern, and
asset matching against a release payload. None of those touch the network.

The _safe_extract tests do build real zip/tar files under tmp_path, but they
stay offline and never reach for a live Stockfish download.
"""

import io
import os
import stat
import tarfile
import zipfile

import pytest

from chess_gui import installer
from chess_gui.installer import (
    asset_name_for,
    available_builds,
    detect_os,
    find_asset,
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


# --- find_asset: pick the right release asset by name -----------------------

def _release(*asset_names):
    """Minimal stand-in for the GitHub release JSON find_asset reads."""
    return {"assets": [{"name": n, "browser_download_url": f"http://x/{n}"}
                       for n in asset_names]}


def test_find_asset_returns_exact_match():
    release = _release(
        "stockfish-windows-x86-64-avx2.zip",
        "stockfish-windows-x86-64-bmi2.zip",
    )
    asset = find_asset(release, "stockfish-windows-x86-64-bmi2.zip")
    assert asset["name"] == "stockfish-windows-x86-64-bmi2.zip"


def test_find_asset_matches_on_substring():
    # find_asset uses containment, so the expected name need only be part of
    # the real asset name (handy if a release suffixes a tag or hash).
    release = _release("stockfish-ubuntu-x86-64-avx2.tar.zst")
    asset = find_asset(release, "stockfish-ubuntu-x86-64-avx2.tar")
    assert asset is not None
    assert asset["name"].startswith("stockfish-ubuntu-x86-64-avx2.tar")


def test_find_asset_returns_first_when_several_match():
    release = _release(
        "stockfish-windows-x86-64-avx2.zip",
        "stockfish-windows-x86-64-avx2.zip.sha256",
    )
    asset = find_asset(release, "stockfish-windows-x86-64-avx2.zip")
    assert asset["name"] == "stockfish-windows-x86-64-avx2.zip"


def test_find_asset_no_match_returns_none():
    release = _release("stockfish-macos-m1-apple-silicon.tar")
    assert find_asset(release, "stockfish-windows-x86-64-bmi2.zip") is None


def test_find_asset_empty_release_returns_none():
    assert find_asset({}, "anything") is None
    assert find_asset({"assets": []}, "anything") is None


# --- _safe_extract: refuse archive members that escape the target dir -------

def _write_zip(path, members):
    """members: list of (arcname, data)."""
    with zipfile.ZipFile(path, "w") as zf:
        for arcname, data in members:
            zf.writestr(arcname, data)


def _write_tar(path, members):
    """members: list of (arcname, data)."""
    with tarfile.open(path, "w") as tf:
        for arcname, data in members:
            info = tarfile.TarInfo(name=arcname)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))


def test_safe_extract_zip_writes_clean_members(tmp_path):
    archive = tmp_path / "good.zip"
    _write_zip(archive, [("stockfish/stockfish.exe", b"bin"),
                         ("stockfish/readme.txt", b"hi")])
    target = tmp_path / "out"
    members = installer._safe_extract(archive, target)

    assert (target / "stockfish" / "stockfish.exe").read_bytes() == b"bin"
    assert (target / "stockfish" / "readme.txt").read_bytes() == b"hi"
    assert len(members) == 2


def test_safe_extract_zip_skips_parent_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    _write_zip(archive, [("stockfish/ok.txt", b"ok"),
                         ("../escape.txt", b"nope")])
    target = tmp_path / "out"
    members = installer._safe_extract(archive, target)

    assert (target / "stockfish" / "ok.txt").exists()
    # The traversal member must not be written anywhere outside the target.
    assert not (tmp_path / "escape.txt").exists()
    assert all("escape.txt" not in str(m) for m in members)


def test_safe_extract_tar_writes_clean_members(tmp_path):
    archive = tmp_path / "good.tar"
    _write_tar(archive, [("stockfish/stockfish", b"bin")])
    target = tmp_path / "out"
    members = installer._safe_extract(archive, target)

    assert (target / "stockfish" / "stockfish").read_bytes() == b"bin"
    assert len(members) == 1


def test_safe_extract_tar_skips_parent_traversal(tmp_path):
    archive = tmp_path / "evil.tar"
    _write_tar(archive, [("stockfish/ok", b"ok"),
                         ("../../escape", b"nope")])
    target = tmp_path / "out"
    installer._safe_extract(archive, target)

    assert (target / "stockfish" / "ok").exists()
    assert not (tmp_path.parent / "escape").exists()
    assert not (tmp_path / "escape").exists()


def test_safe_extract_tar_skips_symlink_that_escapes(tmp_path):
    # A symlink member with a clean name ("stockfish/pwn") but a target that
    # climbs outside the extraction dir must be refused, not created. The
    # name-only check can't catch this, so the escape is caught by the data
    # filter (or, on older Pythons, by refusing link members outright).
    archive = tmp_path / "evil-link.tar"
    with tarfile.open(archive, "w") as tf:
        good = tarfile.TarInfo("stockfish/ok")
        good.size = 2
        tf.addfile(good, io.BytesIO(b"ok"))
        link = tarfile.TarInfo("stockfish/pwn")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../secret"
        tf.addfile(link)

    target = tmp_path / "out"
    members = installer._safe_extract(archive, target)

    # The clean file still comes through...
    assert (target / "stockfish" / "ok").read_bytes() == b"ok"
    # ...but the escaping symlink is neither created nor reported back.
    pwn = target / "stockfish" / "pwn"
    assert not pwn.is_symlink()
    assert not pwn.exists()
    assert all("pwn" not in str(m) for m in members)


def test_safe_extract_rejects_unknown_format(tmp_path):
    archive = tmp_path / "mystery.7z"
    archive.write_bytes(b"not an archive")
    with pytest.raises(RuntimeError):
        installer._safe_extract(archive, tmp_path / "out")


# --- _find_extracted_binary: promote the nested Stockfish binary ------------

def test_find_extracted_binary_promotes_nested_binary(tmp_path, monkeypatch):
    # Stockfish archives put the binary inside a nested stockfish/ folder;
    # _find_extracted_binary moves it up to target_dir and returns it. Pretend
    # we're on a POSIX host so the .exe suffix rule doesn't apply.
    monkeypatch.setattr(installer.sys, "platform", "linux")
    target = tmp_path / "engine"
    nested = target / "stockfish"
    nested.mkdir(parents=True)
    binary = nested / "stockfish-ubuntu-x86-64-avx2"
    binary.write_bytes(b"ELF")
    readme = nested / "readme.md"          # not a stockfish binary
    readme.write_text("hi")
    # A directory and the non-matching file come first to prove they're skipped.
    members = [readme, nested, binary]

    found = installer._find_extracted_binary(target, members)

    assert found == target / "stockfish-ubuntu-x86-64-avx2"
    assert found.read_bytes() == b"ELF"
    assert not binary.exists()             # moved out of the nested folder
    assert readme.exists()                 # left where it was
    if os.name == "posix":
        assert found.stat().st_mode & stat.S_IXUSR


def test_find_extracted_binary_windows_requires_exe(tmp_path, monkeypatch):
    # On Windows a stockfish-named file only counts if it ends in .exe.
    monkeypatch.setattr(installer.sys, "platform", "win32")
    target = tmp_path / "engine"
    nested = target / "stockfish"
    nested.mkdir(parents=True)
    no_ext = nested / "stockfish-nodll"    # right stem, wrong extension
    no_ext.write_bytes(b"x")
    exe = nested / "stockfish-windows-x86-64-avx2.exe"
    exe.write_bytes(b"MZ")
    members = [no_ext, exe]                # extensionless one first, gets skipped

    found = installer._find_extracted_binary(target, members)

    assert found == target / "stockfish-windows-x86-64-avx2.exe"
    assert found.read_bytes() == b"MZ"
    assert not exe.exists()               # promoted up to target_dir


def test_find_extracted_binary_returns_none_without_a_match(tmp_path):
    target = tmp_path / "engine"
    target.mkdir()
    other = target / "someengine.txt"
    other.write_text("nope")
    assert installer._find_extracted_binary(target, [other]) is None


# --- _cleanup_after_extract: drop the archive and the nested folder ---------

def test_cleanup_after_extract_removes_archive_and_nested_dir(tmp_path):
    target = tmp_path / "engine"
    nested = target / "stockfish"
    nested.mkdir(parents=True)
    (nested / "leftover").write_text("junk")
    archive = target / "stockfish-ubuntu-x86-64-avx2.tar"
    archive.write_bytes(b"tarbytes")

    installer._cleanup_after_extract(target, archive)

    assert not archive.exists()
    assert not nested.exists()


def test_cleanup_after_extract_tolerates_missing_paths(tmp_path):
    # A missing archive or absent nested dir must not raise; the OSErrors are
    # swallowed on purpose so a partial install can still finish cleaning up.
    target = tmp_path / "engine"
    target.mkdir()
    installer._cleanup_after_extract(target, target / "gone.tar")
