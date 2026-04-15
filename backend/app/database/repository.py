"""Database bootstrap and query helpers for the active Mic-Wise show file."""

from __future__ import annotations

import re

from sqlalchemy import select

from app.core.settings import MicWiseSettings
from app.database.models import Channel, Scene, SettingsRecord
from app.database.session import DatabaseManager


DEFAULT_CHANNEL_NAME_PATTERN = re.compile(r"^Channel (\d+)$")


async def initialise_show_file(
    database: DatabaseManager,
    settings: MicWiseSettings,
) -> SettingsRecord:
    """Create default settings, channels, and a starter scene if absent."""
    await database.create_schema()

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
                        is_record_enabled=True,
                        sort_index=number - 1,
                    ),
                )

        existing_scene_count = len((await session.scalars(select(Scene))).all())
        if existing_scene_count == 0:
            session.add(Scene(name="Scene 1", order_index=0))

        await session.commit()
        await session.refresh(settings_row)
        return settings_row


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
        result = await session.scalars(select(Scene).order_by(Scene.order_index, Scene.id))
        return list(result.all())


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

        for sort_index, remaining_channel in enumerate(remaining_channels):
            previous_number = remaining_channel.number
            next_number = sort_index + 1
            remaining_channel.sort_index = sort_index
            remaining_channel.number = next_number
            if DEFAULT_CHANNEL_NAME_PATTERN.match(remaining_channel.name) and remaining_channel.name == f"Channel {previous_number}":
                remaining_channel.name = f"Channel {next_number}"

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
