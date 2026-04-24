"""Tests for external scene sync matching and application."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.core.settings import MicWiseSettings
from app.database.repository import create_scene, get_settings, initialise_show_file, update_settings
from app.database.session import DatabaseManager
from app.sync.service import ExternalSyncEvent, apply_scene_sync_event, parse_midi_pattern, scene_matches_event


def test_parse_midi_pattern_supports_common_forms() -> None:
    parsed_program = parse_midi_pattern("program_change:12")
    assert parsed_program is not None
    assert parsed_program.message_type == "program_change"
    assert parsed_program.channel is None
    assert parsed_program.data_1 == 12
    assert parsed_program.data_2 is None

    parsed = parse_midi_pattern("control_change:1:42:127")
    assert parsed is not None
    assert parsed.message_type == "control_change"
    assert parsed.channel == 1
    assert parsed.data_1 == 42
    assert parsed.data_2 == 127


def test_scene_matches_event_for_osc_and_midi_patterns() -> None:
    scene = SimpleNamespace(
        sync_osc_address="/qlab/scene/3",
        sync_osc_argument="GO",
        sync_midi_pattern="note_on:1:60:127",
    )

    assert scene_matches_event(
        scene,
        ExternalSyncEvent(transport="osc", osc_address="/qlab/scene/3", osc_argument="GO"),
    ) is True
    assert scene_matches_event(
        scene,
        ExternalSyncEvent(transport="osc", osc_address="/qlab/scene/3", osc_argument="STOP"),
    ) is False
    assert scene_matches_event(
        scene,
        ExternalSyncEvent(
            transport="midi",
            midi_message_type="note_on",
            midi_channel=1,
            midi_data_1=60,
            midi_data_2=127,
        ),
    ) is True


def test_apply_scene_sync_event_updates_active_scene_when_enabled(tmp_path) -> None:
    settings = MicWiseSettings(
        data_directory=tmp_path,
        show_filename="sync_test.micwise",
        buffer_filename="sync_audio.buffer",
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
            await update_settings(
                database,
                {
                    "external_sync_enabled": True,
                    "external_sync_transport": "osc",
                    "external_sync_osc_host": "127.0.0.1",
                    "external_sync_osc_port": 0,
                },
            )
            created_scene = await create_scene(
                database,
                {
                    "name": "Scene 2",
                    "sync_osc_address": "/qlab/scene/2",
                    "sync_osc_argument": "GO",
                },
            )

            result = await apply_scene_sync_event(
                database,
                ExternalSyncEvent(
                    transport="osc",
                    osc_address="/qlab/scene/2",
                    osc_argument="GO",
                ),
            )
            settings_row = await get_settings(database)

            assert result.matched_scene_id == created_scene.id
            assert result.changed is True
            assert settings_row.active_scene_id == created_scene.id
        finally:
            await database.dispose()

    asyncio.run(scenario())
