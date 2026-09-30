"""Regression coverage for frozen app ownership and readiness."""
from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest

from app.core.settings import default_data_directory

spec = importlib.util.spec_from_file_location(
    "micwise_launcher", Path(__file__).resolve().parents[2] / "packaging" / "micwise_app.py",
)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


def test_frozen_macos_show_data_survives_app_replacement(monkeypatch, tmp_path):
    import sys

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(sys, "executable", "/Applications/MicWise.app/Contents/MacOS/MicWise")
    first = default_data_directory()
    monkeypatch.setattr(sys, "executable", "/Volumes/New Alpha/MicWise.app/Contents/MacOS/MicWise")
    assert default_data_directory() == first == tmp_path / "Library/Application Support/Mic-Wise"


@pytest.mark.skipif(__import__('sys').platform == 'win32', reason="POSIX app lock")
def test_second_app_cannot_own_show_data_and_lock_releases(tmp_path):
    first = launcher._acquire_instance_lock(tmp_path)
    try:
        with pytest.raises(RuntimeError, match="already running"):
            launcher._acquire_instance_lock(tmp_path)
    finally:
        first.close()
    replacement = launcher._acquire_instance_lock(tmp_path)
    replacement.close()


def test_browser_opens_only_after_micwise_health_response(monkeypatch):
    replies = iter([b'{"app":"other"}', b'{"app":"micwise","status":"ok"}'])
    opened = []
    monkeypatch.setattr(launcher, "urlopen", lambda *args, **kwargs: io.BytesIO(next(replies)))
    monkeypatch.setattr(launcher.time, "sleep", lambda delay: None)
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    launcher._wait_and_open_browser("0.0.0.0", 8123)
    assert opened == ["http://127.0.0.1:8123/"]


def test_browser_url_supports_ipv6():
    assert launcher._ui_url("::1", 8000) == "http://[::1]:8000/"
