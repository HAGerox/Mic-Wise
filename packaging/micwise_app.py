"""Standalone Mic-Wise entry point for frozen (PyInstaller) builds.

Runs the same FastAPI app as ``backend/run.py`` but imports the application
object directly (no import-string reload machinery) and opens the operator's
browser once the server is reachable.
"""

from __future__ import annotations

import multiprocessing
import os
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


def main() -> None:
    multiprocessing.freeze_support()

    import uvicorn

    from app.core.settings import MicWiseSettings
    from app.main import app

    settings = MicWiseSettings()
    if os.environ.get("MICWISE_NO_BROWSER", "").strip().lower() not in {"1", "true", "yes"}:
        threading.Thread(
            target=_wait_and_open_browser,
            args=(settings.host, settings.port),
            daemon=True,
        ).start()

    print(f"Mic-Wise server starting on http://{settings.host}:{settings.port}/")
    print(f"Show data directory: {settings.data_directory}")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level="info")


if __name__ == "__main__":
    main()
