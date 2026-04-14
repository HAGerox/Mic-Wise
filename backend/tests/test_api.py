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

		settings = client.get("/api/settings")
		assert settings.status_code == 200
		assert settings.json()["channel_count"] == 4

		channels = client.get("/api/channels")
		assert channels.status_code == 200
		assert len(channels.json()) == 4

		frontend = client.get("/")
		assert frontend.status_code == 200
		assert "Mic-Wise MVP" in frontend.text


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
				"channel_numbers": [1, 2],
				"replay_seconds": 3.5,
			},
		)
		assert response.status_code == 200
		assert response.json() == {"sdp": "dummy-sdp", "type": "answer"}
		assert captured == {
			"sdp": "offer-sdp",
			"type_": "offer",
			"channel_numbers": [1, 2],
			"replay_seconds": 3.5,
		}