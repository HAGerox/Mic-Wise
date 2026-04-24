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
                master_gain_db=0.0,
                scene_mode_enabled=False,
                external_sync_enabled=False,
                external_sync_transport="off",
                external_sync_osc_host="0.0.0.0",
                external_sync_osc_port=53001,
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
            setattr(settings_row, field_name, value)

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
