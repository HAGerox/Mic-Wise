"""Build a standalone Mic-Wise app for the current platform.

Usage:
    python packaging/build.py            # build frontend + standalone app
    python packaging/build.py --skip-frontend

Run it on the platform you are targeting (PyInstaller does not cross-compile):
macOS produces ``dist/MicWise.app``, Windows produces ``dist/MicWise.exe``,
and Linux produces ``dist/MicWise``. Copy the artifact to the show computer
and run it. The server starts, and the operator UI opens in the default
browser.
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

    if sys.platform == "darwin":
        # The .app needs a Cocoa event loop so Dock > Quit / Cmd-Q work.
        try:
            import AppKit  # noqa: F401
        except ImportError:
            run(
                [sys.executable, "-m", "pip", "install", "pyobjc-framework-Cocoa"],
                cwd=PROJECT_ROOT,
            )


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

    dist = PROJECT_ROOT / "dist"
    print()
    if sys.platform == "darwin":
        print(f"Done. macOS app bundle: {dist / 'MicWise.app'}")
        print("Copy MicWise.app to the show computer and double-click it.")
        print("(First launch on a new machine: right-click > Open to pass Gatekeeper.)")
        print(f"Terminal-friendly build also available: {dist / 'MicWise' / 'MicWise'}")
    elif sys.platform.startswith("win"):
        print(f"Done. Single-file app: {dist / 'MicWise.exe'}")
        print("Copy MicWise.exe to the show computer and double-click it.")
        print("Closing its console window stops the server.")
    else:
        print(f"Done. Single-file app: {dist / 'MicWise'}")
        print("Copy the MicWise file to the show computer and run it.")


if __name__ == "__main__":
    main()
