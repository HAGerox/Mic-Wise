"""Database models backing the Mic-Wise show file."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


def utcnow() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SettingsRecord(Base):
    """Singleton row holding active show-wide settings."""

    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_count: Mapped[int] = mapped_column(Integer, nullable=False)
    buffer_duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    block_size: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_source_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="synthetic")
    audio_input_device: Mapped[str | None] = mapped_column(String(255), nullable=True)
    master_gain_db: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    multi_listen_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="monitor")
    scene_mode_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active_scene_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_sync_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    external_sync_transport: Mapped[str] = mapped_column(String(16), nullable=False, default="off")
    external_sync_osc_host: Mapped[str] = mapped_column(String(128), nullable=False, default="0.0.0.0")
    external_sync_osc_port: Mapped[int] = mapped_column(Integer, nullable=False, default=53001)
    external_sync_midi_input_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    alert_popup_duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    radioworld_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    radioworld_flash_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    radioworld_hold_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    radioworld_interface_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class Channel(Base):
    """A monitored radio microphone channel."""

    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("number", name="uq_channels_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    input_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gain_db: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_record_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    scene_assignments: Mapped[list[SceneChannel]] = relationship(
        back_populates="channel",
        cascade="all, delete-orphan",
    )


class Scene(Base):
    """A theatre scene used to prioritize channel visibility."""

    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("order_index", name="uq_scenes_order_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sync_osc_address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_osc_argument: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sync_midi_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)

    channel_assignments: Mapped[list[SceneChannel]] = relationship(
        back_populates="scene",
        cascade="all, delete-orphan",
    )


class SceneChannel(Base):
    """Scene-specific state for a channel."""

    __tablename__ = "scene_channels"

    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), primary_key=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="off")

    scene: Mapped[Scene] = relationship(back_populates="channel_assignments")
    channel: Mapped[Channel] = relationship(back_populates="scene_assignments")
