"""Build a standalone Mic-Wise app for the current platform.

Usage:
    python packaging/build.py            # build frontend + standalone app
    python packaging/build.py --skip-frontend

Run it on the platform you are targeting (PyInstaller does not cross-compile):
macOS produces dist/MicWise for macOS, Windows for Windows, Linux for Linux.
The result is a self-contained folder: copy it to the show computer (or zip
it), then run MicWise (MicWise.exe on Windows). The server starts, and the
operator UI opens in the default browser.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(command)}  (cwd={cwd})")
    subprocess.run(command, cwd=cwd, check=True)


def build_frontend() -> None:
    npm = shutil.which("npm")
    if npm is None:
        raise SystemExit("npm is required to build the frontend (install Node.js)")
    frontend = PROJECT_ROOT / "frontend"
    if not (frontend / "node_modules").exists():
        run([npm, "ci", "--no-audit", "--no-fund"], cwd=frontend)
    run([npm, "run", "build"], cwd=frontend)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pyinstaller"], cwd=PROJECT_ROOT)


def build_app() -> None:
    ensure_pyinstaller()
    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(PROJECT_ROOT / "packaging" / "micwise.spec"),
            "--noconfirm",
            "--distpath",
            str(PROJECT_ROOT / "dist"),
            "--workpath",
            str(PROJECT_ROOT / "build"),
        ],
        cwd=PROJECT_ROOT,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="reuse the existing frontend/dist build",
    )
    arguments = parser.parse_args()

    if not arguments.skip_frontend:
        build_frontend()
    build_app()

    app_dir = PROJECT_ROOT / "dist" / "MicWise"
    print()
    print(f"Done. Standalone app: {app_dir}")
    print("Copy that folder to the show computer and run MicWise inside it.")


if __name__ == "__main__":
    main()
