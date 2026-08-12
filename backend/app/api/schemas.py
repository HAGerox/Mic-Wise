"""Pydantic schemas for the Mic-Wise API."""

from __future__ import annotations

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from app.sync.service import ExternalSyncEvent


SceneSyncTransport = Literal["off", "osc", "midi", "both"]


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
    audio_input_device: str | None
    master_gain_db: float
    multi_listen_enabled: bool
    active_mode: str
    scene_mode_enabled: bool
    active_scene_id: int | None
    external_sync_enabled: bool
    external_sync_transport: str
    external_sync_osc_host: str
    external_sync_osc_port: int
    external_sync_midi_input_name: str | None
    alerts_enabled: bool
    alert_popup_duration_sec: int
    rchat_enabled: bool
    rchat_flash_enabled: bool
    rchat_hold_seconds: int
    rchat_interface_ip: str | None
    rchat_username: str


class SettingsUpdateRequest(BaseModel):
    """Persisted UI-level settings for the active show."""

    sample_rate: int | None = None
    channel_count: int | None = None
    buffer_duration_sec: int | None = None
    block_size: int | None = None
    audio_source_mode: str | None = None
    audio_input_device: str | None = None
    master_gain_db: float | None = None
    multi_listen_enabled: bool | None = None
    active_mode: str | None = None
    scene_mode_enabled: bool | None = None
    active_scene_id: int | None = None
    external_sync_enabled: bool | None = None
    external_sync_transport: SceneSyncTransport | None = None
    external_sync_osc_host: str | None = None
    external_sync_osc_port: int | None = None
    external_sync_midi_input_name: str | None = None
    alerts_enabled: bool | None = None
    alert_popup_duration_sec: int | None = None
    rchat_enabled: bool | None = None
    rchat_flash_enabled: bool | None = None
    rchat_hold_seconds: int | None = None
    rchat_interface_ip: str | None = None
    rchat_username: str | None = None


class NetworkInterfaceResponse(BaseModel):
    """Serialized IPv4 network interface."""

    name: str
    display_name: str
    ipv4_address: str
    broadcast_address: str | None
    is_loopback: bool


class RChatTestResponse(BaseModel):
    """Details returned after sending an RChat test packet."""

    status: str
    sender_ip: str
    username: str
    source_port: int
    destinations: list[str]
    destination_port: int
    error: str | None = None


class AudioInputDeviceResponse(BaseModel):
    """Serialized capture device information for setup UIs."""

    selector: str
    name: str
    hostapi_name: str
    display_name: str
    max_input_channels: int
    default_sample_rate: int
    is_default: bool


class ChannelResponse(BaseModel):
    """Serialized channel settings."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    number: int
    name: str
    photo_path: str | None
    input_index: int | None
    gain_db: float
    is_record_enabled: bool
    sort_index: int
    position_x: float
    position_y: float


class ChannelCreateRequest(BaseModel):
    """Fields that may be supplied when creating a channel."""

    name: str | None = None
    photo_path: str | None = None
    input_index: int | None = None
    gain_db: float | None = None
    is_record_enabled: bool | None = None


class ChannelUpdateRequest(BaseModel):
    """Fields that may be updated for a channel."""

    name: str | None = None
    photo_path: str | None = None
    input_index: int | None = None
    gain_db: float | None = None
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
    sync_osc_address: str | None
    sync_osc_argument: str | None
    sync_midi_pattern: str | None
    channel_assignments: list[SceneChannelAssignmentResponse] = []


class SceneChannelAssignmentResponse(BaseModel):
    """Serialized scene-channel state mapping."""

    model_config = ConfigDict(from_attributes=True)

    channel_id: int
    state: str


class SceneChannelAssignmentRequest(BaseModel):
    """A channel state assignment for a scene."""

    channel_id: int
    state: str


class SceneCreateRequest(BaseModel):
    """Fields that may be supplied when creating a scene."""

    name: str | None = None
    sync_osc_address: str | None = None
    sync_osc_argument: str | None = None
    sync_midi_pattern: str | None = None
    channel_assignments: list[SceneChannelAssignmentRequest] | None = None


class SceneUpdateRequest(BaseModel):
    """Fields that may be updated for a scene."""

    name: str | None = None
    order_index: int | None = None
    sync_osc_address: str | None = None
    sync_osc_argument: str | None = None
    sync_midi_pattern: str | None = None
    channel_assignments: list[SceneChannelAssignmentRequest] | None = None


class SceneSyncStatusResponse(BaseModel):
    """Runtime status for external scene sync listeners."""

    enabled: bool
    transport: str
    osc_listening: bool
    osc_endpoint: str | None
    midi_listening: bool
    midi_input_name: str | None
    last_event_summary: str | None
    last_matched_scene_id: int | None
    error: str | None


class SceneSyncEventRequest(BaseModel):
    """Normalized external cue payload for manual injection and testing."""

    transport: Literal["osc", "midi"]
    osc_address: str | None = None
    osc_argument: str | None = None
    midi_message_type: str | None = None
    midi_channel: int | None = None
    midi_data_1: int | None = None
    midi_data_2: int | None = None

    def to_event(self) -> ExternalSyncEvent:
        """Convert the API payload into the runtime event dataclass."""
        return ExternalSyncEvent(**self.model_dump())


class SceneSyncEventResponse(BaseModel):
    """Result of applying an external sync cue to the current show."""

    matched_scene_id: int | None
    matched_scene_name: str | None
    active_scene_id: int | None
    changed: bool


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


class AudioAlertResponse(BaseModel):
    """Active alert mapped onto the current display channels."""

    id: str
    kind: str
    severity: str
    input_index: int
    title: str
    message: str
    score: float
    started_at: float
    updated_at: float
    channel_ids: list[int]
    channel_numbers: list[int]
    channel_names: list[str]


class ShowfileSceneAssignmentPayload(BaseModel):
    """Portable scene assignment entry inside an exported showfile."""

    channel_number: int
    state: str


class ShowfileChannelPayload(BaseModel):
    """Portable channel data stored in a showfile."""

    number: int
    name: str
    photo_path: str | None = None
    input_index: int | None = None
    gain_db: float = 0.0
    is_record_enabled: bool = True
    sort_index: int = 0
    position_x: float = 0.0
    position_y: float = 0.0


class ShowfileScenePayload(BaseModel):
    """Portable scene data stored in a showfile."""

    name: str
    order_index: int
    sync_osc_address: str | None = None
    sync_osc_argument: str | None = None
    sync_midi_pattern: str | None = None
    channel_assignments: list[ShowfileSceneAssignmentPayload] = []


class ShowfileSettingsPayload(BaseModel):
    """Portable show-wide settings stored in a showfile."""

    sample_rate: int
    channel_count: int
    buffer_duration_sec: int
    block_size: int
    audio_source_mode: str
    audio_input_device: str | None = None
    master_gain_db: float
    multi_listen_enabled: bool
    active_mode: str
    scene_mode_enabled: bool
    active_scene_order_index: int | None = None
    external_sync_enabled: bool
    external_sync_transport: SceneSyncTransport
    external_sync_osc_host: str
    external_sync_osc_port: int
    external_sync_midi_input_name: str | None = None
    alerts_enabled: bool = True
    alert_popup_duration_sec: int = 6
    rchat_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("rchat_enabled", "radioworld_enabled"),
    )
    rchat_flash_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("rchat_flash_enabled", "radioworld_flash_enabled"),
    )
    rchat_hold_seconds: int = Field(
        default=8,
        validation_alias=AliasChoices("rchat_hold_seconds", "radioworld_hold_seconds"),
    )
    rchat_interface_ip: str | None = Field(
        default=None,
        validation_alias=AliasChoices("rchat_interface_ip", "radioworld_interface_ip"),
    )
    rchat_username: str = "Mic-Wise"


class ShowfilePayload(BaseModel):
    """Portable Mic-Wise showfile used for browser import/export."""

    format: str
    version: int
    exported_at: str | None = None
    settings: ShowfileSettingsPayload
    channels: list[ShowfileChannelPayload]
    scenes: list[ShowfileScenePayload]


class ShowfileImportResponse(BaseModel):
    """Summary returned after importing a showfile."""

    status: str
    channels: int
    scenes: int


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
