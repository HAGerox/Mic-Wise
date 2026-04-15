"""Pydantic schemas for the Mic-Wise API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """High-level backend health snapshot."""

    status: str
    audio_engine_running: bool


class SettingsResponse(BaseModel):
    """Serialized show-wide settings."""

    model_config = ConfigDict(from_attributes=True)

    sample_rate: int
    channel_count: int
    buffer_duration_sec: int
    block_size: int
    audio_source_mode: str
    multi_listen_enabled: bool
    active_mode: str


class SettingsUpdateRequest(BaseModel):
    """Persisted UI-level settings for the active show."""

    multi_listen_enabled: bool | None = None
    active_mode: str | None = None


class ChannelResponse(BaseModel):
    """Serialized channel settings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    name: str
    photo_path: str | None
    input_index: int | None
    is_record_enabled: bool
    sort_index: int
    position_x: float
    position_y: float


class ChannelCreateRequest(BaseModel):
    """Fields that may be supplied when creating a channel."""

    name: str | None = None
    photo_path: str | None = None
    input_index: int | None = None
    is_record_enabled: bool | None = None


class ChannelUpdateRequest(BaseModel):
    """Fields that may be updated for a channel."""

    name: str | None = None
    photo_path: str | None = None
    input_index: int | None = None
    is_record_enabled: bool | None = None
    sort_index: int | None = None
    position_x: float | None = None
    position_y: float | None = None


class SceneResponse(BaseModel):
    """Serialized scene information."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    order_index: int


class MeterChannelSnapshot(BaseModel):
    """Meter values for a single channel."""

    channel: int
    rms: float
    peak: float


class MeterSnapshotResponse(BaseModel):
    """Serialized live meter snapshot."""

    write_head: int
    window_frames: int
    channels: list[MeterChannelSnapshot]


class ChannelWaveformResponse(BaseModel):
    """Waveform preview data for a single channel."""

    channel_id: int
    input_index: int | None
    seconds: float
    points: list[float]


class WebRTCOfferRequest(BaseModel):
    """Offer payload sent by the browser for audio streaming."""

    sdp: str
    type: str
    channel_ids: list[int]
    replay_seconds: float = 0.0


class WebRTCAnswerResponse(BaseModel):
    """Answer payload returned to the browser for audio streaming."""

    sdp: str
    type: str
