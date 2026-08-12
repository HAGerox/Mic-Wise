"""Tests for show-file bootstrap and repository helpers."""

from __future__ import annotations

import asyncio
import sqlite3

from app.core.settings import MicWiseSettings
from app.database.repository import (
    create_channel,
    create_scene,
    delete_channel,
    delete_scene,
    get_settings,
    initialise_show_file,
    list_channels,
    list_scenes,
    update_scene,
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
            assert settings_row.master_gain_db == 0.0
            assert settings_row.rchat_username == "Mic-Wise"

            channels = await list_channels(database)
            assert len(channels) == 4
            assert channels[0].name == "Channel 1"
            assert channels[0].gain_db == 0.0

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


def test_initialise_show_file_migrates_radioworld_settings_to_rchat(tmp_path) -> None:
    settings = MicWiseSettings(
        data_directory=tmp_path,
        show_filename="legacy_show.micwise",
        buffer_filename="legacy_audio.buffer",
        default_sample_rate=48_000,
        default_channel_count=4,
        default_buffer_duration_sec=300,
        default_block_size=480,
    )
    settings.ensure_directories()

    async def seed_current_schema() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
        finally:
            await database.dispose()

    asyncio.run(seed_current_schema())

    with sqlite3.connect(settings.show_path) as connection:
        connection.execute("ALTER TABLE settings RENAME COLUMN rchat_enabled TO radioworld_enabled")
        connection.execute("ALTER TABLE settings RENAME COLUMN rchat_flash_enabled TO radioworld_flash_enabled")
        connection.execute("ALTER TABLE settings RENAME COLUMN rchat_hold_seconds TO radioworld_hold_seconds")
        connection.execute("ALTER TABLE settings RENAME COLUMN rchat_interface_ip TO radioworld_interface_ip")
        connection.execute("ALTER TABLE settings DROP COLUMN rchat_username")
        connection.execute(
            "UPDATE settings SET radioworld_enabled = 1, radioworld_flash_enabled = 1, "
            "radioworld_hold_seconds = 12, radioworld_interface_ip = '192.0.2.10'",
        )

    async def verify_migration() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            migrated = await initialise_show_file(database, settings)
            assert migrated.rchat_enabled is True
            assert migrated.rchat_flash_enabled is True
            assert migrated.rchat_hold_seconds == 12
            assert migrated.rchat_interface_ip == "192.0.2.10"
            assert migrated.rchat_username == "Mic-Wise"
        finally:
            await database.dispose()

    asyncio.run(verify_migration())


def test_scene_crud_and_channel_delete_resequencing(tmp_path) -> None:
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

            extra_channel = await create_channel(database)
            deleted = await delete_channel(database, channel_id=channels[1].id)

            assert deleted is True
            channels_after_delete = await list_channels(database)
            assert [channel.number for channel in channels_after_delete] == [1, 2, 3, 4]
            assert extra_channel.id in {channel.id for channel in channels_after_delete}

            created_scene = await create_scene(
                database,
                {
                    "name": "Quick change",
                    "sync_osc_address": "/qlab/quick-change",
                    "sync_midi_pattern": "program_change:12",
                    "channel_assignments": [
                        {"channel_id": channels_after_delete[0].id, "state": "onstage"},
                        {"channel_id": channels_after_delete[1].id, "state": "ready"},
                    ],
                },
            )
            assert created_scene.name == "Quick change"
            assert created_scene.sync_osc_address == "/qlab/quick-change"

            updated_scene = await update_scene(
                database,
                created_scene.id,
                {
                    "order_index": 0,
                    "sync_osc_argument": "GO",
                    "channel_assignments": [
                        {"channel_id": channels_after_delete[0].id, "state": "ready"},
                    ],
                },
            )
            assert updated_scene is not None
            assert updated_scene.order_index == 0
            assert updated_scene.sync_osc_argument == "GO"
            assert [assignment.state for assignment in updated_scene.channel_assignments] == ["ready"]

            scenes = await list_scenes(database)
            assert [scene.name for scene in scenes] == ["Quick change", "Scene 1"]

            deleted_scene = await delete_scene(database, created_scene.id)
            assert deleted_scene is True

            settings_row = await get_settings(database)
            assert settings_row.active_scene_id == scenes[1].id
        finally:
            await database.dispose()

    asyncio.run(scenario())
