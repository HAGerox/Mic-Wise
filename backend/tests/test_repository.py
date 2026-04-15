"""Tests for show-file bootstrap and repository helpers."""

from __future__ import annotations

import asyncio

from app.core.settings import MicWiseSettings
from app.database.repository import (
    create_channel,
    delete_channel,
    initialise_show_file,
    list_channels,
    list_scenes,
    update_channel,
)
from app.database.session import DatabaseManager


def test_initialise_show_file_seeds_default_records(tmp_path) -> None:
    settings = MicWiseSettings(
        data_directory=tmp_path,
        show_filename="test_show.micwise",
        buffer_filename="test_audio.buffer",
        default_sample_rate=48_000,
        default_channel_count=4,
        default_buffer_duration_sec=300,
        default_block_size=480,
    )
    settings.ensure_directories()

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            settings_row = await initialise_show_file(database, settings)
            assert settings_row.channel_count == 4
            assert settings_row.sample_rate == 48_000

            channels = await list_channels(database)
            assert len(channels) == 4
            assert channels[0].name == "Channel 1"

            updated = await update_channel(
                database,
                channel_id=channels[0].id,
                changes={"name": "Lead", "is_record_enabled": False},
            )
            assert updated is not None
            assert updated.name == "Lead"
            assert updated.is_record_enabled is False

            created = await create_channel(database)
            assert created.number == 5
            assert created.input_index is None

            deleted = await delete_channel(database, channel_id=channels[1].id)
            assert deleted is True

            channels_after_delete = await list_channels(database)
            assert [channel.number for channel in channels_after_delete] == [1, 2, 3, 4]
            assert [channel.name for channel in channels_after_delete] == [
                "Lead",
                "Channel 2",
                "Channel 3",
                "Channel 4",
            ]

            scenes = await list_scenes(database)
            assert len(scenes) == 1
            assert scenes[0].name == "Scene 1"
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_initialise_show_file_preserves_deleted_channels(tmp_path) -> None:
    settings = MicWiseSettings(
        data_directory=tmp_path,
        show_filename="test_show.micwise",
        buffer_filename="test_audio.buffer",
        default_sample_rate=48_000,
        default_channel_count=4,
        default_buffer_duration_sec=300,
        default_block_size=480,
    )
    settings.ensure_directories()

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            channels = await list_channels(database)

            deleted = await delete_channel(database, channel_id=channels[1].id)
            assert deleted is True

            channels_after_delete = await list_channels(database)
            assert len(channels_after_delete) == 3
            assert [channel.number for channel in channels_after_delete] == [1, 2, 3]

            await initialise_show_file(database, settings)

            channels_after_restart = await list_channels(database)
            assert len(channels_after_restart) == 3
            assert [channel.number for channel in channels_after_restart] == [1, 2, 3]
        finally:
            await database.dispose()

    asyncio.run(scenario())
