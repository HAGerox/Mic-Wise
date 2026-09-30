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
import hashlib
from importlib.metadata import distributions
import json
import os
import platform
import plistlib
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIRECTORY = Path(os.environ.get("MICWISE_DIST_DIRECTORY", str(PROJECT_ROOT / "dist"))).resolve()
VERSION_INFO = runpy.run_path(str(PROJECT_ROOT / "backend" / "app" / "version.py"))
RELEASE_VERSION = f"{VERSION_INFO['VERSION']}-{VERSION_INFO['RELEASE_LABEL']}"
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
            str(DIST_DIRECTORY),
            "--workpath",
            str(PROJECT_ROOT / "build" / platform.machine()),
        ],
        cwd=PROJECT_ROOT,
    )
    if sys.platform == "darwin":
        app = DIST_DIRECTORY / "MicWise.app"
        resources = app / "Contents" / "Resources"
        shutil.copyfile(PROJECT_ROOT / "LICENSE", resources / "LICENSE.txt")
        (resources / "Source.txt").write_text(
            f"Mic-Wise {RELEASE_VERSION}\n"
            f"Source: https://github.com/HAGerox/Mic-Wise/tree/v{RELEASE_VERSION}\n"
            "Licensed under GNU GPL version 3; see LICENSE.txt.\n",
            encoding="utf-8",
        )
        # Preserve the notices supplied by the installed Python distributions.
        for package in distributions():
            for member in package.files or []:
                lower_name = member.name.lower()
                if ".dist-info/" not in str(member) or not (
                    "/licenses/" in str(member)
                    or lower_name.startswith(("license", "licence", "copying", "notice"))
                ):
                    continue
                source = package.locate_file(member)
                if source.is_file():
                    notice_path = str(member).split(".dist-info/", 1)[1]
                    destination = resources / "licenses" / package.metadata["Name"] / notice_path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
        # Cloud-synced workspaces can attach Finder metadata after PyInstaller
        # signs nested frameworks. Clear it and refresh the ad-hoc signature.
        run(["xattr", "-cr", str(app)], cwd=PROJECT_ROOT)
        identity = os.environ.get("MICWISE_SIGNING_IDENTITY", "-")
        if identity == "-":
            run(["codesign", "--force", "--deep", "--sign", "-", str(app)], cwd=PROJECT_ROOT)
        else:
            # Refresh the outer signature after adding notices. Nested binaries
            # retain the signatures applied by PyInstaller.
            run(["codesign", "--force", "--sign", identity, "--options", "runtime",
                 "--timestamp", "--entitlements", str(PROJECT_ROOT / "packaging" / "entitlements.plist"),
                 str(app)], cwd=PROJECT_ROOT)
        run(["codesign", "--verify", "--deep", "--strict", str(app)], cwd=PROJECT_ROOT)

        # PyInstaller uses this directory while assembling the .app. The app
        # bundle is the sole distributable, so do not leave a second copy.
        shutil.rmtree(DIST_DIRECTORY / "MicWise", ignore_errors=True)


def package_macos_app() -> Path:
    """Produce a standard drag-to-Applications image, optionally notarized."""
    dist = DIST_DIRECTORY
    app = dist / "MicWise.app"
    profile = os.environ.get("MICWISE_NOTARY_PROFILE")
    with (app / "Contents" / "Info.plist").open("rb") as handle:
        minimum_macos = plistlib.load(handle)["LSMinimumSystemVersion"]
    if profile:
        upload = PROJECT_ROOT / "build" / "notary-upload.zip"
        run(["ditto", "-c", "-k", "--keepParent", str(app), str(upload)], PROJECT_ROOT)
        run(["xcrun", "notarytool", "submit", str(upload), "--keychain-profile", profile,
             "--wait"], PROJECT_ROOT)
        run(["xcrun", "stapler", "staple", str(app)], PROJECT_ROOT)
        run(["spctl", "--assess", "--type", "execute", "--verbose", str(app)], PROJECT_ROOT)
    arch = platform.machine()
    image = dist / f"MicWise-{RELEASE_VERSION}-macOS-{arch}.dmg"
    image.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="micwise-installer-") as temporary:
        staging = Path(temporary)
        run(["ditto", str(app), str(staging / app.name)], PROJECT_ROOT)
        (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
        (staging / "Install Mic-Wise.txt").write_text(
            f"Mic-Wise {RELEASE_VERSION} ({arch}), macOS {minimum_macos} or later\n\n"
            "Drag MicWise.app onto Applications, then eject this disk image.\n"
            "Open MicWise from Applications. Its operator interface opens in your browser.\n"
            "Allow microphone access when you select a hardware input in Setup.\n"
            "To update: quit Mic-Wise, replace the app in Applications, then reopen it.\n"
            "Shows and photos remain in ~/Library/Application Support/Mic-Wise.\n"
            "Backups: Setup > Export show, or use Stage Backup on the same network.\n"
            f"Source: https://github.com/HAGerox/Mic-Wise/tree/v{RELEASE_VERSION}\n"
            + ("" if profile else
               "\nThis alpha is not notarized. If macOS blocks it, open System Settings >\n"
               "Privacy & Security and use Open Anyway after attempting to open the app.\n"),
            encoding="utf-8",
        )
        run(["hdiutil", "create", "-volname", "Mic-Wise", "-srcfolder", str(staging),
             "-format", "UDZO", str(image)], PROJECT_ROOT)
    run(["hdiutil", "verify", str(image)], PROJECT_ROOT)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    image.with_suffix(".dmg.sha256").write_text(f"{digest}  {image.name}\n", encoding="utf-8")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=PROJECT_ROOT, text=True).strip())
    (dist / "release-info.json").write_text(json.dumps({
        "version": RELEASE_VERSION, "architecture": arch, "revision": revision,
        "working_tree_changes_included": dirty, "notarized": bool(profile),
        "minimum_macos": minimum_macos,
        "installer": image.name, "sha256": digest,
    }, indent=2) + "\n", encoding="utf-8")
    dependencies = sorted(f"{package.metadata['Name']}=={package.version}" for package in distributions())
    (dist / "build-requirements.txt").write_text("\n".join(dependencies) + "\n", encoding="utf-8")
    return image


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="reuse the existing frontend/dist build",
    )
    arguments = parser.parse_args()

    if os.environ.get("MICWISE_NOTARY_PROFILE") and not os.environ.get("MICWISE_SIGNING_IDENTITY"):
        raise SystemExit("MICWISE_NOTARY_PROFILE requires MICWISE_SIGNING_IDENTITY (Developer ID Application)")

    if not arguments.skip_frontend:
        build_frontend()
    build_app()

    dist = DIST_DIRECTORY
    print()
    if sys.platform == "darwin":
        installer = package_macos_app()
        print(f"Done. macOS app bundle: {dist / 'MicWise.app'}")
        print(f"Installer: {installer}")
        print("Open the disk image and drag MicWise.app to Applications.")
    elif sys.platform.startswith("win"):
        print(f"Done. Single-file app: {dist / 'MicWise.exe'}")
        print("Copy MicWise.exe to the show computer and double-click it.")
        print("Closing its console window stops the server.")
    else:
        print(f"Done. Single-file app: {dist / 'MicWise'}")
        print("Copy the MicWise file to the show computer and run it.")


if __name__ == "__main__":
    main()
