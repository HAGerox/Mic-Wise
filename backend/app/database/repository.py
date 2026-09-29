"""Database bootstrap and query helpers for the active Mic-Wise show file."""

from __future__ import annotations

import hashlib
import io
import json
import re
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath

from sqlalchemy import delete, select, text
from sqlalchemy.orm import selectinload

from app.core.settings import MicWiseSettings
from app.database.models import Channel, Scene, SceneChannel, SettingsRecord
from app.database.session import DatabaseManager


DEFAULT_CHANNEL_NAME_PATTERN = re.compile(r"^Channel (\d+)$")
SCENE_CHANNEL_STATES = {"off", "ready", "onstage"}
SHOWFILE_FORMAT = "micwise-showfile"
SHOWFILE_FORMAT_VERSION = 2
SHOWFILE_SUPPORTED_VERSIONS = {1, 2}
BACKUP_FORMAT = "micwise-backup"
BACKUP_FORMAT_VERSION = 1
SHOWFILE_MEMBER = "micwise-showfile.micwise.json"
BACKUP_MANIFEST_MEMBER = "backup.json"
ASSET_MEMBER_ROOT = "assets/photos"
PHOTO_URL_PREFIX = "/api/assets/photos/"
REMOTE_FETCH_TIMEOUT_SEC = 2.0
REMOTE_FETCH_BUDGET_SEC = 12.0
REMOTE_FETCH_WORKERS = 4
ASSET_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "avif", "bmp"}


def default_scene_osc_address(order_index: int) -> str:
    """Return the portable, argument-free OSC trigger for a scene order position."""
    return f"/micwise/scene/{max(0, int(order_index)) + 1}"


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
        if settings_columns and "scene_osc_defaults_seeded" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN scene_osc_defaults_seeded BOOLEAN NOT NULL DEFAULT 0",
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
        if settings_columns and "rchat_enabled" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN rchat_enabled BOOLEAN NOT NULL DEFAULT 0",
                ),
            )
            if "radioworld_enabled" in settings_columns:
                await connection.execute(text("UPDATE settings SET rchat_enabled = radioworld_enabled"))
        if settings_columns and "rchat_flash_enabled" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN rchat_flash_enabled BOOLEAN NOT NULL DEFAULT 0",
                ),
            )
            if "radioworld_flash_enabled" in settings_columns:
                await connection.execute(text("UPDATE settings SET rchat_flash_enabled = radioworld_flash_enabled"))
        if settings_columns and "rchat_hold_seconds" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN rchat_hold_seconds INTEGER NOT NULL DEFAULT 8",
                ),
            )
            if "radioworld_hold_seconds" in settings_columns:
                await connection.execute(text("UPDATE settings SET rchat_hold_seconds = radioworld_hold_seconds"))
        if settings_columns and "rchat_interface_ip" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN rchat_interface_ip VARCHAR(45)",
                ),
            )
            if "radioworld_interface_ip" in settings_columns:
                await connection.execute(text("UPDATE settings SET rchat_interface_ip = radioworld_interface_ip"))
        if settings_columns and "rchat_username" not in settings_columns:
            await connection.execute(
                text(
                    "ALTER TABLE settings ADD COLUMN rchat_username VARCHAR(128) NOT NULL DEFAULT 'Mic-Wise'",
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

        scene_channel_columns = {
            row[1]
            for row in (
                await connection.execute(text("PRAGMA table_info(scene_channels)"))
            ).fetchall()
        }
        if scene_channel_columns and "checked" not in scene_channel_columns:
            await connection.execute(
                text(
                    "ALTER TABLE scene_channels ADD COLUMN checked BOOLEAN NOT NULL DEFAULT 0",
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
                rchat_enabled=False,
                rchat_flash_enabled=False,
                rchat_hold_seconds=8,
                rchat_interface_ip=None,
                rchat_username="Mic-Wise",
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

        existing_scenes = list(
            (await session.scalars(select(Scene).order_by(Scene.order_index, Scene.id))).all(),
        )
        if not existing_scenes:
            starter_scene = Scene(
                name="Scene 1",
                order_index=0,
                sync_osc_address=default_scene_osc_address(0),
            )
            session.add(starter_scene)
            await session.flush()
            existing_scenes = [starter_scene]
            if settings_row.active_scene_id is None:
                settings_row.active_scene_id = starter_scene.id

        if not settings_row.scene_osc_defaults_seeded:
            for scene in existing_scenes:
                if scene.sync_osc_address is None:
                    scene.sync_osc_address = default_scene_osc_address(scene.order_index)
            settings_row.scene_osc_defaults_seeded = True

        await session.commit()
        await session.refresh(settings_row)
        return settings_row


def _normalise_scene_assignments(
    assignments: list[dict[str, object]] | None,
    existing_checked: dict[int, bool] | None = None,
) -> dict[int, tuple[str, bool]]:
    """Validate scene-channel payloads and drop rows with no lasting meaning.

    An entry is retained when it stages a channel (``ready``/``onstage``) or when
    the operator has ticked it on the scene checklist. Explicitly ``off`` rows
    with no tick are discarded so the show file does not accumulate noise.

    When a payload omits ``checked`` the previous tick is preserved, so painting
    staging states does not silently wipe mic-check progress.
    """
    previous = existing_checked or {}
    mapping: dict[int, tuple[str, bool]] = {}
    for assignment in assignments or []:
        channel_id = int(assignment["channel_id"])
        state = str(assignment.get("state", "off")).strip().lower()
        if state not in SCENE_CHANNEL_STATES:
            raise ValueError(f"Unsupported scene channel state: {state}")
        checked_value = assignment.get("checked", None)
        checked = previous.get(channel_id, False) if checked_value is None else bool(checked_value)
        if state == "off" and not checked:
            mapping.pop(channel_id, None)
            continue
        mapping[channel_id] = (state, checked)
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
    default_address_scene_ids = {
        scene.id
        for scene in ordered_scenes
        if scene.sync_osc_address == default_scene_osc_address(scene.order_index)
    }
    for temp_index, scene in enumerate(ordered_scenes, start=1):
        scene.order_index = -temp_index

    await session.flush()

    for order_index, scene in enumerate(ordered_scenes):
        scene.order_index = order_index
        if scene.id in default_address_scene_ids:
            scene.sync_osc_address = default_scene_osc_address(order_index)


async def _replace_scene_assignments(
    session,
    scene: Scene,
    assignments: list[dict[str, object]] | None,
) -> None:
    """Replace all persisted per-channel states for a scene."""
    existing_rows = list(
        (
            await session.scalars(select(SceneChannel).where(SceneChannel.scene_id == scene.id))
        ).all(),
    )
    existing_checked = {row.channel_id: row.checked for row in existing_rows}
    mapping = _normalise_scene_assignments(assignments, existing_checked)
    await session.execute(delete(SceneChannel).where(SceneChannel.scene_id == scene.id))
    for channel_id, (state, checked) in mapping.items():
        session.add(SceneChannel(scene_id=scene.id, channel_id=channel_id, state=state, checked=checked))
    await session.flush()


async def get_settings(database: DatabaseManager) -> SettingsRecord:
    """Fetch the singleton settings row."""
    async with database.session() as session:
        settings_row = await session.get(SettingsRecord, 1)
        if settings_row is None:
            raise RuntimeError("Show settings have not been initialised")
        return settings_row


async def set_scene_channel_checked(
    database: DatabaseManager,
    scene_id: int,
    channel_id: int,
    checked: bool,
) -> bool:
    """Persist a scene mic-check tick without disturbing the staging state.

    Returns ``False`` when the scene or channel no longer exists. Rows that end
    up as ``off`` and unticked are removed so the show file stays clean.
    """
    async with database.session() as session:
        scene = await session.get(Scene, scene_id)
        channel = await session.get(Channel, channel_id)
        if scene is None or channel is None:
            return False

        assignment = await session.get(SceneChannel, (scene_id, channel_id))
        if assignment is None:
            if not checked:
                return True
            session.add(
                SceneChannel(scene_id=scene_id, channel_id=channel_id, state="off", checked=True),
            )
        else:
            assignment.checked = bool(checked)
            if assignment.state == "off" and not assignment.checked:
                await session.delete(assignment)

        await session.commit()
        return True


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
            if field_name in {"audio_input_device", "external_sync_midi_input_name", "rchat_interface_ip"}:
                value = _normalise_optional_text(value)
            setattr(settings_row, field_name, value)

        await session.commit()
        await session.refresh(settings_row)
        return settings_row


def _asset_extension(name: str, content_type: str | None = None) -> str:
    """Return a safe lowercase image extension for an asset member name."""
    suffix = Path(name).suffix.lstrip(".").lower()
    if suffix in ASSET_EXTENSIONS:
        return suffix
    guessed = (content_type or "").split("/")[-1].split(";")[0].strip().lower()
    if guessed == "jpeg":
        return "jpg"
    if guessed in ASSET_EXTENSIONS:
        return guessed
    return "jpg"


def _asset_member_name(content: bytes, extension: str) -> str:
    """Return the archive member path for photo bytes."""
    digest = hashlib.sha256(content).hexdigest()
    return f"{ASSET_MEMBER_ROOT}/{digest}.{extension}"


def _asset_file_name(member_name: str) -> str:
    """Return the on-disk file name for an archive asset member."""
    return PurePosixPath(member_name).name


def store_photo_asset(
    settings: MicWiseSettings,
    content: bytes,
    source_name: str,
    content_type: str | None = None,
) -> str:
    """Persist photo bytes in the show's asset library and return its URL."""
    if not content:
        raise ValueError("Photo payload is empty")
    extension = _asset_extension(source_name, content_type)
    member_name = _asset_member_name(content, extension)
    file_name = _asset_file_name(member_name)
    settings.photos_directory.mkdir(parents=True, exist_ok=True)
    (settings.photos_directory / file_name).write_bytes(content)
    return f"{PHOTO_URL_PREFIX}{file_name}"


def read_photo_asset(settings: MicWiseSettings, file_name: str) -> bytes | None:
    """Read photo bytes from the show's asset library, if present."""
    safe_name = _asset_file_name(file_name)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", safe_name):
        return None
    path = settings.photos_directory / safe_name
    if not path.is_file():
        return None
    return path.read_bytes()


def _local_photo_file(settings: MicWiseSettings, photo_path: str) -> Path | None:
    """Resolve a locally served photo URL to its file on disk."""
    if not photo_path.startswith(PHOTO_URL_PREFIX):
        return None
    safe_name = _asset_file_name(photo_path[len(PHOTO_URL_PREFIX):])
    if not re.fullmatch(r"[A-Za-z0-9._-]+", safe_name):
        return None
    path = settings.photos_directory / safe_name
    return path if path.is_file() else None


def _fetch_remote_photo(url: str) -> tuple[bytes, str] | None:
    """Best-effort snapshot of an externally hosted photo."""
    max_bytes = 8 * 1024 * 1024
    request = urllib.request.Request(url, headers={"User-Agent": "Mic-Wise/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=REMOTE_FETCH_TIMEOUT_SEC) as response:
            content = response.read(max_bytes + 1)
            if len(content) > max_bytes:
                return None
            content_type = response.headers.get("Content-Type")
    except Exception:
        return None
    return content, content_type or ""


def _snapshot_photo(
    settings: MicWiseSettings,
    photo_path: str | None,
) -> tuple[str | None, bytes | None, str | None]:
    """Return ``(member_name, bytes, original_url)`` for a channel photo.

    Local assets and reachable external URLs are embedded so a restored show is
    byte-identical. Unreachable URLs fall back to carrying the URL alone.
    """
    if not photo_path:
        return None, None, None

    local_file = _local_photo_file(settings, photo_path)
    if local_file is not None:
        content = local_file.read_bytes()
        return _asset_member_name(content, local_file.suffix.lstrip(".").lower() or "jpg"), content, None

    if photo_path.startswith(("http://", "https://")):
        return None, None, photo_path

    candidate = Path(photo_path)
    if candidate.is_file():
        content = candidate.read_bytes()
        return _asset_member_name(content, _asset_extension(candidate.name)), content, None

    return None, None, photo_path


def _snapshot_remote_photos(
    settings: MicWiseSettings,
    snapshots: dict[str, tuple[str | None, bytes | None, str | None]],
) -> None:
    """Replace URL-only snapshots with embedded bytes when reachable."""
    pending = {
        photo_path: snapshot
        for photo_path, snapshot in snapshots.items()
        if snapshot[0] is None and snapshot[2] and snapshot[2].startswith(("http://", "https://"))
    }
    if not pending:
        return

    deadline = time.monotonic() + REMOTE_FETCH_BUDGET_SEC
    with ThreadPoolExecutor(max_workers=REMOTE_FETCH_WORKERS) as executor:
        futures = {
            photo_path: executor.submit(_fetch_remote_photo, photo_path)
            for photo_path in pending
        }
        for photo_path, future in futures.items():
            if time.monotonic() >= deadline:
                break
            try:
                result = future.result(timeout=max(0.1, deadline - time.monotonic()))
            except Exception:
                continue
            if not result:
                continue
            content, content_type = result
            member_name = _asset_member_name(content, _asset_extension(photo_path, content_type))
            snapshots[photo_path] = (member_name, content, photo_path)


def _apply_photo_payload(
    settings: MicWiseSettings,
    channel_payload: dict[str, object],
    archive_assets: dict[str, bytes],
) -> str | None:
    """Materialise a channel photo from an imported payload and return its URL."""
    member_name = _normalise_optional_text(channel_payload.get("photo_asset"))
    if member_name and member_name in archive_assets:
        content = archive_assets[member_name]
        return store_photo_asset(settings, content, _asset_file_name(member_name))

    photo_path = _normalise_optional_text(channel_payload.get("photo_path"))
    photo_url = _normalise_optional_text(channel_payload.get("photo_url"))
    return photo_path or photo_url


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
        "rchat_enabled": settings_row.rchat_enabled,
        "rchat_flash_enabled": settings_row.rchat_flash_enabled,
        "rchat_hold_seconds": settings_row.rchat_hold_seconds,
        "rchat_interface_ip": settings_row.rchat_interface_ip,
        "rchat_username": settings_row.rchat_username,
    }


async def export_showfile(
    database: DatabaseManager,
    settings: MicWiseSettings | None = None,
    embed_assets: bool = True,
) -> dict[str, object]:
    """Export the current show as a portable JSON-friendly payload.

    With ``embed_assets`` the payload also carries a ``photo_asset`` reference
    for every channel photo whose bytes could be resolved, so the show can be
    restored byte-identically from an archive.
    """
    settings_row = await get_settings(database)
    channels = await list_channels(database)
    scenes = await list_scenes(database)
    channel_by_id = {channel.id: channel for channel in channels}
    active_scene = next((scene for scene in scenes if scene.id == settings_row.active_scene_id), None)

    snapshots: dict[str, tuple[str | None, bytes | None, str | None]] = {}
    if embed_assets and settings is not None:
        for channel in channels:
            if channel.photo_path:
                snapshots[channel.photo_path] = _snapshot_photo(settings, channel.photo_path)
        _snapshot_remote_photos(settings, snapshots)

    asset_members: dict[str, bytes] = {}
    channels_payload: list[dict[str, object]] = []
    for channel in channels:
        member_name: str | None = None
        photo_url: str | None = None
        if channel.photo_path and channel.photo_path in snapshots:
            member_name, content, photo_url = snapshots[channel.photo_path]
            if member_name is not None and content is not None:
                asset_members[member_name] = content
        channels_payload.append(
            {
                "number": channel.number,
                "name": channel.name,
                "photo_path": channel.photo_path,
                "photo_asset": member_name,
                "photo_url": photo_url,
                "input_index": channel.input_index,
                "gain_db": channel.gain_db,
                "is_record_enabled": channel.is_record_enabled,
                "sort_index": channel.sort_index,
                "position_x": channel.position_x,
                "position_y": channel.position_y,
            },
        )

    return {
        "format": SHOWFILE_FORMAT,
        "version": SHOWFILE_FORMAT_VERSION,
        "exported_at": settings_row.updated_at.isoformat(),
        "settings": _serialise_showfile_settings(settings_row, active_scene),
        "channels": channels_payload,
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
                        "checked": assignment.checked,
                    }
                    for assignment in scene.channel_assignments
                    if assignment.channel_id in channel_by_id
                ],
            }
            for scene in scenes
        ],
        "_assets": asset_members,
    }


def _normalise_showfile_payload(payload: dict[str, object]) -> dict[str, object]:
    """Validate a showfile-like mapping enough for repository import."""
    if str(payload.get("format") or "").strip() != SHOWFILE_FORMAT:
        raise ValueError("Unsupported Mic-Wise showfile format")

    version = int(payload.get("version") or 0)
    if version not in SHOWFILE_SUPPORTED_VERSIONS:
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

    assets_payload = payload.get("_assets")
    archive_assets = assets_payload if isinstance(assets_payload, dict) else {}

    return {
        "settings": settings_payload,
        "channels": channels_payload,
        "scenes": scenes_payload,
        "assets": archive_assets,
    }


async def import_showfile(
    database: DatabaseManager,
    payload: dict[str, object],
    settings: MicWiseSettings | None = None,
) -> SettingsRecord:
    """Replace the current show contents with an imported showfile payload."""
    normalised_payload = _normalise_showfile_payload(payload)
    settings_payload = normalised_payload["settings"]
    archive_assets: dict[str, bytes] = {
        str(name): content
        for name, content in normalised_payload["assets"].items()
        if isinstance(content, (bytes, bytearray))
    }
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
            photo_path = (
                _apply_photo_payload(settings, channel_payload, archive_assets)
                if settings is not None
                else _normalise_optional_text(channel_payload.get("photo_path"))
                or _normalise_optional_text(channel_payload.get("photo_url"))
            )
            channel = Channel(
                number=channel_number,
                name=str(channel_payload.get("name") or f"Channel {channel_number}").strip() or f"Channel {channel_number}",
                photo_path=photo_path,
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
            scene_order_index = int(scene_payload.get("order_index", order_index) or order_index)
            scene = Scene(
                name=str(scene_payload.get("name") or f"Scene {order_index + 1}").strip() or f"Scene {order_index + 1}",
                order_index=scene_order_index,
                sync_osc_address=(
                    _normalise_optional_text(scene_payload.get("sync_osc_address"))
                    if "sync_osc_address" in scene_payload
                    else default_scene_osc_address(scene_order_index)
                ),
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
                checked = bool(assignment_payload.get("checked", False))
                if channel_id is None or state not in SCENE_CHANNEL_STATES:
                    continue
                if state == "off" and not checked:
                    continue
                session.add(
                    SceneChannel(
                        scene_id=scene.id,
                        channel_id=channel_id,
                        state=state,
                        checked=checked,
                    ),
                )

        for field_name, value in settings_payload.items():
            if field_name == "active_scene_order_index":
                continue
            if field_name in {"audio_input_device", "external_sync_midi_input_name", "rchat_interface_ip"}:
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


def _build_backup_manifest(members: dict[str, dict[str, object]]) -> bytes:
    """Serialise the archive integrity manifest."""
    return json.dumps(
        {
            "format": BACKUP_FORMAT,
            "version": BACKUP_FORMAT_VERSION,
            "members": members,
        },
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


async def export_show_archive(database: DatabaseManager, settings: MicWiseSettings) -> bytes:
    """Export the show as a self-contained ``.micwise.zip`` archive.

    The archive carries the portable showfile, every embedded photo asset, and
    a SHA-256 manifest. Restoring it into any Mic-Wise session reproduces the
    show exactly, including photos.
    """
    payload = await export_showfile(database, settings, embed_assets=True)
    asset_members: dict[str, bytes] = payload.pop("_assets", {})  # type: ignore[assignment]

    members: dict[str, bytes] = {
        SHOWFILE_MEMBER: json.dumps(payload, indent=2, sort_keys=True).encode("utf-8"),
        **asset_members,
    }

    manifest: dict[str, dict[str, object]] = {}
    for name, content in members.items():
        manifest[name] = {
            "kind": "showfile" if name == SHOWFILE_MEMBER else "asset",
            "size": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    members[BACKUP_MANIFEST_MEMBER] = _build_backup_manifest(manifest)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(members):
            archive.writestr(name, members[name])
    return buffer.getvalue()


def _valid_asset_member(name: str) -> str:
    """Validate an archive asset member path and return it."""
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or "\x00" in name
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != name
    ):
        raise ValueError("Invalid archive member path")
    if path.parts[0] != "assets" or len(path.parts) != 3 or path.parts[1] != "photos":
        raise ValueError("Archive contains data outside the photo library")
    if path.suffix.lstrip(".").lower() not in ASSET_EXTENSIONS:
        raise ValueError("Archive contains an unsupported photo type")
    return name


async def import_show_archive(
    database: DatabaseManager,
    settings: MicWiseSettings,
    data: bytes,
) -> SettingsRecord:
    """Restore a show from a ``.micwise.zip`` archive produced by the exporter.

    Every member is size- and hash-verified against the manifest before any of
    it is applied, and paths that would escape the photo library are rejected.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise ValueError("Show archive is not a valid zip file") from error

    with archive:
        names = set(archive.namelist())
        if SHOWFILE_MEMBER not in names:
            raise ValueError("Show archive is missing its showfile")
        if BACKUP_MANIFEST_MEMBER not in names:
            raise ValueError("Show archive is missing its manifest")

        raw_manifest = json.loads(archive.read(BACKUP_MANIFEST_MEMBER).decode("utf-8"))
        if str(raw_manifest.get("format") or "") != BACKUP_FORMAT:
            raise ValueError("Unsupported Mic-Wise backup manifest format")
        if int(raw_manifest.get("version") or 0) != BACKUP_FORMAT_VERSION:
            raise ValueError("Unsupported Mic-Wise backup manifest version")
        manifest = raw_manifest.get("members")
        if not isinstance(manifest, dict):
            raise ValueError("Show archive manifest is missing its members")

        contents: dict[str, bytes] = {}
        for name, entry in manifest.items():
            if not isinstance(entry, dict):
                raise ValueError("Show archive manifest entry is malformed")
            if name == BACKUP_MANIFEST_MEMBER:
                raise ValueError("Show archive manifest must not list itself")
            if name != SHOWFILE_MEMBER:
                _valid_asset_member(name)
            if name not in names:
                raise ValueError(f"Show archive is missing member: {name}")
            content = archive.read(name)
            if len(content) != int(entry.get("size") or -1):
                raise ValueError(f"Show archive member has the wrong size: {name}")
            if hashlib.sha256(content).hexdigest() != str(entry.get("sha256") or ""):
                raise ValueError(f"Show archive member failed its checksum: {name}")
            contents[name] = content

        unexpected = names - set(manifest) - {BACKUP_MANIFEST_MEMBER}
        if unexpected:
            raise ValueError("Show archive contains unlisted members")

    payload = json.loads(contents[SHOWFILE_MEMBER].decode("utf-8"))
    asset_members = {
        name: content for name, content in contents.items() if name != SHOWFILE_MEMBER
    }
    payload["_assets"] = asset_members
    return await import_showfile(database, payload, settings)


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
            sync_osc_address=default_scene_osc_address(next_order_index),
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
                {
                    "channel_id": assignment.channel_id,
                    "state": assignment.state,
                    "checked": assignment.checked,
                }
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
