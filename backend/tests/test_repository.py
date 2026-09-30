"""Tests for show-file bootstrap and repository helpers."""

from __future__ import annotations

import asyncio
import json

from app.core.settings import MicWiseSettings
from app.database.repository import (
    create_channel,
    create_scene,
    delete_channel,
    delete_scene,
    export_show_archive,
    export_showfile,
    get_scene,
    get_settings,
    import_show_archive,
    import_showfile,
    initialise_show_file,
    list_channels,
    list_scenes,
    set_scene_channel_checked,
    store_photo_asset,
    update_scene,
    update_channel,
)
from app.database.session import DatabaseManager


def build_settings(tmp_path, show_filename: str = "test_show.micwise") -> MicWiseSettings:
    settings = MicWiseSettings(
        data_directory=tmp_path,
        show_filename=show_filename,
        buffer_filename="test_audio.buffer",
        default_sample_rate=48_000,
        default_channel_count=4,
        default_buffer_duration_sec=300,
        default_block_size=480,
    )
    settings.ensure_directories()
    return settings


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
            assert scenes[0].sync_osc_address == "/micwise/scene/1"
            assert scenes[0].sync_osc_argument is None
            assert scenes[0].sync_midi_pattern is None
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


def test_initialise_show_file_preserves_cleared_scene_cue(tmp_path) -> None:
    settings = MicWiseSettings(data_directory=tmp_path)

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            scenes = await list_scenes(database)
            await update_scene(database, scenes[0].id, {"sync_osc_address": None})
            await initialise_show_file(database, settings)
            assert (await list_scenes(database))[0].sync_osc_address is None
        finally:
            await database.dispose()

    asyncio.run(scenario())


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

            default_scene = await create_scene(database)
            assert default_scene.sync_osc_address == "/micwise/scene/3"
            assert default_scene.sync_osc_argument is None
            assert default_scene.sync_midi_pattern is None

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
            assert [scene.name for scene in scenes] == ["Quick change", "Scene 1", "Scene 3"]
            assert scenes[0].sync_osc_address == "/qlab/quick-change"
            assert scenes[1].sync_osc_address == "/micwise/scene/2"
            assert scenes[2].sync_osc_address == "/micwise/scene/3"

            deleted_scene = await delete_scene(database, created_scene.id)
            assert deleted_scene is True

            settings_row = await get_settings(database)
            assert settings_row.active_scene_id == scenes[1].id
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_scene_checklist_ticks_persist_beyond_off_state(tmp_path) -> None:
    settings = build_settings(tmp_path, "checklist.micwise")

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            channels = await list_channels(database)
            scenes = await list_scenes(database)
            scene_id = scenes[0].id

            assert await set_scene_channel_checked(database, scene_id, channels[0].id, True) is True
            scene = await get_scene(database, scene_id)
            assert [
                (assignment.channel_id, assignment.state, assignment.checked)
                for assignment in scene.channel_assignments
            ] == [(channels[0].id, "off", True)]

            await update_scene(
                database,
                scene_id,
                {
                    "channel_assignments": [
                        {"channel_id": channels[0].id, "state": "onstage"},
                        {"channel_id": channels[1].id, "state": "off", "checked": True},
                    ],
                },
            )
            scene = await get_scene(database, scene_id)
            by_channel = {assignment.channel_id: assignment for assignment in scene.channel_assignments}
            assert by_channel[channels[0].id].state == "onstage"
            assert by_channel[channels[0].id].checked is True
            assert by_channel[channels[1].id].state == "off"
            assert by_channel[channels[1].id].checked is True

            await update_scene(
                database,
                scene_id,
                {
                    "channel_assignments": [
                        {"channel_id": channels[0].id, "state": "onstage", "checked": False},
                    ],
                },
            )
            scene = await get_scene(database, scene_id)
            assert [
                (assignment.channel_id, assignment.state, assignment.checked)
                for assignment in scene.channel_assignments
            ] == [(channels[0].id, "onstage", False)]

            assert await set_scene_channel_checked(database, scene_id, channels[1].id, False) is True
            scene = await get_scene(database, scene_id)
            assert [assignment.channel_id for assignment in scene.channel_assignments] == [channels[0].id]

            assert await set_scene_channel_checked(database, scene_id, 9999, True) is False
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_pre_alpha_showfile_is_rejected(tmp_path) -> None:
    import pytest

    settings = build_settings(tmp_path, "show.micwise")

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            with pytest.raises(ValueError, match="Unsupported Mic-Wise showfile version"):
                await import_showfile(database, {"format": "micwise-showfile", "version": 1}, settings)
            assert len(await list_channels(database)) == settings.default_channel_count
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_showfile_rejects_unknown_version(tmp_path) -> None:
    settings = build_settings(tmp_path, "future.micwise")

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            payload = await export_showfile(database, settings, embed_assets=False)
            payload.pop("_assets", None)
            payload["version"] = 99
            try:
                await import_showfile(database, payload, settings)
            except ValueError as error:
                assert "version" in str(error)
            else:
                raise AssertionError("expected a version mismatch")
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_show_archive_round_trips_photos(tmp_path) -> None:
    settings = build_settings(tmp_path, "archive.micwise")
    photo_bytes = b"\x89PNG\r\n\x1a\n" + b"payload"

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            photo_path = store_photo_asset(settings, photo_bytes, "performer.png", "image/png")
            await update_channel(database, 1, {"name": "Lead", "photo_path": photo_path})
            scenes = await list_scenes(database)
            await set_scene_channel_checked(database, scenes[0].id, 1, True)

            archive_bytes = await export_show_archive(database, settings)

            await update_channel(database, 1, {"name": "Wiped", "photo_path": None})
            await set_scene_channel_checked(database, scenes[0].id, 1, False)

            await import_show_archive(database, settings, archive_bytes)

            channels = await list_channels(database)
            assert channels[0].name == "Lead"
            assert channels[0].photo_path == photo_path
            restored = (settings.photos_directory / photo_path.rsplit("/", 1)[-1]).read_bytes()
            assert restored == photo_bytes

            scenes_after = await list_scenes(database)
            assert [
                (assignment.channel_id, assignment.state, assignment.checked)
                for assignment in scenes_after[0].channel_assignments
            ] == [(channels[0].id, "off", True)]

            reexported = await export_show_archive(database, settings)
            assert reexported == archive_bytes
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_show_archive_rejects_unlisted_members(tmp_path) -> None:
    import io
    import zipfile

    settings = build_settings(tmp_path, "tamper.micwise")

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            archive_bytes = await export_show_archive(database, settings)
        finally:
            await database.dispose()

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        members["extra.txt"] = b"surprise"

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, content in members.items():
                archive.writestr(name, content)

        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            try:
                await import_show_archive(database, settings, buffer.getvalue())
            except ValueError as error:
                assert "unlisted" in str(error)
            else:
                raise AssertionError("expected unlisted members to be rejected")

            manifest = json.loads(members["backup.json"])
            manifest["members"]["../../escape.png"] = {"kind": "asset", "size": 1, "sha256": "00"}
            members["backup.json"] = json.dumps(manifest).encode("utf-8")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, content in members.items():
                    archive.writestr(name, content)
            try:
                await import_show_archive(database, settings, buffer.getvalue())
            except ValueError as error:
                assert "photo library" in str(error) or "member path" in str(error)
            else:
                raise AssertionError("expected path escapes to be rejected")

            manifest = json.loads(members["backup.json"])
            manifest["members"].pop("../../escape.png", None)
            manifest["members"]["other/thing.png"] = {"kind": "asset", "size": 1, "sha256": "00"}
            members["backup.json"] = json.dumps(manifest).encode("utf-8")
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                for name, content in members.items():
                    archive.writestr(name, content)
            try:
                await import_show_archive(database, settings, buffer.getvalue())
            except ValueError as error:
                assert "outside the photo library" in str(error)
            else:
                raise AssertionError("expected foreign members to be rejected")
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_create_scene_copies_checklist_ticks(tmp_path) -> None:
    settings = build_settings(tmp_path, "copy.micwise")

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            channels = await list_channels(database)
            scenes = await list_scenes(database)
            await update_scene(
                database,
                scenes[0].id,
                {
                    "channel_assignments": [
                        {"channel_id": channels[0].id, "state": "onstage", "checked": True},
                    ],
                },
            )

            created = await create_scene(database)
            assert [
                (assignment.channel_id, assignment.state, assignment.checked)
                for assignment in created.channel_assignments
            ] == [(channels[0].id, "onstage", True)]
        finally:
            await database.dispose()

    asyncio.run(scenario())


def test_backup_compression_does_not_block_live_async_work(tmp_path, monkeypatch) -> None:
    import threading
    from app.database import repository

    started = threading.Event()
    release = threading.Event()
    original = repository._compress_archive_members

    def slow_compression(members):
        started.set()
        release.wait(timeout=1)
        return original(members)

    monkeypatch.setattr(repository, "_compress_archive_members", slow_compression)
    settings = build_settings(tmp_path)

    async def scenario() -> None:
        database = DatabaseManager(settings.show_path)
        try:
            await initialise_show_file(database, settings)
            task = asyncio.create_task(repository.export_show_archive(database, settings))
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.005)
            try:
                assert started.is_set()
                # A meter/health task can run while compression is in progress.
                assert not task.done()
            finally:
                release.set()
            assert (await task).startswith(b"PK")
        finally:
            await database.dispose()

    asyncio.run(scenario())
