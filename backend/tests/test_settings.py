"""Tests for runtime path selection in Mic-Wise settings."""

from __future__ import annotations

from app.core.settings import MicWiseSettings


def test_buffer_path_uses_runtime_directory(tmp_path) -> None:
    settings = MicWiseSettings(
        data_directory=tmp_path / "show-data",
        runtime_directory=tmp_path / "runtime-data",
        port=8123,
        show_filename="show.micwise",
        buffer_filename="audio.buffer",
    )

    assert settings.show_path == tmp_path / "show-data" / "show.micwise"
    assert settings.runtime_buffer_directory == tmp_path / "runtime-data" / "port-8123"
    assert settings.buffer_path == tmp_path / "runtime-data" / "port-8123" / "audio.buffer"


def test_ensure_directories_creates_runtime_buffer_directory(tmp_path) -> None:
    settings = MicWiseSettings(
        data_directory=tmp_path / "show-data",
        runtime_directory=tmp_path / "runtime-data",
        port=9001,
    )

    settings.ensure_directories()

    assert settings.data_directory.is_dir()
    assert settings.runtime_buffer_directory.is_dir()