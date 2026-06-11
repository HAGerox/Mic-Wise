"""Runtime configuration for the Mic-Wise backend."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from tempfile import gettempdir

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def is_frozen_app() -> bool:
    """Return whether the backend runs from a frozen (PyInstaller) bundle."""
    return bool(getattr(sys, "frozen", False))


def default_data_directory() -> Path:
    """Return the persistent show-data directory.

    Source checkouts keep show files under ``backend/data`` as before. Frozen
    standalone builds must not write next to the bundled (read-only and
    possibly temporary) application files, so they use the platform user-data
    location instead.
    """
    if not is_frozen_app():
        return Path(__file__).resolve().parents[2] / "data"

    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "Mic-Wise"


def default_runtime_directory() -> Path:
    """Return a local runtime directory safe for memory-mapped buffers."""
    return Path(gettempdir()) / "mic-wise-runtime"


class MicWiseSettings(BaseSettings):
    """Application settings loaded from environment variables when present."""

    model_config = SettingsConfigDict(
        env_prefix="MICWISE_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    data_directory: Path = Field(default_factory=default_data_directory)
    runtime_directory: Path = Field(default_factory=default_runtime_directory)
    show_filename: str = "default.micwise"
    buffer_filename: str = "audio.buffer"
    default_sample_rate: int = 48_000
    default_channel_count: int = 16
    default_buffer_duration_sec: int = 300
    default_block_size: int = 480
    audio_source_mode: str = "synthetic"
    meter_window_ms: int = 100
    meter_poll_interval_ms: int = 50
    zeroconf_enabled: bool = False

    @property
    def show_path(self) -> Path:
        """Return the SQLite show file path."""
        return self.data_directory / self.show_filename

    @property
    def runtime_buffer_directory(self) -> Path:
        """Return the local runtime folder used for the shared audio buffer."""
        return self.runtime_directory / f"port-{self.port}"

    @property
    def buffer_path(self) -> Path:
        """Return the mmap audio buffer file path."""
        return self.runtime_buffer_directory / self.buffer_filename

    def ensure_directories(self) -> None:
        """Ensure the persistent and runtime backend directories exist."""
        self.data_directory.mkdir(parents=True, exist_ok=True)
        self.runtime_buffer_directory.mkdir(parents=True, exist_ok=True)
