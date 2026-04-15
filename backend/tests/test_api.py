"""Integration tests for the backend API and browser signaling path."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def configure_test_environment(monkeypatch, tmp_path) -> None:
	"""Configure environment variables for isolated backend integration tests."""
	monkeypatch.setenv("MICWISE_DATA_DIRECTORY", str(tmp_path))
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

		channels = client.get("/api/channels")
		assert channels.status_code == 200
		assert len(channels.json()) == 4

		frontend = client.get("/")
		assert frontend.status_code == 200
		assert "Program show file" in frontend.text


def test_settings_and_waveform_routes(tmp_path, monkeypatch) -> None:
	configure_test_environment(monkeypatch, tmp_path)
	with TestClient(create_app()) as client:
		patch_response = client.patch(
			"/api/settings",
			json={"multi_listen_enabled": True, "active_mode": "configure"},
		)
		assert patch_response.status_code == 200
		assert patch_response.json()["multi_listen_enabled"] is True
		assert patch_response.json()["active_mode"] == "configure"

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
			"input_indices": [0, 1],
			"replay_seconds": 3.5,
		}