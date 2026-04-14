"""Runtime configuration for the Mic-Wise backend."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MicWiseSettings(BaseSettings):
    """Application settings loaded from environment variables when present."""

    model_config = SettingsConfigDict(
        env_prefix="MICWISE_",
        env_file=".env",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8000
    data_directory: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "data",
    )
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
    def buffer_path(self) -> Path:
        """Return the mmap audio buffer file path."""
        return self.data_directory / self.buffer_filename

    def ensure_directories(self) -> None:
        """Ensure the backend data directory exists."""
        self.data_directory.mkdir(parents=True, exist_ok=True)
