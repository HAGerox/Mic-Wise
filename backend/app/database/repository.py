"""Database bootstrap and query helpers for the active Mic-Wise show file."""

from __future__ import annotations

from sqlalchemy import select

from app.core.settings import MicWiseSettings
from app.database.models import Channel, Scene, SettingsRecord
from app.database.session import DatabaseManager


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

        existing_channels = {
            channel.number: channel
            for channel in (
                await session.scalars(select(Channel).order_by(Channel.number))
            ).all()
        }
        for number in range(1, settings_row.channel_count + 1):
            if number not in existing_channels:
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
