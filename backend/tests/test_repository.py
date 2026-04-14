"""Tests for show-file bootstrap and repository helpers."""

from __future__ import annotations

import asyncio

from app.core.settings import MicWiseSettings
from app.database.repository import initialise_show_file, list_channels, list_scenes, update_channel
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

            scenes = await list_scenes(database)
            assert len(scenes) == 1
            assert scenes[0].name == "Scene 1"
        finally:
            await database.dispose()

    asyncio.run(scenario())
