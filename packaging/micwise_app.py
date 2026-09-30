"""Frozen app launcher with exclusive ownership and a standard macOS lifecycle."""
from __future__ import annotations

import multiprocessing
import os
import signal
import sys
import threading
import time
import webbrowser
from urllib.request import urlopen
import json


def _ui_url(host: str, port: int) -> str:
    host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    if ":" in host:
        host = f"[{host}]"
    return f"http://{host}:{port}/"


def _wait_and_open_browser(host: str, port: int) -> None:
    """Wait for completed FastAPI startup, rather than an open TCP port."""
    url = _ui_url(host, port)
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            with urlopen(url + "api/health", timeout=1) as response:
                if json.load(response).get("app") == "micwise":
                    webbrowser.open(url)
                    return
        except (OSError, ValueError):
            pass
        time.sleep(0.25)


def _has_console() -> bool:
    if sys.stdout is None or sys.stderr is None:
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, OSError, ValueError):
        return False


def _start_browser_when_ready(host: str, port: int) -> None:
    if os.environ.get("MICWISE_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
        threading.Thread(target=_wait_and_open_browser, args=(host, port), daemon=True).start()


def _redirect_output_to_log_file(data_directory) -> None:
    data_directory.mkdir(parents=True, exist_ok=True)
    path = data_directory / "micwise-server.log"
    if path.exists() and path.stat().st_size > 5 * 1024 * 1024:
        path.replace(data_directory / "micwise-server.previous.log")
    log_file = path.open("a", buffering=1, encoding="utf-8")
    log_file.write(f"\n--- Mic-Wise started {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    sys.stdout = sys.stderr = log_file
    os.environ["MICWISE_LOG_FILE"] = str(path)


def _acquire_instance_lock(data_directory):
    """Hold a kernel lock for this show store, including across app replacements."""
    import fcntl

    data_directory.mkdir(parents=True, exist_ok=True)
    handle = (data_directory / "micwise.lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError("Mic-Wise is already running. Quit the existing app before opening another copy.")
    return handle


def _show_error(message: str) -> None:
    print(message, file=sys.stderr)
    if sys.platform == "darwin" and not _has_console():
        import AppKit

        application = AppKit.NSApplication.sharedApplication()
        application.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
        application.activateIgnoringOtherApps_(True)
        alert = AppKit.NSAlert.alloc().init()
        alert.setMessageText_("Mic-Wise could not start")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("OK")
        alert.runModal()


def _run_macos_app(server, listener, url: str) -> None:
    """Keep Cocoa responsive to Quit/reopen and surface server startup failures."""
    import AppKit
    import Foundation

    # A browser UI leaves the Cocoa app without a visible window. App Nap can
    # then throttle its server/meter timers during a show, even with clients.
    process_info = Foundation.NSProcessInfo.processInfo()
    activity = process_info.beginActivityWithOptions_reason_(
        Foundation.NSActivityUserInitiated,
        "Live microphone monitoring and network backups",
    )
    failure: list[str] = []

    def run_server() -> None:
        try:
            server.run(sockets=[listener])
        except BaseException as exc:
            failure.append(str(exc))

    server_thread = threading.Thread(target=run_server, name="micwise-server", daemon=True)

    def shutdown_server() -> None:
        server.should_exit = True
        server_thread.join(timeout=10)

    class MicWiseAppDelegate(AppKit.NSObject):
        def applicationDidFinishLaunching_(self, notification):
            server_thread.start()
            _start_browser_when_ready(server.config.host, server.config.port)
            self.timer = Foundation.NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                0.5, self, "checkServer:", None, True,
            )

        def checkServer_(self, timer):
            if not server_thread.is_alive():
                timer.invalidate()
                _show_error((failure[0] if failure else "The server stopped unexpectedly.") +
                            "\nSee ~/Library/Application Support/Mic-Wise/micwise-server.log for details.")
                AppKit.NSApplication.sharedApplication().terminate_(None)

        def applicationShouldHandleReopen_hasVisibleWindows_(self, application, visible):
            if server.started:
                webbrowser.open(url)
            return False

        def openInterface_(self, sender):
            if server.started:
                webbrowser.open(url)

        def applicationShouldTerminate_(self, sender):
            shutdown_server()
            return AppKit.NSTerminateNow

    def handle_sigterm(signum, frame):
        shutdown_server()
        AppKit.NSApplication.sharedApplication().stop_(None)
        # Wake the Cocoa loop so the launcher can release its lock/socket.
        AppKit.NSApplication.sharedApplication().terminate_(None)

    signal.signal(signal.SIGTERM, handle_sigterm)
    application = AppKit.NSApplication.sharedApplication()
    application.setActivationPolicy_(AppKit.NSApplicationActivationPolicyRegular)
    delegate = MicWiseAppDelegate.alloc().init()
    application.setDelegate_(delegate)
    main_menu = AppKit.NSMenu.alloc().init()
    app_menu_item = AppKit.NSMenuItem.alloc().init()
    main_menu.addItem_(app_menu_item)
    app_menu = AppKit.NSMenu.alloc().initWithTitle_("Mic-Wise")
    open_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Open Mic-Wise", "openInterface:", "o")
    open_item.setTarget_(delegate)
    app_menu.addItem_(open_item)
    app_menu.addItem_(AppKit.NSMenuItem.separatorItem())
    quit_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Quit Mic-Wise", "terminate:", "q")
    quit_item.setTarget_(application)
    app_menu.addItem_(quit_item)
    app_menu_item.setSubmenu_(app_menu)
    application.setMainMenu_(main_menu)
    try:
        application.run()
    finally:
        process_info.endActivity_(activity)


def main() -> None:
    # Must precede imports and any lock acquisition: frozen audio workers reenter here.
    multiprocessing.freeze_support()
    from app.core.settings import MicWiseSettings

    settings = MicWiseSettings()
    has_console = _has_console()
    if not has_console:
        _redirect_output_to_log_file(settings.data_directory)
    lock = None
    listener = None
    try:
        if sys.platform == "darwin":
            lock = _acquire_instance_lock(settings.data_directory)
        import uvicorn
        from app.main import app

        config = uvicorn.Config(app, host=settings.host, port=settings.port, log_level="info",
                                timeout_graceful_shutdown=5)
        # Bind before lifespan can create/truncate the shared audio buffer.
        try:
            listener = config.bind_socket()
        except SystemExit as exc:
            raise RuntimeError(f"Port {settings.port} is in use. Quit the other server and reopen Mic-Wise.") from exc
        server = uvicorn.Server(config)
        print(f"Show data directory: {settings.data_directory}")
        if sys.platform == "darwin" and not has_console:
            _run_macos_app(server, listener, _ui_url(settings.host, settings.port))
        else:
            _start_browser_when_ready(settings.host, settings.port)
            server.run(sockets=[listener])
    except Exception as exc:
        _show_error(str(exc))
        raise SystemExit(1) from exc
    finally:
        if listener is not None:
            listener.close()
        if lock is not None:
            lock.close()


if __name__ == "__main__":
    main()
