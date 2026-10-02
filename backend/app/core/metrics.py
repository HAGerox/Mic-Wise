"""In-process Prometheus metrics store for the Mic-Wise backend.

Analysis services push their latest values into an app-scoped
``MetricsStore``; the ``/metrics`` route refreshes the cheap runtime-state
gauges and renders the registry in the Prometheus text format. Each app owns
its own ``CollectorRegistry`` so multiple apps (tests, restarts) never collide
on the process-global default registry.
"""

from __future__ import annotations

import time

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Info,
    generate_latest,
)
from prometheus_client import GCCollector, PlatformCollector, ProcessCollector


ALERT_KINDS = ("pop", "wind", "feedback")
ALERT_SEVERITIES = ("warning", "critical")


class MetricsStore:
    """Holds the Prometheus registry and the metrics Mic-Wise publishes."""

    content_type = CONTENT_TYPE_LATEST

    def __init__(self, *, version: str = "", release: str = "") -> None:
        self.registry = CollectorRegistry()
        # ProcessCollector only reports on platforms with /proc (Linux); it
        # silently yields nothing elsewhere, so it is safe to always register.
        ProcessCollector(registry=self.registry)
        PlatformCollector(registry=self.registry)
        GCCollector(registry=self.registry)

        Info("micwise_build", "Mic-Wise build information.", registry=self.registry).info(
            {"version": version, "release": release},
        )

        self.input_rms = Gauge(
            "micwise_input_rms_level",
            "Latest RMS level per physical input as a linear ratio of full scale (0-1).",
            ["input"],
            registry=self.registry,
        )
        self.input_peak = Gauge(
            "micwise_input_peak_level",
            "Latest peak level per physical input as a linear ratio of full scale (0-1).",
            ["input"],
            registry=self.registry,
        )
        self.meter_last_update = Gauge(
            "micwise_meter_last_update_timestamp_seconds",
            "Unix time of the most recent meter analysis pass.",
            registry=self.registry,
        )
        self.frames_written = Counter(
            "micwise_audio_frames_written",
            "Audio frames written to the shared ring buffer by the audio engine.",
            registry=self.registry,
        )
        self.alerts = Counter(
            "micwise_audio_alerts",
            "Audio alert onsets per physical input, by kind (pop, wind, feedback) and onset severity.",
            ["kind", "severity", "input"],
            registry=self.registry,
        )
        self.alerts_active = Gauge(
            "micwise_audio_alerts_active",
            "Alerts currently active, by kind and severity.",
            ["kind", "severity"],
            registry=self.registry,
        )
        self.alerts_enabled = Gauge(
            "micwise_audio_alerts_enabled",
            "Whether audio alert detection is enabled (1) or disabled (0).",
            registry=self.registry,
        )
        self.audio_engine_up = Gauge(
            "micwise_audio_engine_up",
            "Whether the audio engine process is running (1) or not (0).",
            registry=self.registry,
        )
        self.audio_input_channels = Gauge(
            "micwise_audio_input_channels",
            "Number of physical input channels captured by the audio engine.",
            registry=self.registry,
        )
        self.audio_sample_rate = Gauge(
            "micwise_audio_sample_rate_hertz",
            "Audio engine sample rate in hertz.",
            registry=self.registry,
        )
        self.audio_source = Gauge(
            "micwise_audio_source_info",
            "Active audio source mode (value is always 1).",
            ["mode"],
            registry=self.registry,
        )
        self.websocket_clients = Gauge(
            "micwise_websocket_clients",
            "Connected meter WebSocket clients.",
            registry=self.registry,
        )
        self.webrtc_listeners = Gauge(
            "micwise_webrtc_listeners",
            "Active WebRTC listener peer connections.",
            registry=self.registry,
        )
        self.scene_sync_listening = Gauge(
            "micwise_scene_sync_listening",
            "Whether the external scene sync listener is active (1) or not (0), by transport.",
            ["transport"],
            registry=self.registry,
        )
        self._last_write_head = 0
        for kind in ALERT_KINDS:
            for severity in ALERT_SEVERITIES:
                self.alerts_active.labels(kind=kind, severity=severity).set(0)

    def configure_audio_runtime(self, *, channels: int, sample_rate: int, source_mode: str) -> None:
        """Reset per-input series when the audio runtime (re)starts."""
        # Channel count can shrink across restarts; drop series for inputs
        # that no longer exist rather than leaving stale levels behind.
        self.input_rms.clear()
        self.input_peak.clear()
        for channel in range(1, channels + 1):
            self.input_rms.labels(input=str(channel)).set(0)
            self.input_peak.labels(input=str(channel)).set(0)
        self.audio_input_channels.set(channels)
        self.audio_sample_rate.set(sample_rate)
        self.audio_source.clear()
        self.audio_source.labels(mode=source_mode).set(1)
        # A new runtime creates a fresh buffer whose write head starts at 0.
        self._last_write_head = 0

    def record_meter_snapshot(self, snapshot: object) -> None:
        """Push a ``MeterSnapshot``'s per-input levels into the store."""
        for channel in getattr(snapshot, "channels"):
            label = str(channel["channel"])
            self.input_rms.labels(input=label).set(float(channel["rms"]))
            self.input_peak.labels(input=label).set(float(channel["peak"]))
        self.record_write_head(int(getattr(snapshot, "write_head")))
        self.meter_last_update.set(time.time())

    def record_write_head(self, write_head: int) -> None:
        """Advance the frames-written counter from the buffer's monotonic write head."""
        if write_head < self._last_write_head:
            # The buffer was recreated without configure_audio_runtime.
            self._last_write_head = 0
        delta = write_head - self._last_write_head
        if delta > 0:
            self.frames_written.inc(delta)
        self._last_write_head = write_head

    def record_alert_onset(self, *, kind: str, severity: str, input_index: int) -> None:
        """Count a newly raised alert for a zero-based physical input index."""
        self.alerts.labels(kind=kind, severity=severity, input=str(input_index + 1)).inc()

    def refresh_runtime_state(self, state: object) -> None:
        """Sample cheap runtime-state gauges from ``app.state`` at scrape time."""
        audio_process = getattr(state, "audio_process", None)
        self.audio_engine_up.set(1 if audio_process is not None and audio_process.is_alive() else 0)

        websocket_manager = getattr(state, "websocket_manager", None)
        self.websocket_clients.set(websocket_manager.connection_count if websocket_manager is not None else 0)

        webrtc_manager = getattr(state, "webrtc_manager", None)
        self.webrtc_listeners.set(webrtc_manager.connection_count if webrtc_manager is not None else 0)

        alert_analysis = getattr(state, "alert_analysis", None)
        active_counts = {(kind, severity): 0 for kind in ALERT_KINDS for severity in ALERT_SEVERITIES}
        if alert_analysis is not None:
            self.alerts_enabled.set(1 if alert_analysis.enabled else 0)
            for alert in alert_analysis.get_active_alerts():
                key = (alert.kind, alert.severity)
                active_counts[key] = active_counts.get(key, 0) + 1
        else:
            self.alerts_enabled.set(0)
        for (kind, severity), count in active_counts.items():
            self.alerts_active.labels(kind=kind, severity=severity).set(count)

        scene_sync_service = getattr(state, "scene_sync_service", None)
        sync_status = scene_sync_service.status if scene_sync_service is not None else None
        self.scene_sync_listening.labels(transport="osc").set(1 if sync_status is not None and sync_status.osc_listening else 0)
        self.scene_sync_listening.labels(transport="midi").set(1 if sync_status is not None and sync_status.midi_listening else 0)

    def render(self) -> bytes:
        """Render the registry in the Prometheus text exposition format."""
        return generate_latest(self.registry)
