"""Database bootstrap and query helpers for the active Mic-Wise show file."""

from __future__ import annotations

import re

from sqlalchemy import delete, select, text
from sqlalchemy.orm import selectinload

from app.core.settings import MicWiseSettings
from app.database.models import Channel, Scene, SceneChannel, SettingsRecord
from app.database.session import DatabaseManager


DEFAULT_CHANNEL_NAME_PATTERN = re.compile(r"^Channel (\d+)$")
SCENE_CHANNEL_STATES = {"off", "ready", "onstage"}
SHOWFILE_FORMAT = "micwise-showfile"
SHOWFILE_FORMAT_VERSION = 1


def _normalise_optional_text(value: object | None) -> str | None:
    """Normalize empty string-like values into ``None``."""
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


async def _ensure_show_file_compatibility(database: DatabaseManager) -> None:
    """Add newly introduced columns to existing show files."""

    async with database.engine.begin() as connection:
        settings_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(settings)"))
            ).fetchall()
        }
        if settings_columns and "master_gain_db" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN master_gain_db FLOAT NOT NULL DEFAULT 0.0",
                ),
            )
        if settings_columns and "scene_mode_enabled" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN scene_mode_enabled BOOLEAN NOT NULL DEFAULT 0",
                ),
            )
        if settings_columns and "active_scene_id" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN active_scene_id INTEGER",
                ),
            )
        if settings_columns and "external_sync_enabled" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN external_sync_enabled BOOLEAN NOT NULL DEFAULT 0",
                ),
            )
        if settings_columns and "external_sync_transport" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN external_sync_transport VARCHAR(16) NOT NULL DEFAULT 'off'",
                ),
            )
        if settings_columns and "external_sync_osc_host" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN external_sync_osc_host VARCHAR(128) NOT NULL DEFAULT '0.0.0.0'",
                ),
            )
        if settings_columns and "external_sync_osc_port" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN external_sync_osc_port INTEGER NOT NULL DEFAULT 53001",
                ),
            )
        if settings_columns and "external_sync_midi_input_name" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN external_sync_midi_input_name VARCHAR(128)",
                ),
            )
        if settings_columns and "audio_input_device" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN audio_input_device VARCHAR(255)",
                ),
            )
        if settings_columns and "alerts_enabled" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN alerts_enabled BOOLEAN NOT NULL DEFAULT 1",
                ),
            )
        if settings_columns and "alert_popup_duration_sec" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN alert_popup_duration_sec INTEGER NOT NULL DEFAULT 6",
                ),
            )
        if settings_columns and "radioworld_enabled" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN radioworld_enabled BOOLEAN NOT NULL DEFAULT 0",
                ),
            )
        if settings_columns and "radioworld_flash_enabled" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN radioworld_flash_enabled BOOLEAN NOT NULL DEFAULT 0",
                ),
            )
        if settings_columns and "radioworld_hold_seconds" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN radioworld_hold_seconds INTEGER NOT NULL DEFAULT 8",
                ),
            )
        if settings_columns and "radioworld_interface_ip" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN radioworld_interface_ip VARCHAR(45)",
                ),
            )

        channel_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(channels)"))
            ).fetchall()
        }
        if channel_columns and "gain_db" not in channel_columns:
            await connection.execute(
                text(
                    "ALTER TABLE channels ADD COLUMN gain_db FLOAT NOT NULL DEFAULT 0.0",
                ),
            )

        scene_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(scenes)"))
            ).fetchall()
        }
        if scene_columns and "sync_osc_address" not in scene_columns:
            await connection.execute(
                text(
                    "ALTER TABLE scenes ADD COLUMN sync_osc_address VARCHAR(255)",
                ),
            )
        if scene_columns and "sync_osc_argument" not in scene_columns:
            await connection.execute(
                text(
                    "ALTER TABLE scenes ADD COLUMN sync_osc_argument VARCHAR(255)",
                ),
            )
        if scene_columns and "sync_midi_pattern" not in scene_columns:
            await connection.execute(
                text(
                    "ALTER TABLE scenes ADD COLUMN sync_midi_pattern VARCHAR(255)",
                ),
            )


async def initialise_show_file(
    database: DatabaseManager,
    settings: MicWiseSettings,
) -> SettingsRecord:
    """Create default settings, channels, and a starter scene if absent."""
    await database.create_schema()
    await _ensure_show_file_compatibility(database)

    async with database.session() as session:
        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is None:
            settings_row = SettingsRecord(
                id=1,
                sample_rate=settings.default_sample_rate,
                channel_count=settings.default_channel_count,
                buffer_duration_sec=settings.default_buffer_duration_sec,
                block_size=settings.default_block_size,
                audio_source_mode=settings.audio_source_mode,
                audio_input_device=None,
                master_gain_db=0.0,
                scene_mode_enabled=False,
                external_sync_enabled=False,
                external_sync_transport="off",
                external_sync_osc_host="0.0.0.0",
                external_sync_osc_port=53001,
                alerts_enabled=True,
                alert_popup_duration_sec=6,
                radioworld_enabled=False,
                radioworld_flash_enabled=False,
                radioworld_hold_seconds=8,
                radioworld_interface_ip=None,
            )
            session.add(settings_row)
            await session.flush()

        existing_channels = list(
            (
                await session.scalars(select(Channel).order_by(Channel.number))
            ).all(),
        )
        if not existing_channels:
            for number in range(1, settings_row.channel_count + 1):
                session.add(
                    Channel(
                        number=number,
                        name=f"Channel {number}",
                        input_index=number - 1,
                        gain_db=0.0,
                        is_record_enabled=True,
                        sort_index=number - 1,
                    ),
                )

        existing_scene_count = len((await session.scalars(select(Scene))).all())
        if existing_scene_count == 0:
            starter_scene = Scene(name="Scene 1", order_index=0)
            session.add(starter_scene)
            await session.flush()
            if settings_row.active_scene_id is None:
                settings_row.active_scene_id = starter_scene.id

        await session.commit()
        await session.refresh(settings_row)
        return settings_row


def _normalise_scene_assignments(assignments: list[dict[str, object]] | None) -> dict[int, str]:
    """Validate scene-channel state payloads and discard explicitly off entries."""
    mapping: dict[int, str] = {}
    for assignment in assignments or []:
        channel_id = int(assignment["channel_id"])
        state = str(assignment.get("state", "off")).strip().lower()
        if state not in SCENE_CHANNEL_STATES:
            raise ValueError(f"Unsupported scene channel state: {state}")
        if state == "off":
            mapping.pop(channel_id, None)
            continue
        mapping[channel_id] = state
    return mapping


async def _apply_channel_sequence(session, ordered_channels: list[Channel]) -> None:
    """Reassign channel numbers without tripping SQLite's unique constraint."""
    previous_numbers = {channel.id: channel.number for channel in ordered_channels}
    for temp_index, channel in enumerate(ordered_channels, start=1):
        channel.number = -temp_index
        channel.sort_index = temp_index - 1

    await session.flush()

    for sort_index, channel in enumerate(ordered_channels):
        previous_number = previous_numbers[channel.id]
        next_number = sort_index + 1
        channel.sort_index = sort_index
        channel.number = next_number
        if DEFAULT_CHANNEL_NAME_PATTERN.match(channel.name) and channel.name == f"Channel {previous_number}":
            channel.name = f"Channel {next_number}"


async def _apply_scene_order(session, ordered_scenes: list[Scene]) -> None:
    """Reassign scene order indexes without violating unique constraints."""
    for temp_index, scene in enumerate(ordered_scenes, start=1):
        scene.order_index = -temp_index

    await session.flush()

    for order_index, scene in enumerate(ordered_scenes):
        scene.order_index = order_index


async def _replace_scene_assignments(
    session,
    scene: Scene,
    assignments: list[dict[str, object]] | None,
) -> None:
    """Replace all persisted per-channel states for a scene."""
    mapping = _normalise_scene_assignments(assignments)
    await session.execute(delete(SceneChannel).where(SceneChannel.scene_id == scene.id))
    for channel_id, state in mapping.items():
        session.add(SceneChannel(scene_id=scene.id, channel_id=channel_id, state=state))
    await session.flush()


async def get_settings(database: DatabaseManager) -> SettingsRecord:
    """Fetch the singleton settings row."""
    async with database.session() as session:
        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is None:
            raise RuntimeError("Show settings have not been initialised")
        return settings_row


async def list_channels(database: DatabaseManager) -> list[Channel]:
    """Return all channels ordered for UI display."""
    async with database.session() as session:
        result = await session.scalars(
            select(Channel).order_by(Channel.sort_index, Channel.number),
        )
        return list(result.all())


async def list_scenes(database: DatabaseManager) -> list[Scene]:
    """Return all scenes ordered by their show order."""
    async with database.session() as session:
        result = await session.scalars(
            select(Scene)
            .options(selectinload(Scene.channel_assignments))
            .order_by(Scene.order_index, Scene.id),
        )
        return list(result.all())


async def get_scene(database: DatabaseManager, scene_id: int) -> Scene | None:
    """Fetch a single scene with its assignment rows."""
    async with database.session() as session:
        return await session.scalar(
            select(Scene)
            .options(selectinload(Scene.channel_assignments))
            .where(Scene.id == scene_id),
        )


async def get_channel(database: DatabaseManager, channel_id: int) -> Channel | None:
    """Fetch a single channel by primary key."""
    async with database.session() as session:
        return await session.get(Channel, channel_id)


async def get_channels_by_ids(
    database: DatabaseManager,
    channel_ids: list[int],
) -> list[Channel]:
    """Fetch a set of channels by ID."""
    if not channel_ids:
        return []

    async with database.session() as session:
        result = await session.scalars(select(Channel).where(Channel.id.in_(channel_ids)))
        return list(result.all())


async def create_channel(
    database: DatabaseManager,
    changes: dict[str, object] | None = None,
) -> Channel:
    """Create a new display channel appended to the current monitor layout."""
    channel_changes = changes or {}

    async with database.session() as session:
        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is None:
            raise RuntimeError("Show settings have not been initialised")

        existing_channels = list(
            (
                await session.scalars(
                    select(Channel).order_by(Channel.sort_index, Channel.number, Channel.id),
                )
            ).all(),
        )
        next_number = len(existing_channels) + 1
        default_input_index = next_number - 1 if next_number <= settings_row.channel_count else None
        channel = Channel(
            number=next_number,
            name=f"Channel {next_number}",
            input_index=default_input_index,
            gain_db=0.0,
            is_record_enabled=True,
            sort_index=len(existing_channels),
        )
        session.add(channel)
        await session.flush()

        for field_name, value in channel_changes.items():
            setattr(channel, field_name, value)

        if not channel.name.strip():
            channel.name = f"Channel {next_number}"

        await session.commit()
        await session.refresh(channel)
        return channel


async def delete_channel(database: DatabaseManager, channel_id: int) -> bool:
    """Delete a display channel and compact numbering and layout order."""
    async with database.session() as session:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            return False

        await session.delete(channel)
        await session.flush()

        remaining_channels = list(
            (
                await session.scalars(
                    select(Channel).order_by(Channel.sort_index, Channel.number, Channel.id),
                )
            ).all(),
        )

        await _apply_channel_sequence(session, remaining_channels)

        await session.commit()
        return True


async def update_channel(
    database: DatabaseManager,
    channel_id: int,
    changes: dict[str, object],
) -> Channel | None:
    """Update a channel and return the saved record."""
    async with database.session() as session:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            return None

        for field_name, value in changes.items():
            setattr(channel, field_name, value)

        await session.commit()
        await session.refresh(channel)
        return channel


async def update_settings(
    database: DatabaseManager,
    changes: dict[str, object],
) -> SettingsRecord:
    """Update and return the singleton settings row."""
    async with database.session() as session:
        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is None:
            raise RuntimeError("Show settings have not been initialised")

        for field_name, value in changes.items():
            if field_name in {"audio_input_device", "external_sync_midi_input_name", "radioworld_interface_ip"}:
                value = _normalise_optional_text(value)
            setattr(settings_row, field_name, value)

        await session.commit()
        await session.refresh(settings_row)
        return settings_row


def _serialise_showfile_settings(settings_row: SettingsRecord, active_scene: Scene | None) -> dict[str, object]:
    """Convert persisted settings into a portable showfile payload."""
    return {
        "sample_rate": settings_row.sample_rate,
        "channel_count": settings_row.channel_count,
        "buffer_duration_sec": settings_row.buffer_duration_sec,
        "block_size": settings_row.block_size,
        "audio_source_mode": settings_row.audio_source_mode,
        "audio_input_device": settings_row.audio_input_device,
        "master_gain_db": settings_row.master_gain_db,
        "multi_listen_enabled": settings_row.multi_listen_enabled,
        "active_mode": settings_row.active_mode,
        "scene_mode_enabled": settings_row.scene_mode_enabled,
        "active_scene_order_index": active_scene.order_index if active_scene is not None else None,
        "external_sync_enabled": settings_row.external_sync_enabled,
        "external_sync_transport": settings_row.external_sync_transport,
        "external_sync_osc_host": settings_row.external_sync_osc_host,
        "external_sync_osc_port": settings_row.external_sync_osc_port,
        "external_sync_midi_input_name": settings_row.external_sync_midi_input_name,
        "alerts_enabled": settings_row.alerts_enabled,
        "alert_popup_duration_sec": settings_row.alert_popup_duration_sec,
        "radioworld_enabled": settings_row.radioworld_enabled,
        "radioworld_flash_enabled": settings_row.radioworld_flash_enabled,
        "radioworld_hold_seconds": settings_row.radioworld_hold_seconds,
        "radioworld_interface_ip": settings_row.radioworld_interface_ip,
    }


async def export_showfile(database: DatabaseManager) -> dict[str, object]:
    """Export the current show as a portable JSON-friendly payload."""
    settings_row = await get_settings(database)
    channels = await list_channels(database)
    scenes = await list_scenes(database)
    channel_by_id = {channel.id: channel for channel in channels}
    active_scene = next((scene for scene in scenes if scene.id == settings_row.active_scene_id), None)

    return {
        "format": SHOWFILE_FORMAT,
        "version": SHOWFILE_FORMAT_VERSION,
        "exported_at": settings_row.updated_at.isoformat(),
        "settings": _serialise_showfile_settings(settings_row, active_scene),
        "channels": [
            {
                "number": channel.number,
                "name": channel.name,
                "photo_path": channel.photo_path,
                "input_index": channel.input_index,
                "gain_db": channel.gain_db,
                "is_record_enabled": channel.is_record_enabled,
                "sort_index": channel.sort_index,
                "position_x": channel.position_x,
                "position_y": channel.position_y,
            }
            for channel in channels
        ],
        "scenes": [
            {
                "name": scene.name,
                "order_index": scene.order_index,
                "sync_osc_address": scene.sync_osc_address,
                "sync_osc_argument": scene.sync_osc_argument,
                "sync_midi_pattern": scene.sync_midi_pattern,
                "channel_assignments": [
                    {
                        "channel_number": channel_by_id[assignment.channel_id].number,
                        "state": assignment.state,
                    }
                    for assignment in scene.channel_assignments
                    if assignment.channel_id in channel_by_id
                ],
            }
            for scene in scenes
        ],
    }


def _normalise_showfile_payload(payload: dict[str, object]) -> dict[str, object]:
    """Validate a showfile-like mapping enough for repository import."""
    if str(payload.get("format") or "").strip() != SHOWFILE_FORMAT:
        raise ValueError("Unsupported Mic-Wise showfile format")

    version = int(payload.get("version") or 0)
    if version != SHOWFILE_FORMAT_VERSION:
        raise ValueError(f"Unsupported Mic-Wise showfile version: {version}")

    settings_payload = payload.get("settings")
    if not isinstance(settings_payload, dict):
        raise ValueError("Showfile settings payload is missing")

    channels_payload = payload.get("channels")
    if not isinstance(channels_payload, list):
        raise ValueError("Showfile channels payload is missing")

    scenes_payload = payload.get("scenes")
    if not isinstance(scenes_payload, list):
        raise ValueError("Showfile scenes payload is missing")

    return {
        "settings": settings_payload,
        "channels": channels_payload,
        "scenes": scenes_payload,
    }


async def import_showfile(database: DatabaseManager, payload: dict[str, object]) -> SettingsRecord:
    """Replace the current show contents with an imported showfile payload."""
    normalised_payload = _normalise_showfile_payload(payload)
    settings_payload = normalised_payload["settings"]
    channels_payload = sorted(
        normalised_payload["channels"],
        key=lambda channel: (int(channel.get("sort_index", channel.get("number", 0)) or 0), int(channel.get("number", 0) or 0)),
    )
    scenes_payload = sorted(
        normalised_payload["scenes"],
        key=lambda scene: int(scene.get("order_index", 0) or 0),
    )

    async with database.session() as session:
        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is None:
            settings_row = SettingsRecord(id=1, sample_rate=48_000, channel_count=16, buffer_duration_sec=300, block_size=480)
            session.add(settings_row)
            await session.flush()

        await session.execute(delete(SceneChannel))
        await session.execute(delete(Scene))
        await session.execute(delete(Channel))
        await session.flush()

        number_to_channel_id: dict[int, int] = {}
        for sort_index, channel_payload in enumerate(channels_payload):
            channel_number = int(channel_payload.get("number") or (sort_index + 1))
            channel = Channel(
                number=channel_number,
                name=str(channel_payload.get("name") or f"Channel {channel_number}").strip() or f"Channel {channel_number}",
                photo_path=_normalise_optional_text(channel_payload.get("photo_path")),
                input_index=int(channel_payload["input_index"]) if channel_payload.get("input_index") is not None else None,
                gain_db=float(channel_payload.get("gain_db") or 0.0),
                is_record_enabled=bool(channel_payload.get("is_record_enabled", True)),
                sort_index=int(channel_payload.get("sort_index", sort_index) or sort_index),
                position_x=float(channel_payload.get("position_x") or 0.0),
                position_y=float(channel_payload.get("position_y") or 0.0),
            )
            session.add(channel)
            await session.flush()
            number_to_channel_id[channel.number] = channel.id

        order_index_to_scene_id: dict[int, int] = {}
        for order_index, scene_payload in enumerate(scenes_payload):
            scene = Scene(
                name=str(scene_payload.get("name") or f"Scene {order_index + 1}").strip() or f"Scene {order_index + 1}",
                order_index=int(scene_payload.get("order_index", order_index) or order_index),
                sync_osc_address=_normalise_optional_text(scene_payload.get("sync_osc_address")),
                sync_osc_argument=_normalise_optional_text(scene_payload.get("sync_osc_argument")),
                sync_midi_pattern=_normalise_optional_text(scene_payload.get("sync_midi_pattern")),
            )
            session.add(scene)
            await session.flush()
            order_index_to_scene_id[scene.order_index] = scene.id

            for assignment_payload in scene_payload.get("channel_assignments", []) or []:
                channel_number = int(assignment_payload.get("channel_number") or 0)
                channel_id = number_to_channel_id.get(channel_number)
                state = str(assignment_payload.get("state") or "off").strip().lower()
                if channel_id is None or state not in SCENE_CHANNEL_STATES or state == "off":
                    continue
                session.add(SceneChannel(scene_id=scene.id, channel_id=channel_id, state=state))

        for field_name, value in settings_payload.items():
            if field_name == "active_scene_order_index":
                continue
            if field_name in {"audio_input_device", "external_sync_midi_input_name", "radioworld_interface_ip"}:
                value = _normalise_optional_text(value)
            setattr(settings_row, field_name, value)

        active_scene_order_index = settings_payload.get("active_scene_order_index")
        if active_scene_order_index is None:
            settings_row.active_scene_id = next(iter(order_index_to_scene_id.values()), None)
        else:
            settings_row.active_scene_id = order_index_to_scene_id.get(int(active_scene_order_index))

        await session.commit()
        await session.refresh(settings_row)
        return settings_row


async def create_scene(
    database: DatabaseManager,
    changes: dict[str, object] | None = None,
) -> Scene:
    """Create a new scene, defaulting to a copy of the previous scene's assignments."""
    scene_changes = changes or {}

    created_scene_id: int | None = None

    async with database.session() as session:
        existing_scenes = list(
            (
                await session.scalars(
                    select(Scene)
                    .options(selectinload(Scene.channel_assignments))
                    .order_by(Scene.order_index, Scene.id),
                )
            ).all(),
        )
        next_order_index = len(existing_scenes)
        scene = Scene(
            name=f"Scene {next_order_index + 1}",
            order_index=next_order_index,
        )
        session.add(scene)
        await session.flush()

        if name := scene_changes.get("name"):
            scene.name = str(name).strip() or scene.name
        for field_name in ("sync_osc_address", "sync_osc_argument", "sync_midi_pattern"):
            if field_name in scene_changes:
                setattr(scene, field_name, _normalise_optional_text(scene_changes[field_name]))

        assignments = scene_changes.get("channel_assignments")
        if assignments is None and existing_scenes:
            assignments = [
                {"channel_id": assignment.channel_id, "state": assignment.state}
                for assignment in existing_scenes[-1].channel_assignments
            ]
        await _replace_scene_assignments(session, scene, assignments)

        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is not None and settings_row.active_scene_id is None:
            settings_row.active_scene_id = scene.id

        await session.commit()
        created_scene_id = scene.id

    refreshed_scene = await get_scene(database, created_scene_id)
    if refreshed_scene is None:
        raise RuntimeError("Scene could not be reloaded after creation")
    return refreshed_scene


async def update_scene(
    database: DatabaseManager,
    scene_id: int,
    changes: dict[str, object],
) -> Scene | None:
    """Update scene metadata, ordering, and per-channel states."""
    updated_scene_id: int | None = None

    async with database.session() as session:
        scene = await session.scalar(
            select(Scene)
            .options(selectinload(Scene.channel_assignments))
            .where(Scene.id == scene_id),
        )
        if scene is None:
            return None

        if "name" in changes:
            scene.name = str(changes["name"] or "").strip() or scene.name

        for field_name in ("sync_osc_address", "sync_osc_argument", "sync_midi_pattern"):
            if field_name in changes:
                setattr(scene, field_name, _normalise_optional_text(changes[field_name]))

        if "channel_assignments" in changes:
            await _replace_scene_assignments(session, scene, changes["channel_assignments"])

        if "order_index" in changes and changes["order_index"] is not None:
            scenes = list(
                (
                    await session.scalars(select(Scene).order_by(Scene.order_index, Scene.id))
                ).all(),
            )
            scenes = [item for item in scenes if item.id != scene_id]
            target_index = max(0, min(int(changes["order_index"]), len(scenes)))
            scenes.insert(target_index, scene)
            await _apply_scene_order(session, scenes)

        await session.commit()
        updated_scene_id = scene.id

    return await get_scene(database, updated_scene_id)


async def delete_scene(database: DatabaseManager, scene_id: int) -> bool:
    """Delete a scene and compact the remaining show order."""
    async with database.session() as session:
        scene = await session.get(Scene, scene_id)
        if scene is None:
            return False

        await session.delete(scene)
        await session.flush()

        remaining_scenes = list(
            (
                await session.scalars(select(Scene).order_by(Scene.order_index, Scene.id))
            ).all(),
        )
        await _apply_scene_order(session, remaining_scenes)

        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is not None:
            if settings_row.active_scene_id == scene_id:
                settings_row.active_scene_id = remaining_scenes[0].id if remaining_scenes else None
            if not remaining_scenes:
                settings_row.scene_mode_enabled = False

        await session.commit()
        return True
