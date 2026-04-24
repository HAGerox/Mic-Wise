"""External OSC/MIDI scene sync helpers and runtime services."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

try:
    import mido
except ImportError:  # pragma: no cover - optional runtime integration
    mido = None

try:
    from pythonosc.dispatcher import Dispatcher
    from pythonosc.osc_server import AsyncIOOSCUDPServer
except ImportError:  # pragma: no cover - optional runtime integration
    AsyncIOOSCUDPServer = None
    Dispatcher = None

from app.database.repository import get_settings, list_scenes, update_settings
from app.database.session import DatabaseManager


SYNC_TRANSPORTS = {"off", "osc", "midi", "both"}


@dataclass(slots=True)
class ExternalSyncEvent:
    """Normalized external cue event used for scene matching."""

    transport: str
    osc_address: str | None = None
    osc_argument: str | None = None
    midi_message_type: str | None = None
    midi_channel: int | None = None
    midi_data_1: int | None = None
    midi_data_2: int | None = None


@dataclass(slots=True)
class SceneSyncResult:
    """Outcome of matching an external event against show scenes."""

    matched_scene_id: int | None
    matched_scene_name: str | None
    active_scene_id: int | None
    changed: bool


@dataclass(slots=True)
class SceneSyncStatusSnapshot:
    """Runtime status for the external sync service."""

    enabled: bool = False
    transport: str = "off"
    osc_listening: bool = False
    osc_endpoint: str | None = None
    midi_listening: bool = False
    midi_input_name: str | None = None
    last_event_summary: str | None = None
    last_matched_scene_id: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the status snapshot for API responses."""
        return asdict(self)


@dataclass(slots=True)
class MidiPattern:
    """Parsed MIDI scene-trigger pattern."""

    message_type: str
    channel: int | None
    data_1: int | None
    data_2: int | None


def _normalise_transport(value: str | None) -> str:
    transport = (value or "off").strip().lower()
    return transport if transport in SYNC_TRANSPORTS else "off"


def _normalise_optional_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _transport_matches(configured_transport: str, event_transport: str) -> bool:
    if configured_transport == "off":
        return False
    if configured_transport == "both":
        return event_transport in {"osc", "midi"}
    return configured_transport == event_transport


def parse_midi_pattern(pattern: str | None) -> MidiPattern | None:
    """Parse a compact MIDI trigger description.

    Supported forms:
    - ``program_change:12``
    - ``control_change:1:42``
    - ``note_on:1:60:127``
    """
    raw_pattern = _normalise_optional_text(pattern)
    if raw_pattern is None:
        return None

    parts = [part.strip().lower() for part in raw_pattern.split(":")]
    if len(parts) not in {2, 3, 4}:
        raise ValueError("MIDI pattern must have 2, 3, or 4 colon-separated parts")

    message_type = parts[0]
    if not message_type:
        raise ValueError("MIDI message type is required")

    try:
        if len(parts) == 2:
            return MidiPattern(
                message_type=message_type,
                channel=None,
                data_1=int(parts[1]),
                data_2=None,
            )
        if len(parts) == 3:
            return MidiPattern(
                message_type=message_type,
                channel=int(parts[1]),
                data_1=int(parts[2]),
                data_2=None,
            )
        return MidiPattern(
            message_type=message_type,
            channel=int(parts[1]),
            data_1=int(parts[2]),
            data_2=int(parts[3]),
        )
    except ValueError as error:
        raise ValueError("MIDI pattern values must be integers") from error


def scene_matches_event(scene: object, event: ExternalSyncEvent) -> bool:
    """Return whether a scene should react to the external event."""
    if event.transport == "osc":
        scene_address = _normalise_optional_text(getattr(scene, "sync_osc_address", None))
        if scene_address is None or scene_address != _normalise_optional_text(event.osc_address):
            return False
        expected_argument = _normalise_optional_text(getattr(scene, "sync_osc_argument", None))
        if expected_argument is None:
            return True
        return expected_argument == _normalise_optional_text(event.osc_argument)

    if event.transport == "midi":
        midi_pattern = parse_midi_pattern(getattr(scene, "sync_midi_pattern", None))
        if midi_pattern is None:
            return False
        if midi_pattern.message_type != (event.midi_message_type or "").strip().lower():
            return False
        if midi_pattern.channel is not None and midi_pattern.channel != event.midi_channel:
            return False
        if midi_pattern.data_1 is not None and midi_pattern.data_1 != event.midi_data_1:
            return False
        if midi_pattern.data_2 is not None and midi_pattern.data_2 != event.midi_data_2:
            return False
        return True

    return False


def summarise_event(event: ExternalSyncEvent) -> str:
    """Return a compact human-readable summary for diagnostics."""
    if event.transport == "osc":
        if event.osc_argument is None:
            return f"OSC {event.osc_address or '(missing address)'}"
        return f"OSC {event.osc_address or '(missing address)'} {event.osc_argument}"

    values = [
        f"type={event.midi_message_type or 'unknown'}",
        f"channel={event.midi_channel if event.midi_channel is not None else '-'}",
        f"data1={event.midi_data_1 if event.midi_data_1 is not None else '-'}",
    ]
    if event.midi_data_2 is not None:
        values.append(f"data2={event.midi_data_2}")
    return f"MIDI {' '.join(values)}"


async def apply_scene_sync_event(
    database: DatabaseManager,
    event: ExternalSyncEvent,
) -> SceneSyncResult:
    """Apply an external sync event to the active show settings when matched."""
    settings = await get_settings(database)
    if not bool(getattr(settings, "external_sync_enabled", False)):
        return SceneSyncResult(
            matched_scene_id=None,
            matched_scene_name=None,
            active_scene_id=getattr(settings, "active_scene_id", None),
            changed=False,
        )

    configured_transport = _normalise_transport(getattr(settings, "external_sync_transport", "off"))
    if not _transport_matches(configured_transport, event.transport):
        return SceneSyncResult(
            matched_scene_id=None,
            matched_scene_name=None,
            active_scene_id=getattr(settings, "active_scene_id", None),
            changed=False,
        )

    scenes = await list_scenes(database)
    matched_scene = next((scene for scene in scenes if scene_matches_event(scene, event)), None)
    if matched_scene is None:
        return SceneSyncResult(
            matched_scene_id=None,
            matched_scene_name=None,
            active_scene_id=getattr(settings, "active_scene_id", None),
            changed=False,
        )

    if getattr(settings, "active_scene_id", None) == matched_scene.id:
        return SceneSyncResult(
            matched_scene_id=matched_scene.id,
            matched_scene_name=matched_scene.name,
            active_scene_id=matched_scene.id,
            changed=False,
        )

    updated_settings = await update_settings(database, {"active_scene_id": matched_scene.id})
    return SceneSyncResult(
        matched_scene_id=matched_scene.id,
        matched_scene_name=matched_scene.name,
        active_scene_id=updated_settings.active_scene_id,
        changed=True,
    )


class SceneSyncService:
    """Runtime service that optionally listens for OSC/MIDI cues."""

    def __init__(self, database: DatabaseManager) -> None:
        self._database = database
        self._loop: asyncio.AbstractEventLoop | None = None
        self._osc_transport = None
        self._midi_port = None
        self._status = SceneSyncStatusSnapshot()

    @property
    def status(self) -> SceneSyncStatusSnapshot:
        """Return the latest runtime status snapshot."""
        return self._status

    async def start(self) -> None:
        """Capture the current loop and configure listeners from persisted settings."""
        self._loop = asyncio.get_running_loop()
        await self.reload()

    async def stop(self) -> None:
        """Stop active listeners and reset runtime state."""
        await self._stop_osc_listener()
        self._stop_midi_listener()

    async def reload(self) -> None:
        """Reconfigure listeners after settings changes."""
        await self._stop_osc_listener()
        self._stop_midi_listener()

        self._status = SceneSyncStatusSnapshot()
        settings = await get_settings(self._database)
        self._status.enabled = bool(getattr(settings, "external_sync_enabled", False))
        self._status.transport = _normalise_transport(getattr(settings, "external_sync_transport", "off"))
        self._status.midi_input_name = _normalise_optional_text(
            getattr(settings, "external_sync_midi_input_name", None),
        )

        if not self._status.enabled or self._status.transport == "off":
            return

        if self._status.transport in {"osc", "both"}:
            await self._start_osc_listener(settings)

        if self._status.transport in {"midi", "both"}:
            self._start_midi_listener(settings)

    async def handle_event(self, event: ExternalSyncEvent) -> SceneSyncResult:
        """Apply a normalized event and update diagnostic status."""
        result = await apply_scene_sync_event(self._database, event)
        self._status.last_event_summary = summarise_event(event)
        self._status.last_matched_scene_id = result.matched_scene_id
        if result.changed:
            self._status.error = None
        return result

    async def _start_osc_listener(self, settings: object) -> None:
        if AsyncIOOSCUDPServer is None or Dispatcher is None:
            self._status.error = "Install python-osc to enable OSC scene sync."
            return

        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self._handle_osc_message)

        host = getattr(settings, "external_sync_osc_host", "0.0.0.0")
        port = int(getattr(settings, "external_sync_osc_port", 53001))
        server = AsyncIOOSCUDPServer((host, port), dispatcher, self._loop or asyncio.get_running_loop())
        try:
            self._osc_transport, _ = await server.create_serve_endpoint()
        except OSError as error:
            self._status.error = str(error)
            return

        self._status.osc_listening = True
        self._status.osc_endpoint = f"{host}:{port}"

    async def _stop_osc_listener(self) -> None:
        if self._osc_transport is not None:
            self._osc_transport.close()
            self._osc_transport = None
        self._status.osc_listening = False
        self._status.osc_endpoint = None

    def _start_midi_listener(self, settings: object) -> None:
        midi_input_name = _normalise_optional_text(
            getattr(settings, "external_sync_midi_input_name", None),
        )
        if midi_input_name is None:
            self._status.error = "Set a MIDI input name to enable MIDI scene sync."
            return

        if mido is None:
            self._status.error = "Install mido to enable MIDI scene sync."
            return

        try:
            self._midi_port = mido.open_input(midi_input_name, callback=self._handle_midi_message)
        except Exception as error:  # pragma: no cover - backend availability depends on host system
            self._status.error = str(error)
            return

        self._status.midi_listening = True
        self._status.midi_input_name = midi_input_name

    def _stop_midi_listener(self) -> None:
        if self._midi_port is not None:
            try:
                self._midi_port.close()
            finally:
                self._midi_port = None
        self._status.midi_listening = False

    def _handle_osc_message(self, address: str, *osc_args: object) -> None:
        event = ExternalSyncEvent(
            transport="osc",
            osc_address=address,
            osc_argument=_normalise_optional_text(osc_args[0]) if osc_args else None,
        )
        asyncio.create_task(self.handle_event(event))

    def _handle_midi_message(self, message: Any) -> None:
        if self._loop is None:
            return

        data_1 = getattr(message, "note", None)
        if data_1 is None:
            data_1 = getattr(message, "control", None)
        if data_1 is None:
            data_1 = getattr(message, "program", None)

        data_2 = getattr(message, "velocity", None)
        if data_2 is None:
            data_2 = getattr(message, "value", None)

        channel = getattr(message, "channel", None)
        if channel is not None:
            channel = int(channel) + 1

        event = ExternalSyncEvent(
            transport="midi",
            midi_message_type=_normalise_optional_text(getattr(message, "type", None)),
            midi_channel=channel,
            midi_data_1=data_1,
            midi_data_2=data_2,
        )
        self._loop.call_soon_threadsafe(
            asyncio.create_task,
            self.handle_event(event),
        )
