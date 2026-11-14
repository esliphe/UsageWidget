"""Build, verify and package a Windows release.

Why this exists
---------------
The previous packaging step copied ``dist/UsageWidget`` into the package folder
and then ran a cleanup pass that removed what it had just copied. Releases
v5.45.6, v5.45.8, v5.45.10 and v5.45.12 all shipped with an empty
``UsageWidget/`` directory, i.e. a downloadable package with no executable in
it, and nobody noticed because nothing checked.

This script never moves or deletes the payload. It builds, verifies, copies,
hashes and zips -- and it fails loudly if any step leaves the payload
incomplete.

Usage
-----
    python scripts/build_release.py              # build + package
    python scripts/build_release.py --skip-tests # package only
    python scripts/build_release.py --skip-build # re-package existing dist/

Output: ``release/UsageWidget-<version>-win64.zip`` plus ``SHA256SUMS.txt``.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_APP = ROOT / "dist" / "UsageWidget"
RELEASE_DIR = ROOT / "release"
STAGING = ROOT / "build" / "release-staging"

MIN_EXE_BYTES = 1_000_000
MIN_INTERNAL_FILES = 100


def read_version() -> str:
    text = (ROOT / "usage_widget" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise SystemExit("could not read __version__ from usage_widget/__init__.py")
    return match.group(1)


def run(cmd: list[str], label: str) -> None:
    print(f"==> {label}")
    completed = subprocess.run(cmd, cwd=str(ROOT))
    if completed.returncode != 0:
        raise SystemExit(f"{label} failed (exit {completed.returncode})")


def park_previous_build(app_dir: Path) -> None:
    """Move a previous build aside instead of deleting it.

    PyInstaller's COLLECT step removes its output directory before writing a
    new one. That deletion is both what tripped host-level bulk-delete guards
    and the shape of the bug that emptied four release packages. Renaming is
    cheap, reversible, and leaves nothing for a guard to block.
    """
    if not app_dir.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    parked = ROOT / "build" / f"previous-dist-{stamp}"
    parked.parent.mkdir(parents=True, exist_ok=True)
    app_dir.rename(parked)
    print(f"==> previous build parked at {parked}")


def verify_payload(app_dir: Path) -> dict[str, int]:
    """Refuse to package an incomplete build."""
    exe = app_dir / "UsageWidget.exe"
    internal = app_dir / "_internal"
    if not exe.exists():
        raise SystemExit(f"payload incomplete: {exe} is missing")
    exe_bytes = exe.stat().st_size
    if exe_bytes < MIN_EXE_BYTES:
        raise SystemExit(f"payload incomplete: {exe} is only {exe_bytes} bytes")

    if not internal.is_dir():
        raise SystemExit(f"payload incomplete: {internal} is missing")
    internal_files = [path for path in internal.rglob("*") if path.is_file()]
    if len(internal_files) < MIN_INTERNAL_FILES:
        raise SystemExit(
            f"payload incomplete: _internal has {len(internal_files)} files, expected at least {MIN_INTERNAL_FILES}"
        )

    fonts = [path for path in internal.rglob("*.ttf")]
    if not fonts:
        raise SystemExit("payload incomplete: bundled CJK font is missing from _internal")

    return {
        "exe_bytes": exe_bytes,
        "internal_files": len(internal_files),
        "fonts": len(fonts),
    }


def stage_payload(app_dir: Path) -> Path:
    """Copy (never move, never delete) dist/UsageWidget into a staging folder."""
    if STAGING.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        parked = STAGING.with_name(f"previous-staging-{stamp}")
        STAGING.rename(parked)
        print(f"==> previous staging parked at {parked}")
    STAGING.mkdir(parents=True)
    target = STAGING / "UsageWidget"
    shutil.copytree(app_dir, target)
    return target


def write_zip(source_root: Path, zip_path: Path) -> int:
    """Zip the staged folder and return the number of entries written."""
    count = 0
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(source_root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_root.parent).as_posix())
                count += 1
    return count


def verify_zip(zip_path: Path, expected_entries: int) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        if len(names) != expected_entries:
            raise SystemExit(f"zip incomplete: {len(names)} entries, expected {expected_entries}")
        if not any(name.endswith("UsageWidget.exe") for name in names):
            raise SystemExit("zip incomplete: UsageWidget.exe is not inside the archive")
        bad = archive.testzip()
        if bad:
            raise SystemExit(f"zip corrupt at {bad}")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and package a UsageWidget release.")
    parser.add_argument("--skip-tests", action="store_true", help="skip the regression suite")
    parser.add_argument("--skip-build", action="store_true", help="reuse an existing dist/UsageWidget")
    args = parser.parse_args()

    version = read_version()
    print(f"==> UsageWidget {version}")

    if not args.skip_build:
        run([sys.executable, "-m", "compileall", "-q", "usage_widget", "run.py", "UsageWidget.spec"], "compile check")
        if not args.skip_tests:
            run([sys.executable, "run_tests.py"], "regression suite")
        park_previous_build(DIST_APP)
        run([sys.executable, "-m", "PyInstaller", "-y", "UsageWidget.spec"], "pyinstaller build")
    elif not DIST_APP.exists():
        raise SystemExit(f"--skip-build given but {DIST_APP} does not exist")

    metrics = verify_payload(DIST_APP)
    print(
        f"==> payload verified: exe {metrics['exe_bytes'] / 1024 / 1024:.1f} MB, "
        f"{metrics['internal_files']} runtime files, {metrics['fonts']} bundled font(s)"
    )

    staged = stage_payload(DIST_APP)
    staged_metrics = verify_payload(staged)
    if staged_metrics["internal_files"] != metrics["internal_files"]:
        raise SystemExit("staging copy is incomplete: file count changed during copy")

    RELEASE_DIR.mkdir(exist_ok=True)
    zip_path = RELEASE_DIR / f"UsageWidget-{version}-win64.zip"
    entries = write_zip(staged, zip_path)
    verify_zip(zip_path, entries)

    checksums = RELEASE_DIR / f"SHA256SUMS-{version}.txt"
    checksums.write_text(
        f"{sha256_of(zip_path)}  {zip_path.name}\n"
        f"{sha256_of(DIST_APP / 'UsageWidget.exe')}  UsageWidget/UsageWidget.exe\n",
        encoding="utf-8",
    )

    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"==> package: {zip_path} ({size_mb:.1f} MB, {entries} entries)")
    print(f"==> checksums: {checksums}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
