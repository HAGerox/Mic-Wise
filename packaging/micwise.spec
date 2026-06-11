# PyInstaller spec for the standalone Mic-Wise server.
#
# Build with:  python packaging/build.py        (recommended; builds frontend too)
# or directly: pyinstaller packaging/micwise.spec --noconfirm
#
# Per-platform output:
#   macOS    -> dist/MicWise.app (double-clickable bundle; server logs go to
#               the per-user data directory) plus dist/MicWise/ for terminal use
#   Windows  -> dist/MicWise.exe (single file; shows a console with the logs,
#               closing the console stops the server)
#   Linux    -> dist/MicWise (single executable file)

import sys
import sysconfig
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

project_root = Path(SPECPATH).resolve().parent
backend_root = project_root / "backend"
frontend_dist = project_root / "frontend" / "dist"

is_macos = sys.platform == "darwin"
is_windows = sys.platform.startswith("win")
# One-file is the friendliest hand-off on Windows/Linux; macOS gets a real
# .app bundle instead (one-file and .app bundles are mutually exclusive).
onefile = not is_macos
icon = (
    project_root / "build" / "icons" / "MicWise.icns"
    if is_macos
    else project_root / "build" / "icons" / "MicWise.ico"
    if is_windows
    else None
)

if icon is not None and not icon.exists():
    raise SystemExit(
        f"{icon} is missing - build with `python packaging/build.py` so the "
        "platform icon is generated first.",
    )

if not (frontend_dist / "index.html").exists():
    raise SystemExit(
        "frontend/dist/index.html is missing - run `npm run build` in frontend/ "
        "or use packaging/build.py which does it for you.",
    )

hiddenimports = [
    # uvicorn's import-by-name internals
    *collect_submodules("uvicorn"),
    # Python 3.14 currently needs the broad fallback; earlier versions use
    # PyInstaller's NumPy hook and avoid scanning NumPy's large test tree.
    *(collect_submodules("numpy") if sys.version_info >= (3, 14) else []),
    # stdlib lazy imports missed on Python 3.14
    *collect_submodules("ctypes"),
    *collect_submodules("encodings"),
    # PyAV/aiortc cython modules import each other by name at init time
    *collect_submodules("av"),
    *collect_submodules("aiortc"),
    # sqlalchemy loads dialects via entry-point-style plugin names
    *collect_submodules("sqlalchemy.dialects"),
    # anyio picks its asyncio backend by string at runtime (StaticFiles)
    *collect_submodules("anyio"),
    # optional integrations imported lazily / by plugin name
    "mido.backends.rtmidi",
    "zeroconf",
    "ifaddr",
    "aiosqlite",
    "greenlet",
]

# zoneinfo (pulled in via pydantic) needs the platform sysconfig data module,
# which PyInstaller does not always collect on its own.
_sysconfigdata_name = getattr(sysconfig, "_get_sysconfigdata_name", lambda: None)()
if _sysconfigdata_name:
    hiddenimports.append(_sysconfigdata_name)

a = Analysis(
    [str(project_root / "packaging" / "micwise_app.py")],
    pathex=[str(backend_root)],
    binaries=[],
    datas=[(str(frontend_dist), "frontend/dist")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

pyz = PYZ(a.pure)

if onefile:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.datas,
        [],
        name="MicWise",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=True,
        icon=str(icon) if icon else None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="MicWise",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        icon=str(icon),
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        name="MicWise",
    )

    app = BUNDLE(
        coll,
        name="MicWise.app",
        icon=str(icon),
        bundle_identifier="com.micwise.server",
        info_plist={
            "CFBundleName": "MicWise",
            "CFBundleDisplayName": "Mic-Wise",
            "CFBundleShortVersionString": "0.1.0",
            "NSHighResolutionCapable": True,
            # Required for CoreAudio input capture from a bundled app;
            # without it macOS refuses the microphone permission prompt.
            "NSMicrophoneUsageDescription": (
                "Mic-Wise monitors audio interface inputs for live metering "
                "and listening."
            ),
        },
    )
