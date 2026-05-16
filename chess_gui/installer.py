"""Stockfish auto-installer.

Detects OS + CPU, fetches the latest Stockfish release from GitHub, picks the
best build the CPU supports, downloads it (with progress), and extracts the
binary into the project's stockfish/ folder.

Usable as a library (called from install_dialog.py) and as a CLI:

    python -m chess_gui.installer                # install recommended
    python -m chess_gui.installer --list         # list available builds
    python -m chess_gui.installer --build bmi2   # install a specific build
"""

import json
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

GITHUB_API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
USER_AGENT = "stockfish-chess-installer"

# (slug, label, required_cpu_flags), ordered most-optimised first.
# Slugs are the exact text that appears in Stockfish's release asset names.
WINDOWS_BUILDS = [
    ("vnni512",      "AVX-512 VNNI",             ["avx512vnni"]),
    ("avx512icl",    "AVX-512 Ice Lake",         ["avx512_vbmi", "avx512_vbmi2"]),
    ("avx512",       "AVX-512",                  ["avx512f"]),
    ("avxvnni",      "AVX-VNNI (12th-gen+)",     ["avx_vnni"]),
    ("bmi2",         "BMI2 + AVX2",              ["bmi2", "avx2"]),
    ("avx2",         "AVX2",                     ["avx2"]),
    ("sse41-popcnt", "SSE4.1 + POPCNT",          ["sse4_1", "popcnt"]),
    ("x86-64",       "Generic x86-64 (slowest)", []),
]

MACOS_ARM_BUILDS = [
    ("m1-apple-silicon", "Apple Silicon (M-series)", []),
]

MACOS_INTEL_BUILDS = [
    ("bmi2",         "BMI2 + AVX2",      ["bmi2", "avx2"]),
    ("avx2",         "AVX2",             ["avx2"]),
    ("sse41-popcnt", "SSE4.1 + POPCNT",  ["sse4_1", "popcnt"]),
    ("x86-64",       "Generic x86-64",   []),
]

LINUX_BUILDS = [
    ("vnni512",      "AVX-512 VNNI",      ["avx512vnni"]),
    ("avx512icl",    "AVX-512 Ice Lake",  ["avx512_vbmi", "avx512_vbmi2"]),
    ("avx512",       "AVX-512",           ["avx512f"]),
    ("avxvnni",      "AVX-VNNI",          ["avx_vnni"]),
    ("bmi2",         "BMI2 + AVX2",       ["bmi2", "avx2"]),
    ("avx2",         "AVX2",              ["avx2"]),
    ("sse41-popcnt", "SSE4.1 + POPCNT",   ["sse4_1", "popcnt"]),
    ("x86-64",       "Generic x86-64",    []),
]


def detect_os():
    name = platform.system()
    if name == "Windows":
        return "windows"
    if name == "Darwin":
        if platform.machine() in ("arm64", "aarch64"):
            return "macos-arm"
        return "macos-intel"
    if name == "Linux":
        return "ubuntu"
    raise RuntimeError(f"Unsupported OS: {name}")


def detect_cpu():
    """Return {'name': str, 'flags': set[str], 'arch': str}."""
    try:
        from cpuinfo import get_cpu_info
        info = get_cpu_info()
        return {
            "name": info.get("brand_raw", "Unknown CPU"),
            "flags": set(info.get("flags", [])),
            "arch": info.get("arch_string_raw", platform.machine()),
        }
    except ImportError:
        return {
            "name": platform.processor() or "Unknown CPU",
            "flags": set(),
            "arch": platform.machine(),
        }


def available_builds(os_id):
    return {
        "windows":     WINDOWS_BUILDS,
        "macos-intel": MACOS_INTEL_BUILDS,
        "macos-arm":   MACOS_ARM_BUILDS,
        "ubuntu":      LINUX_BUILDS,
    }.get(os_id, [])


def recommend_build(os_id, cpu_flags):
    """Pick the most-optimised build the CPU supports."""
    for slug, label, requires in available_builds(os_id):
        if all(f in cpu_flags for f in requires):
            return slug, label
    return "x86-64", "Generic"


def asset_name_for(os_id, slug):
    """Stockfish release-asset filename pattern.

    e.g. stockfish-windows-x86-64-bmi2.zip
         stockfish-ubuntu-x86-64.tar
         stockfish-macos-m1-apple-silicon.tar
    """
    ext = ".zip" if os_id == "windows" else ".tar"
    if os_id == "macos-arm":
        return f"stockfish-macos-{slug}{ext}"
    if slug == "x86-64":
        return f"stockfish-{os_id}-x86-64{ext}"
    return f"stockfish-{os_id}-x86-64-{slug}{ext}"


def fetch_latest_release():
    req = urllib.request.Request(
        GITHUB_API,
        headers={"User-Agent": USER_AGENT,
                 "Accept": "application/vnd.github+json"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def find_asset(release, expected_name):
    for asset in release.get("assets", []):
        if expected_name in asset["name"]:
            return asset
    # Fallback: any asset whose name contains the slug
    return None


def download_with_progress(url, dest_path, on_progress=None):
    """Stream a download to dest_path. on_progress(done, total) called periodically."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk = 64 * 1024
        with open(dest_path, "wb") as f:
            while True:
                buf = resp.read(chunk)
                if not buf:
                    break
                f.write(buf)
                downloaded += len(buf)
                if on_progress:
                    on_progress(downloaded, total)


def _safe_extract(archive_path, target_dir):
    archive_path = Path(archive_path)
    target_dir = Path(target_dir)
    members = []
    name = archive_path.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as zf:
            for member in zf.namelist():
                # Skip absolute paths and any ".." components for safety
                p = Path(member)
                if p.is_absolute() or ".." in p.parts:
                    continue
                zf.extract(member, target_dir)
                members.append(target_dir / member)
    elif name.endswith(".tar"):
        with tarfile.open(archive_path, "r") as tf:
            for member in tf.getmembers():
                p = Path(member.name)
                if p.is_absolute() or ".." in p.parts:
                    continue
                tf.extract(member, target_dir)
                members.append(target_dir / member.name)
    else:
        raise RuntimeError(f"Unknown archive format: {archive_path.name}")
    return members


def _find_extracted_binary(target_dir, members):
    """Stockfish archives contain a nested 'stockfish/' folder with the binary
    inside. Move that binary up to target_dir/ and return its new path."""
    target_dir = Path(target_dir)
    for path in members:
        if not path.exists() or not path.is_file():
            continue
        stem = path.stem.lower()
        if stem.startswith("stockfish"):
            if sys.platform == "win32" and path.suffix.lower() != ".exe":
                continue
            dest = target_dir / path.name
            if path.resolve() != dest.resolve():
                if dest.exists():
                    dest.unlink()
                shutil.move(str(path), str(dest))
            if sys.platform != "win32":
                import stat
                dest.chmod(dest.stat().st_mode
                           | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return dest
    return None


def _cleanup_after_extract(target_dir, archive_path):
    """Remove the downloaded archive and the unused nested 'stockfish/' subdir."""
    archive_path = Path(archive_path)
    target_dir = Path(target_dir)
    try:
        archive_path.unlink()
    except OSError:
        pass
    nested = target_dir / "stockfish"
    if nested.exists() and nested.is_dir():
        try:
            shutil.rmtree(nested)
        except OSError:
            pass


def install_stockfish(target_dir, slug, os_id=None,
                      on_progress=None, on_status=None):
    """Download Stockfish into target_dir. Returns the path to the binary."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    if os_id is None:
        os_id = detect_os()

    if on_status:
        on_status("Fetching release info from GitHub…")
    release = fetch_latest_release()
    expected = asset_name_for(os_id, slug)
    asset = find_asset(release, expected)
    if asset is None:
        raise RuntimeError(
            f"Could not find an asset matching '{expected}' in "
            f"Stockfish {release.get('tag_name', 'latest')}."
        )

    archive_path = target_dir / asset["name"]
    if on_status:
        size_mb = asset.get("size", 0) / 1024 / 1024
        on_status(f"Downloading {asset['name']} ({size_mb:.1f} MB)…")
    download_with_progress(asset["browser_download_url"], archive_path,
                           on_progress=on_progress)

    if on_status:
        on_status("Extracting…")
    members = _safe_extract(archive_path, target_dir)

    binary = _find_extracted_binary(target_dir, members)
    _cleanup_after_extract(target_dir, archive_path)
    if binary is None:
        raise RuntimeError("Stockfish binary not found inside the archive.")
    if on_status:
        on_status(f"Installed: {binary.name}")
    return binary


def _cli():
    import argparse
    parser = argparse.ArgumentParser(description="Install Stockfish")
    parser.add_argument("--target", default=None,
                        help="Install folder (default: ./stockfish)")
    parser.add_argument("--build", default=None,
                        help="Specific build slug (e.g. 'bmi2'). "
                             "Default: recommend.")
    parser.add_argument("--list", action="store_true",
                        help="List available builds for this OS")
    args = parser.parse_args()

    target = Path(args.target) if args.target else (
        Path(__file__).resolve().parent.parent / "stockfish"
    )
    os_id = detect_os()

    if args.list:
        print(f"Builds available for {os_id}:")
        for slug, label, requires in available_builds(os_id):
            req = ", ".join(requires) or "(none)"
            print(f"  {slug:18s}  {label:30s}  needs: {req}")
        return

    cpu = detect_cpu()
    slug = args.build
    if slug is None:
        slug, label = recommend_build(os_id, cpu["flags"])
        print(f"OS:    {os_id}")
        print(f"CPU:   {cpu['name']}")
        print(f"Pick:  {slug} ({label})")

    def progress(done, total):
        if total:
            pct = done * 100 // total
            print(f"\r  {pct:3d}% [{done/1024/1024:6.1f} / {total/1024/1024:6.1f} MB]",
                  end="", flush=True)

    def status(msg):
        print(f"\n{msg}")

    try:
        path = install_stockfish(target, slug, os_id, progress, status)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"\nReady: {path}")


if __name__ == "__main__":
    _cli()
