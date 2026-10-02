"""Tests for the Prometheus metrics store and /metrics endpoint."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app.audio.alerts import AlertAnalysisService, DetectionOutcome
from app.audio.analysis import MeterSnapshot
from app.core.metrics import MetricsStore
from app.main import create_app


def configure_test_environment(monkeypatch, tmp_path) -> None:
    """Isolate the app's show data and runtime buffer under tmp_path."""
    monkeypatch.setenv("MICWISE_DATA_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("MICWISE_RUNTIME_DIRECTORY", str(tmp_path / "runtime"))
    monkeypatch.setenv("MICWISE_SHOW_FILENAME", "metrics.micwise")
    monkeypatch.setenv("MICWISE_BUFFER_FILENAME", "metrics.buffer")
    monkeypatch.setenv("MICWISE_DEFAULT_CHANNEL_COUNT", "4")
    monkeypatch.setenv("MICWISE_DEFAULT_SAMPLE_RATE", "48000")
    monkeypatch.setenv("MICWISE_DEFAULT_BUFFER_DURATION_SEC", "5")
    monkeypatch.setenv("MICWISE_DEFAULT_BLOCK_SIZE", "480")
    monkeypatch.setenv("MICWISE_ZEROCONF_ENABLED", "false")


def _samples(payload: str) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    """Parse exposition text into {(sample name, sorted labels): value}."""
    return {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in text_string_to_metric_families(payload)
        for sample in family.samples
    }


def _render(store: MetricsStore) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    return _samples(store.render().decode("utf-8"))


def test_meter_snapshot_pushes_per_input_levels_and_frame_counter() -> None:
    store = MetricsStore(version="1.0", release="test")
    store.configure_audio_runtime(channels=2, sample_rate=48_000, source_mode="synthetic")
    store.record_meter_snapshot(
        MeterSnapshot(
            write_head=4_800,
            window_frames=480,
            channels=[
                {"channel": 1, "rms": 0.25, "peak": 0.5},
                {"channel": 2, "rms": 0.0, "peak": 0.0},
            ],
        ),
    )
    store.record_write_head(9_600)

    samples = _render(store)
    assert samples[("micwise_input_rms_level", (("input", "1"),))] == 0.25
    assert samples[("micwise_input_peak_level", (("input", "1"),))] == 0.5
    assert samples[("micwise_input_rms_level", (("input", "2"),))] == 0.0
    assert samples[("micwise_audio_frames_written_total", ())] == 9_600
    assert samples[("micwise_audio_input_channels", ())] == 2
    assert samples[("micwise_audio_sample_rate_hertz", ())] == 48_000
    assert samples[("micwise_audio_source_info", (("mode", "synthetic"),))] == 1
    assert samples[("micwise_build_info", (("release", "test"), ("version", "1.0")))] == 1
    assert samples[("micwise_meter_last_update_timestamp_seconds", ())] > 0


def test_runtime_restart_drops_stale_inputs_and_keeps_frame_counter_monotonic() -> None:
    store = MetricsStore()
    store.configure_audio_runtime(channels=4, sample_rate=48_000, source_mode="synthetic")
    store.record_write_head(1_000)
    store.configure_audio_runtime(channels=2, sample_rate=44_100, source_mode="sounddevice")
    store.record_write_head(250)

    samples = _render(store)
    inputs = {dict(labels)["input"] for name, labels in samples if name == "micwise_input_rms_level"}
    assert inputs == {"1", "2"}
    assert samples[("micwise_audio_frames_written_total", ())] == 1_250
    assert ("micwise_audio_source_info", (("mode", "synthetic"),)) not in samples
    assert samples[("micwise_audio_source_info", (("mode", "sounddevice"),))] == 1


def test_alert_service_counts_onsets_not_every_detection_pass(tmp_path) -> None:
    store = MetricsStore()
    service = AlertAnalysisService(
        buffer_path=str(tmp_path / "unused.buffer"),
        sample_rate=1_000,
        channels=2,
        metrics=store,
    )
    pop = DetectionOutcome("pop", "warning", 0.5, "Pop detected", "Pop")
    critical_pop = DetectionOutcome("pop", "critical", 0.9, "Pop detected", "Pop")

    # The same pop stays visible across overlapping analysis windows.
    service._apply_detection_outcomes([[pop], []])
    service._apply_detection_outcomes([[critical_pop], []])
    service._apply_detection_outcomes([[], [pop]])

    samples = _render(store)
    assert samples[("micwise_audio_alerts_total", (("input", "1"), ("kind", "pop"), ("severity", "warning")))] == 1
    assert samples[("micwise_audio_alerts_total", (("input", "2"), ("kind", "pop"), ("severity", "warning")))] == 1
    assert ("micwise_audio_alerts_total", (("input", "1"), ("kind", "pop"), ("severity", "critical"))) not in samples


def test_refresh_runtime_state_samples_app_state() -> None:
    store = MetricsStore()
    alert_service = SimpleNamespace(
        enabled=True,
        get_active_alerts=lambda: [
            SimpleNamespace(kind="pop", severity="critical"),
            SimpleNamespace(kind="pop", severity="critical"),
        ],
    )
    state = SimpleNamespace(
        audio_process=SimpleNamespace(is_alive=lambda: True),
        websocket_manager=SimpleNamespace(connection_count=3),
        webrtc_manager=SimpleNamespace(connection_count=1),
        alert_analysis=alert_service,
        scene_sync_service=SimpleNamespace(status=SimpleNamespace(osc_listening=True, midi_listening=False)),
    )
    store.refresh_runtime_state(state)

    samples = _render(store)
    assert samples[("micwise_audio_engine_up", ())] == 1
    assert samples[("micwise_websocket_clients", ())] == 3
    assert samples[("micwise_webrtc_listeners", ())] == 1
    assert samples[("micwise_audio_alerts_enabled", ())] == 1
    assert samples[("micwise_audio_alerts_active", (("kind", "pop"), ("severity", "critical")))] == 2
    assert samples[("micwise_audio_alerts_active", (("kind", "wind"), ("severity", "warning")))] == 0
    assert samples[("micwise_scene_sync_listening", (("transport", "osc"),))] == 1
    assert samples[("micwise_scene_sync_listening", (("transport", "midi"),))] == 0

    store.refresh_runtime_state(SimpleNamespace())
    samples = _render(store)
    assert samples[("micwise_audio_engine_up", ())] == 0
    assert samples[("micwise_audio_alerts_active", (("kind", "pop"), ("severity", "critical")))] == 0


def test_metrics_endpoint_serves_prometheus_text_from_running_app(tmp_path, monkeypatch) -> None:
    configure_test_environment(monkeypatch, tmp_path)
    with TestClient(create_app()) as client:
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "version=" in response.headers["content-type"]

        samples = _samples(response.text)
        inputs = {dict(labels)["input"] for name, labels in samples if name == "micwise_input_peak_level"}
        assert inputs == {"1", "2", "3", "4"}
        assert samples[("micwise_audio_input_channels", ())] == 4
        assert ("micwise_audio_engine_up", ()) in samples
        assert ("micwise_audio_frames_written_total", ()) in samples
        assert ("micwise_audio_alerts_active", (("kind", "pop"), ("severity", "warning"))) in samples

        # The frontend static mount must not shadow the scrape endpoint.
        assert client.get("/api/health").status_code == 200
