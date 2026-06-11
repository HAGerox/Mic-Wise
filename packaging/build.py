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
ICON_SOURCE = PROJECT_ROOT / "packaging" / "assets" / "micwise-icon-source.png"
ICON_OUTPUT_DIRECTORY = PROJECT_ROOT / "build" / "icons"
ICON_ARTWORK_SCALE = 1.16
MACOS_ICON_INSET = 96


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


def ensure_build_dependencies() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pyinstaller"], cwd=PROJECT_ROOT)

    try:
        import PIL  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pillow"], cwd=PROJECT_ROOT)

    if sys.platform == "darwin":
        # The .app needs a Cocoa event loop so Dock > Quit / Cmd-Q work.
        try:
            import AppKit  # noqa: F401
        except ImportError:
            run(
                [sys.executable, "-m", "pip", "install", "pyobjc-framework-Cocoa"],
                cwd=PROJECT_ROOT,
            )


def prepare_app_icon() -> None:
    if sys.platform != "darwin" and not sys.platform.startswith("win"):
        return

    if not ICON_SOURCE.exists():
        raise SystemExit(f"App icon source is missing: {ICON_SOURCE}")

    from PIL import Image, ImageChops, ImageDraw

    ICON_OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with Image.open(ICON_SOURCE) as source:
        source = source.convert("RGBA")
        side = min(source.size)
        left = (source.width - side) // 2
        top = (source.height - side) // 2
        square = source.crop((left, top, left + side, top + side))
        artwork_side = round(side / ICON_ARTWORK_SCALE)
        artwork_left = (side - artwork_side) // 2
        square = square.crop(
            (
                artwork_left,
                artwork_left,
                artwork_left + artwork_side,
                artwork_left + artwork_side,
            ),
        )
        master = square.resize((1024, 1024), Image.Resampling.LANCZOS)

        if sys.platform == "darwin":
            # Legacy ICNS files are not automatically clipped to the modern
            # macOS app-icon silhouette or optically sized like modern icons.
            # Place the artwork inside an inset platform-style enclosure.
            enclosure_size = master.width - (MACOS_ICON_INSET * 2)
            enclosure = master.resize(
                (enclosure_size, enclosure_size),
                Image.Resampling.LANCZOS,
            )
            master = Image.new("RGBA", master.size, (0, 0, 0, 0))
            master.alpha_composite(
                enclosure,
                (MACOS_ICON_INSET, MACOS_ICON_INSET),
            )

            scale = 4
            mask = Image.new("L", (master.width * scale, master.height * scale), 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                (
                    MACOS_ICON_INSET * scale,
                    MACOS_ICON_INSET * scale,
                    (master.width - MACOS_ICON_INSET) * scale - 1,
                    (master.height - MACOS_ICON_INSET) * scale - 1,
                ),
                radius=185 * scale,
                fill=255,
            )
            mask = mask.resize(master.size, Image.Resampling.LANCZOS)
            master.putalpha(ImageChops.multiply(master.getchannel("A"), mask))
            output = ICON_OUTPUT_DIRECTORY / "MicWise.icns"
            master.save(output, format="ICNS")
        else:
            output = ICON_OUTPUT_DIRECTORY / "MicWise.ico"
            master.save(
                output,
                format="ICO",
                sizes=[
                    (16, 16),
                    (24, 24),
                    (32, 32),
                    (48, 48),
                    (64, 64),
                    (128, 128),
                    (256, 256),
                ],
            )

    print(f"Prepared app icon: {output}")


def build_app() -> None:
    ensure_build_dependencies()
    prepare_app_icon()
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
    if sys.platform == "darwin":
        app = PROJECT_ROOT / "dist" / "MicWise.app"
        # Cloud-synced workspaces can attach Finder metadata after PyInstaller
        # signs nested frameworks. Clear it and refresh the ad-hoc signature.
        run(["xattr", "-cr", str(app)], cwd=PROJECT_ROOT)
        run(["codesign", "--force", "--deep", "--sign", "-", str(app)], cwd=PROJECT_ROOT)
        run(["codesign", "--verify", "--deep", "--strict", str(app)], cwd=PROJECT_ROOT)

        # PyInstaller uses this directory while assembling the .app. The app
        # bundle is the sole distributable, so do not leave a second copy.
        shutil.rmtree(PROJECT_ROOT / "dist" / "MicWise", ignore_errors=True)


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
    elif sys.platform.startswith("win"):
        print(f"Done. Single-file app: {dist / 'MicWise.exe'}")
        print("Copy MicWise.exe to the show computer and double-click it.")
        print("Closing its console window stops the server.")
    else:
        print(f"Done. Single-file app: {dist / 'MicWise'}")
        print("Copy the MicWise file to the show computer and run it.")


if __name__ == "__main__":
    main()
