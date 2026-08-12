"""Integration tests for the backend API and browser signaling path."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.audio.alerts import AudioAlert
from app.main import create_app


def configure_test_environment(monkeypatch, tmp_path) -> None:
	"""Configure environment variables for isolated backend integration tests."""
	monkeypatch.setenv("MICWISE_DATA_DIRECTORY", str(tmp_path))
	monkeypatch.setenv("MICWISE_RUNTIME_DIRECTORY", str(tmp_path / "runtime"))
	monkeypatch.setenv("MICWISE_SHOW_FILENAME", "integration.micwise")
	monkeypatch.setenv("MICWISE_BUFFER_FILENAME", "integration.buffer")
	monkeypatch.setenv("MICWISE_DEFAULT_CHANNEL_COUNT", "4")
	monkeypatch.setenv("MICWISE_DEFAULT_SAMPLE_RATE", "48000")
	monkeypatch.setenv("MICWISE_DEFAULT_BUFFER_DURATION_SEC", "5")
	monkeypatch.setenv("MICWISE_DEFAULT_BLOCK_SIZE", "480")
	monkeypatch.setenv("MICWISE_ZEROCONF_ENABLED", "false")


def test_api_health_and_static_frontend(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		health = client.get("/api/health")
		assert health.status_code == 200
		assert health.json()["status"] == "ok"
		assert "buffer_write_head" not in health.json()

		settings = client.get("/api/settings")
		assert settings.status_code == 200
		assert settings.json()["channel_count"] == 4
		assert settings.json()["master_gain_db"] == 0.0
		assert settings.json()["scene_mode_enabled"] is False
		assert settings.json()["active_scene_id"] == 1
		assert settings.json()["external_sync_enabled"] is False
		assert settings.json()["external_sync_transport"] == "off"
		assert settings.json()["rchat_enabled"] is False
		assert settings.json()["rchat_username"] == "Mic-Wise"

		channels = client.get("/api/channels")
		assert channels.status_code == 200
		assert len(channels.json()) == 4

		frontend = client.get("/")
		assert frontend.status_code == 200
		assert "Mic-Wise" in frontend.text


def test_settings_and_waveform_routes(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		patch_response = client.patch(
			"/api/settings",
			json={
				"multi_listen_enabled": True,
				"active_mode": "setup",
				"master_gain_db": 3.0,
				"scene_mode_enabled": True,
				"active_scene_id": 1,
				"external_sync_enabled": True,
				"external_sync_transport": "osc",
				"external_sync_osc_host": "127.0.0.1",
				"external_sync_osc_port": 0,
			},
		)
		assert patch_response.status_code == 200
		assert patch_response.json()["multi_listen_enabled"] is True
		assert patch_response.json()["active_mode"] == "setup"
		assert patch_response.json()["master_gain_db"] == 3.0
		assert patch_response.json()["scene_mode_enabled"] is True
		assert patch_response.json()["active_scene_id"] == 1
		assert patch_response.json()["external_sync_enabled"] is True
		assert patch_response.json()["external_sync_transport"] == "osc"

		waveform = client.get("/api/channels/1/waveform?seconds=5&points=64")
		assert waveform.status_code == 200
		payload = waveform.json()
		assert payload["channel_id"] == 1
		assert payload["input_index"] == 0
		assert len(payload["points"]) == 64


def test_create_and_delete_channel_routes(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		created = client.post("/api/channels", json={"name": "Spare Mic", "input_index": None})
		assert created.status_code == 201
		assert created.json()["number"] == 5
		assert created.json()["name"] == "Spare Mic"
		assert created.json()["gain_db"] == 0.0

		channels = client.get("/api/channels")
		assert channels.status_code == 200
		assert len(channels.json()) == 5

		deleted = client.delete("/api/channels/2")
		assert deleted.status_code == 204

		channels_after_delete = client.get("/api/channels")
		assert channels_after_delete.status_code == 200
		channel_payload = channels_after_delete.json()
		assert len(channel_payload) == 4
		assert [channel["number"] for channel in channel_payload] == [1, 2, 3, 4]


def test_repeated_channel_deletes_keep_numbers_compact(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		client.post("/api/channels", json={})
		client.post("/api/channels", json={})

		channels = client.get("/api/channels").json()
		delete_ids = [channels[1]["id"], channels[4]["id"]]

		for channel_id in delete_ids:
			deleted = client.delete(f"/api/channels/{channel_id}")
			assert deleted.status_code == 204

		remaining = client.get("/api/channels")
		assert remaining.status_code == 200
		assert [channel["number"] for channel in remaining.json()] == [1, 2, 3, 4]


def test_deleted_channels_persist_across_restart(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		deleted = client.delete("/api/channels/2")
		assert deleted.status_code == 204

		channels_after_delete = client.get("/api/channels")
		assert channels_after_delete.status_code == 200
		assert [channel["number"] for channel in channels_after_delete.json()] == [1, 2, 3]

	with TestClient(create_app()) as restarted_client:
		channels_after_restart = restarted_client.get("/api/channels")
		assert channels_after_restart.status_code == 200
		channel_payload = channels_after_restart.json()
		assert len(channel_payload) == 3
		assert [channel["number"] for channel in channel_payload] == [1, 2, 3]


def test_webrtc_offer_route_delegates_to_manager(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		captured: dict[str, object] = {}

		class DummyAnswer:
			sdp = "dummy-sdp"
			type = "answer"

		class DummyManager:
			async def create_answer(self, **kwargs):
				captured.update(kwargs)
				return DummyAnswer()

		client.app.state.webrtc_manager = DummyManager()
		response = client.post(
			"/api/streaming/webrtc/offer",
			json={
				"sdp": "offer-sdp",
				"type": "offer",
				"channel_ids": [1, 2],
				"replay_seconds": 3.5,
			},
		)
		assert response.status_code == 200
		assert response.json() == {"sdp": "dummy-sdp", "type": "answer"}
		assert captured == {
			"sdp": "offer-sdp",
			"type_": "offer",
			"input_sources": [(0, 0.0), (1, 0.0)],
			"replay_seconds": 3.5,
		}


def test_scene_routes_support_programming(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		channels = client.get("/api/channels").json()
		created = client.post(
			"/api/scenes",
			json={
				"name": "Scene 2",
				"sync_osc_address": "/qlab/scene/2",
				"sync_osc_argument": "GO",
				"sync_midi_pattern": "program_change:12",
				"channel_assignments": [
					{"channel_id": channels[0]["id"], "state": "onstage"},
					{"channel_id": channels[1]["id"], "state": "ready"},
				],
			},
		)
		assert created.status_code == 201
		created_payload = created.json()
		assert created_payload["name"] == "Scene 2"
		assert created_payload["sync_osc_address"] == "/qlab/scene/2"
		assert created_payload["sync_midi_pattern"] == "program_change:12"
		assert len(created_payload["channel_assignments"]) == 2

		updated = client.patch(
			f"/api/scenes/{created_payload['id']}",
			json={
				"order_index": 0,
				"channel_assignments": [
					{"channel_id": channels[0]["id"], "state": "ready"},
				],
			},
		)
		assert updated.status_code == 200
		assert updated.json()["order_index"] == 0

		settings_patch = client.patch(
			"/api/settings",
			json={"scene_mode_enabled": True, "active_scene_id": created_payload["id"]},
		)
		assert settings_patch.status_code == 200
		assert settings_patch.json()["scene_mode_enabled"] is True
		assert settings_patch.json()["active_scene_id"] == created_payload["id"]

		scenes = client.get("/api/scenes")
		assert scenes.status_code == 200
		assert scenes.json()[0]["id"] == created_payload["id"]

		deleted = client.delete(f"/api/scenes/{created_payload['id']}")
		assert deleted.status_code == 204


def test_sync_routes_apply_external_scene_event(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		created = client.post(
			"/api/scenes",
			json={
				"name": "Scene 2",
				"sync_osc_address": "/qlab/scene/2",
				"sync_osc_argument": "GO",
			},
		)
		assert created.status_code == 201
		created_scene_id = created.json()["id"]

		settings_patch = client.patch(
			"/api/settings",
			json={
				"external_sync_enabled": True,
				"external_sync_transport": "osc",
				"external_sync_osc_host": "127.0.0.1",
				"external_sync_osc_port": 0,
			},
		)
		assert settings_patch.status_code == 200

		status_payload = client.get("/api/sync/status")
		assert status_payload.status_code == 200
		assert status_payload.json()["enabled"] is True
		assert status_payload.json()["transport"] == "osc"

		applied = client.post(
			"/api/sync/events",
			json={
				"transport": "osc",
				"osc_address": "/qlab/scene/2",
				"osc_argument": "GO",
			},
		)
		assert applied.status_code == 200
		assert applied.json()["matched_scene_id"] == created_scene_id
		assert applied.json()["changed"] is True

		settings_after_event = client.get("/api/settings")
		assert settings_after_event.status_code == 200
		assert settings_after_event.json()["active_scene_id"] == created_scene_id


def test_active_alerts_route_maps_inputs_to_display_channels(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		updated = client.patch("/api/channels/2", json={"input_index": 0})
		assert updated.status_code == 200

		client.app.state.alert_analysis = SimpleNamespace(
			get_active_alerts=lambda: [
				AudioAlert(
					id="pop-0",
					kind="pop",
					severity="critical",
					input_index=0,
					title="Pop detected",
					message="Short impulsive spike detected on the input.",
					score=0.99,
					started_at=1.0,
					updated_at=2.0,
				),
			],
		)

		response = client.get("/api/alerts/active")
		assert response.status_code == 200
		assert response.json() == [
			{
				"id": "pop-0",
				"kind": "pop",
				"severity": "critical",
				"input_index": 0,
				"title": "Pop detected",
				"message": "Short impulsive spike detected on the input.",
				"score": 0.99,
				"started_at": 1.0,
				"updated_at": 2.0,
				"channel_ids": [1, 2],
				"channel_numbers": [1, 2],
				"channel_names": ["Channel 1", "Channel 2"],
			},
		]


def test_settings_route_accepts_hardware_audio_alias(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		monkeypatch.setattr("app.api.routes.resolve_input_device", lambda selector, required_channels: 1)

		async def fake_restart_audio_runtime(_updated_settings) -> None:
			return None

		client.app.state.restart_audio_runtime = fake_restart_audio_runtime
		response = client.patch(
			"/api/settings",
			json={
				"audio_source_mode": "hardware",
				"audio_input_device": "Core Audio::Built-in Microphone",
				"channel_count": 2,
			},
		)

		assert response.status_code == 200
		assert response.json()["audio_source_mode"] == "sounddevice"
		assert response.json()["audio_input_device"] == "Core Audio::Built-in Microphone"


def test_showfile_export_and_import_routes_round_trip(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		updated_channel = client.patch("/api/channels/1", json={"name": "Lead Mic", "gain_db": 3.0})
		assert updated_channel.status_code == 200

		created_scene = client.post(
			"/api/scenes",
			json={
				"name": "Dress Rehearsal",
				"channel_assignments": [{"channel_id": 1, "state": "onstage"}],
			},
		)
		assert created_scene.status_code == 201

		exported = client.get("/api/showfile/export")
		assert exported.status_code == 200
		payload = exported.json()
		assert payload["format"] == "micwise-showfile"
		assert payload["settings"]["audio_source_mode"] == "synthetic"
		assert payload["channels"][0]["name"] == "Lead Mic"

		payload["settings"]["master_gain_db"] = 5.0
		payload["settings"]["alert_popup_duration_sec"] = 9
		payload["settings"]["rchat_username"] = "A2 Desk"
		payload["channels"][0]["name"] = "Imported Lead"
		payload["scenes"][0]["name"] = "Imported Scene 1"

		imported = client.post("/api/showfile/import", json=payload)
		assert imported.status_code == 200
		assert imported.json() == {"status": "ok", "channels": 4, "scenes": 2}

		settings = client.get("/api/settings")
		assert settings.status_code == 200
		assert settings.json()["master_gain_db"] == 5.0
		assert settings.json()["alert_popup_duration_sec"] == 9
		assert settings.json()["rchat_username"] == "A2 Desk"

		channels = client.get("/api/channels")
		assert channels.status_code == 200
		assert channels.json()[0]["name"] == "Imported Lead"

		scenes = client.get("/api/scenes")
		assert scenes.status_code == 200
		assert scenes.json()[0]["name"] == "Imported Scene 1"
