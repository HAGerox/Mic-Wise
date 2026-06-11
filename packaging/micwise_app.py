"""Standalone Mic-Wise entry point for frozen (PyInstaller) builds.

Runs the same FastAPI app as ``backend/run.py`` but imports the application
object directly (no import-string reload machinery) and opens the operator's
browser once the server is reachable.
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import socket
import sys
import threading
import time
import webbrowser


def _wait_and_open_browser(host: str, port: int) -> None:
    """Open the UI once the server accepts connections (best effort)."""
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((probe_host, port), timeout=1.0):
                break
        except OSError:
            time.sleep(0.25)
    else:
        return
    webbrowser.open(f"http://{probe_host}:{port}/")


def _has_console() -> bool:
    """Return whether stdout is a usable interactive console."""
    if sys.stdout is None or sys.stderr is None:
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, OSError, ValueError):
        return False


def _redirect_output_to_log_file(data_directory) -> None:
    """Send stdout/stderr to a log file when no console is attached.

    Windowed bundles (the macOS .app) have no visible console, and uvicorn's
    logging would otherwise be lost - or crash outright where the streams
    are ``None``.
    """
    data_directory.mkdir(parents=True, exist_ok=True)
    log_file = open(  # noqa: SIM115 - kept open for the process lifetime
        data_directory / "micwise-server.log",
        "a",
        buffering=1,
        encoding="utf-8",
    )
    log_file.write(f"\n--- Mic-Wise started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    sys.stdout = log_file
    sys.stderr = log_file


def _run_macos_app(server) -> bool:
    """Host the server inside an NSApplication run loop on macOS.

    A plain uvicorn process inside a windowed .app cannot answer the Quit
    Apple Event, so Dock > Quit and Cmd-Q appear to hang and operators are
    forced to Force Quit. Running the Cocoa event loop on the main thread
    (server on a worker thread) makes Quit shut the server down cleanly.
    Returns False when pyobjc is unavailable so callers can fall back.
    """
    try:
        import AppKit
    except ImportError:
        return False

    server_thread = threading.Thread(target=server.run, name="micwise-server", daemon=True)

    def shutdown_server(timeout: float = 10.0) -> None:
        server.should_exit = True
        server_thread.join(timeout=timeout)

    class MicWiseAppDelegate(AppKit.NSObject):
        def applicationDidFinishLaunching_(self, notification) -> None:
            del notification
            server_thread.start()

        def applicationShouldTerminate_(self, sender):
            del sender
            shutdown_server()
            return AppKit.NSTerminateNow

    def install_main_menu(application) -> None:
        """Install the standard app menu, including the Cmd-Q key equivalent."""
        main_menu = AppKit.NSMenu.alloc().init()
        app_menu_item = AppKit.NSMenuItem.alloc().init()
        main_menu.addItem_(app_menu_item)

        app_menu = AppKit.NSMenu.alloc().initWithTitle_("MicWise")
        quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit MicWise",
            "terminate:",
            "q",
        )
        quit_item.setTarget_(application)
        app_menu.addItem_(quit_item)
        app_menu_item.setSubmenu_(app_menu)
        application.setMainMenu_(main_menu)

    def handle_sigterm(signum, frame) -> None:
        del signum, frame
        shutdown_server()
        os._exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    application = AppKit.NSApplication.sharedApplication()
    application.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    install_main_menu(application)
    delegate = MicWiseAppDelegate.alloc().init()
    application.setDelegate_(delegate)
    application.run()
    return True


def main() -> None:
    multiprocessing.freeze_support()

    import uvicorn

    from app.core.settings import MicWiseSettings
    from app.main import app

    settings = MicWiseSettings()
    has_console = _has_console()
    if not has_console:
        _redirect_output_to_log_file(settings.data_directory)
    if os.environ.get("MICWISE_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
        threading.Thread(
            target=_wait_and_open_browser,
            args=(settings.host, settings.port),
            daemon=True,
        ).start()

    print(f"Mic-Wise server starting on http://{settings.host}:{settings.port}/")
    print(f"Show data directory: {settings.data_directory}")

    config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="info")
    server = uvicorn.Server(config)

    if sys.platform == "darwin" and not has_console and _run_macos_app(server):
        return
    server.run()


if __name__ == "__main__":
    main()
