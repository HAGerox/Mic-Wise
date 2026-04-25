"""Lightweight audio event detection and alert runtime services."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.audio.buffer import AudioBuffer


AlertKind = Literal["pop", "wind", "feedback"]
AlertSeverity = Literal["warning", "critical"]
AlertNotifier = Callable[[str], Awaitable[None]]


@dataclass(slots=True)
class AudioAlert:
    """Active alert currently tracked by the backend."""

    id: str
    kind: AlertKind
    severity: AlertSeverity
    input_index: int
    title: str
    message: str
    score: float
    started_at: float
    updated_at: float

    def to_dict(self) -> dict[str, object]:
        """Serialize the alert for API responses."""
        return {
            "id": self.id,
            "kind": self.kind,
            "severity": self.severity,
            "input_index": self.input_index,
            "title": self.title,
            "message": self.message,
            "score": self.score,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class DetectionOutcome:
    """Internal result used while tracking alert state."""

    kind: AlertKind
    severity: AlertSeverity
    score: float
    title: str
    message: str


def _safe_rms(samples: np.ndarray) -> float:
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float32), dtype=np.float32)))


def _severity_from_score(
    score: float,
    *,
    warning_threshold: float,
    critical_threshold: float,
) -> AlertSeverity | None:
    if score >= critical_threshold:
        return "critical"
    if score >= warning_threshold:
        return "warning"
    return None


def _normalised_pop_score(samples: np.ndarray) -> float:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    rms = _safe_rms(samples)
    crest_factor = peak / max(rms, 1e-5)
    transient_peak = float(np.max(np.abs(np.diff(samples)))) if samples.size > 1 else 0.0
    impulse_peak = float(np.max(np.abs(samples[- min(samples.size, 512) :]))) if samples.size else 0.0

    peak_component = np.clip((peak - 0.42) / 0.4, 0.0, 1.0)
    transient_component = np.clip((transient_peak - 0.28) / 0.52, 0.0, 1.0)
    crest_component = np.clip((crest_factor - 4.0) / 7.0, 0.0, 1.0)
    impulse_component = np.clip((impulse_peak - 0.45) / 0.35, 0.0, 1.0)
    return float((0.34 * peak_component) + (0.32 * transient_component) + (0.18 * crest_component) + (0.16 * impulse_component))


def detect_pop_severity(samples: np.ndarray) -> AlertSeverity | None:
    """Flag strong wideband transients typical of pops or handling hits."""
    score = _normalised_pop_score(samples)
    return _severity_from_score(score, warning_threshold=0.42, critical_threshold=0.74)


def _normalised_wind_score(samples: np.ndarray, sample_rate: int) -> float:
    if samples.size == 0:
        return 0.0

    spectrum = np.abs(np.fft.rfft(samples * np.hanning(samples.size)))
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    total_energy = float(np.sum(spectrum))
    if total_energy <= 1e-8:
        return 0.0

    low_band_energy = float(np.sum(spectrum[frequencies <= 180.0]))
    very_low_band_energy = float(np.sum(spectrum[frequencies <= 80.0]))
    low_band_ratio = low_band_energy / total_energy
    very_low_band_ratio = very_low_band_energy / total_energy
    rms = _safe_rms(samples)
    zero_crossings = float(np.mean(np.abs(np.diff(np.signbit(samples)).astype(np.float32)))) if samples.size > 1 else 0.0

    low_band_component = np.clip((low_band_ratio - 0.48) / 0.42, 0.0, 1.0)
    very_low_component = np.clip((very_low_band_ratio - 0.26) / 0.42, 0.0, 1.0)
    zcr_component = np.clip((0.12 - zero_crossings) / 0.12, 0.0, 1.0)
    rms_component = np.clip((rms - 0.03) / 0.18, 0.0, 1.0)
    return float((0.34 * low_band_component) + (0.28 * very_low_component) + (0.18 * zcr_component) + (0.2 * rms_component))


def detect_wind_severity(samples: np.ndarray, sample_rate: int) -> AlertSeverity | None:
    """Flag low-frequency rumble consistent with wind noise."""
    score = _normalised_wind_score(samples, sample_rate)
    return _severity_from_score(score, warning_threshold=0.46, critical_threshold=0.72)


def _normalised_feedback_score(samples: np.ndarray, sample_rate: int) -> float:
    if samples.size == 0:
        return 0.0

    windowed = samples * np.hanning(samples.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    if spectrum.size == 0:
        return 0.0

    spectrum_sum = float(np.sum(spectrum))
    if spectrum_sum <= 1e-8:
        return 0.0

    peak_index = int(np.argmax(spectrum))
    peak_value = float(spectrum[peak_index])
    tonal_ratio = peak_value / spectrum_sum
    rms = _safe_rms(samples)
    frequencies = np.fft.rfftfreq(samples.size, d=1.0 / sample_rate)
    peak_frequency = float(frequencies[peak_index]) if peak_index < frequencies.size else 0.0

    neighbourhood_start = max(0, peak_index - 2)
    neighbourhood_end = min(spectrum.size, peak_index + 3)
    neighbourhood_energy = float(np.sum(spectrum[neighbourhood_start:neighbourhood_end]))
    neighbourhood_ratio = neighbourhood_energy / spectrum_sum

    tonal_component = np.clip((tonal_ratio - 0.08) / 0.24, 0.0, 1.0)
    neighbourhood_component = np.clip((neighbourhood_ratio - 0.14) / 0.36, 0.0, 1.0)
    rms_component = np.clip((rms - 0.015) / 0.16, 0.0, 1.0)
    frequency_component = np.clip((peak_frequency - 300.0) / 3_500.0, 0.0, 1.0)
    return float((0.4 * tonal_component) + (0.25 * neighbourhood_component) + (0.2 * rms_component) + (0.15 * frequency_component))


def detect_feedback_severity(samples: np.ndarray, sample_rate: int) -> AlertSeverity | None:
    """Flag narrowband tones consistent with feedback build-up."""
    score = _normalised_feedback_score(samples, sample_rate)
    return _severity_from_score(score, warning_threshold=0.44, critical_threshold=0.7)


def _build_detection_outcomes(samples: np.ndarray, sample_rate: int) -> list[DetectionOutcome]:
    pop_score = _normalised_pop_score(samples)
    pop_severity = detect_pop_severity(samples)

    wind_score = _normalised_wind_score(samples, sample_rate)
    wind_severity = detect_wind_severity(samples, sample_rate)

    feedback_score = _normalised_feedback_score(samples, sample_rate)
    feedback_severity = detect_feedback_severity(samples, sample_rate)

    outcomes: list[DetectionOutcome] = []
    if pop_severity is not None:
        outcomes.append(
            DetectionOutcome(
                kind="pop",
                severity=pop_severity,
                score=pop_score,
                title="Pop detected",
                message="Short impulsive spike detected on the input.",
            ),
        )
    if wind_severity is not None:
        outcomes.append(
            DetectionOutcome(
                kind="wind",
                severity=wind_severity,
                score=wind_score,
                title="Wind noise",
                message="Low-frequency rumble is building on the input.",
            ),
        )
    if feedback_severity is not None:
        outcomes.append(
            DetectionOutcome(
                kind="feedback",
                severity=feedback_severity,
                score=feedback_score,
                title="Feedback risk",
                message="Narrowband tone suggests feedback is starting to ring.",
            ),
        )
    return outcomes


class AlertAnalysisService:
    """Continuously scans the shared buffer for notable audio events."""

    def __init__(
        self,
        *,
        buffer_path: str,
        sample_rate: int,
        channels: int,
        poll_interval_ms: int = 250,
        analysis_window_ms: int = 750,
        active_hold_ms: int = 2_500,
        notification_cooldown_ms: int = 8_000,
        enabled: bool = True,
        notifier: AlertNotifier | None = None,
    ) -> None:
        self.buffer_path = buffer_path
        self.sample_rate = sample_rate
        self.channels = channels
        self.poll_interval_seconds = max(0.05, poll_interval_ms / 1000.0)
        self.analysis_window_frames = max(1, int(round(sample_rate * (analysis_window_ms / 1000.0))))
        self.active_hold_seconds = max(0.5, active_hold_ms / 1000.0)
        self.notification_cooldown_seconds = max(0.5, notification_cooldown_ms / 1000.0)
        self.enabled = enabled
        self.notifier = notifier
        self.latest_alerts: list[AudioAlert] = []
        self._active_alerts: dict[tuple[AlertKind, int], AudioAlert] = {}
        self._last_notified_at: dict[tuple[AlertKind, int], float] = {}
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Start the background alert analysis loop."""
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="alert-analysis")

    async def stop(self) -> None:
        """Stop the background analysis loop."""
        if self._task is None:
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    def apply_settings(self, *, enabled: bool) -> None:
        """Apply simple runtime configuration updates without a restart."""
        self.enabled = bool(enabled)
        if not self.enabled:
            self._active_alerts.clear()
            self.latest_alerts = []

    def get_active_alerts(self) -> list[AudioAlert]:
        """Return the currently active alerts sorted newest first."""
        return sorted(self.latest_alerts, key=lambda alert: alert.updated_at, reverse=True)

    async def _run(self) -> None:
        """Poll the shared buffer and maintain the active alert set."""
        with AudioBuffer(self.buffer_path) as buffer:
            while True:
                self._analyze_buffer(buffer)
                await asyncio.sleep(self.poll_interval_seconds)

    def _analyze_buffer(self, buffer: AudioBuffer) -> None:
        """Inspect the latest audio window for detectable issues."""
        if not self.enabled:
            self._active_alerts.clear()
            self.latest_alerts = []
            return

        chunk = buffer.read_latest(self.analysis_window_frames)
        if chunk.size == 0:
            self._expire_stale_alerts(time.time(), active_keys=set())
            return

        normalized = chunk.astype(np.float32) / 32_768.0
        now = time.time()
        active_keys: set[tuple[AlertKind, int]] = set()
        new_notifications: list[str] = []
        for input_index in range(min(self.channels, normalized.shape[1])):
            channel_samples = normalized[:, input_index]
            for outcome in _build_detection_outcomes(channel_samples, self.sample_rate):
                key = (outcome.kind, input_index)
                active_keys.add(key)
                existing_alert = self._active_alerts.get(key)
                if existing_alert is None:
                    alert = AudioAlert(
                        id=f"{outcome.kind}-{input_index}-{int(now * 1000)}",
                        kind=outcome.kind,
                        severity=outcome.severity,
                        input_index=input_index,
                        title=outcome.title,
                        message=outcome.message,
                        score=outcome.score,
                        started_at=now,
                        updated_at=now,
                    )
                    self._active_alerts[key] = alert
                    new_notifications.append(self._format_notification_message(alert))
                else:
                    should_notify_again = (
                        outcome.severity == "critical"
                        and existing_alert.severity != "critical"
                    )
                    existing_alert.severity = outcome.severity
                    existing_alert.title = outcome.title
                    existing_alert.message = outcome.message
                    existing_alert.score = outcome.score
                    existing_alert.updated_at = now
                    if should_notify_again:
                        new_notifications.append(self._format_notification_message(existing_alert))

        self._expire_stale_alerts(now, active_keys=active_keys)
        self.latest_alerts = self.get_active_alerts()

        if self.notifier is None:
            return

        for key, alert in self._active_alerts.items():
            if self._format_notification_message(alert) not in new_notifications:
                continue
            last_notified_at = self._last_notified_at.get(key, 0.0)
            if now - last_notified_at < self.notification_cooldown_seconds:
                continue
            self._last_notified_at[key] = now
            asyncio.create_task(self.notifier(self._format_notification_message(alert)))

    def _expire_stale_alerts(self, now: float, *, active_keys: set[tuple[AlertKind, int]]) -> None:
        stale_keys = [
            key
            for key, alert in self._active_alerts.items()
            if key not in active_keys and (now - alert.updated_at) > self.active_hold_seconds
        ]
        for key in stale_keys:
            self._active_alerts.pop(key, None)

    @staticmethod
    def _format_notification_message(alert: AudioAlert) -> str:
        severity_label = "CRIT" if alert.severity == "critical" else "WARN"
        return f"{severity_label} CH {alert.input_index + 1}: {alert.title}"
