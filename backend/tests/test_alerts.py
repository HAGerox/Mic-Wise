"""Tests for lightweight alert detection and RadioWorld packet helpers."""

from __future__ import annotations

import asyncio

import numpy as np

from app.audio.alerts import detect_feedback_severity, detect_pop_severity, detect_wind_severity
from app.network.radioworld import RadioWorldBroadcaster, build_radioworld_packet


def test_build_radioworld_packet_uses_expected_wire_format() -> None:
    assert build_radioworld_packet("192.0.2.134", "COMM1") == b"RWSENDIP192.0.2.134#COMM1"


def test_radioworld_broadcaster_sends_observed_text_sequence() -> None:
    broadcaster = RadioWorldBroadcaster(sender_ip="192.0.2.134")
    sent_commands: list[tuple[str, bool]] = []

    async def fake_send_command(command: str, *, duplicate: bool = True) -> None:
        sent_commands.append((command, duplicate))

    broadcaster._send_command = fake_send_command  # type: ignore[method-assign]

    asyncio.run(broadcaster._send_text("Hello"))

    assert sent_commands == [
        ("KEYP", True),
        ("KEYPHello", False),
        ("KEYPHello\n", False),
    ]


def test_radioworld_test_message_waits_before_enabling_flash(monkeypatch) -> None:
    broadcaster = RadioWorldBroadcaster(sender_ip="192.0.2.134", flash_settle_delay_seconds=0.12)
    broadcaster.update_settings(enabled=True, flash_enabled=True, hold_seconds=0)
    events: list[tuple[object, ...]] = []

    async def fake_send_text(message: str) -> None:
        events.append(("text", message))

    async def fake_send_command(command: str, *, duplicate: bool = True) -> None:
        events.append(("command", command, duplicate))

    async def fake_sleep(delay: float) -> None:
        events.append(("sleep", delay))

    broadcaster._send_text = fake_send_text  # type: ignore[method-assign]
    broadcaster._send_command = fake_send_command  # type: ignore[method-assign]
    monkeypatch.setattr("app.network.radioworld.asyncio.sleep", fake_sleep)

    asyncio.run(broadcaster.send_test_message())

    assert events == [
        ("text", "Mic-Wise RadioWorld test"),
        ("sleep", 0.12),
        ("command", "COMM0", True),
    ]


def test_detect_pop_severity_flags_strong_impulses() -> None:
    samples = np.zeros(4_096, dtype=np.float32)
    samples[2_048] = 1.0
    samples[2_049] = -0.9

    assert detect_pop_severity(samples) == "critical"


def test_detect_wind_severity_flags_low_frequency_rumble() -> None:
    sample_rate = 48_000
    duration_seconds = 0.75
    frame_count = int(sample_rate * duration_seconds)
    time_axis = np.arange(frame_count, dtype=np.float32) / sample_rate
    rumble = 0.28 * np.sin(2 * np.pi * 28 * time_axis)

    assert detect_wind_severity(rumble.astype(np.float32), sample_rate) == "critical"


def test_detect_feedback_severity_flags_narrowband_tones() -> None:
    sample_rate = 48_000
    frame_count = 4_096
    aligned_frequency = (170 * sample_rate) / frame_count
    time_axis = np.arange(frame_count, dtype=np.float32) / sample_rate
    tone = 0.3 * np.sin(2 * np.pi * aligned_frequency * time_axis)

    assert detect_feedback_severity(tone.astype(np.float32), sample_rate) == "critical"
