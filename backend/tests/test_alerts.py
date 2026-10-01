"""Tests for lightweight alert detection and RChat packet helpers."""

from __future__ import annotations

import asyncio
import socket
import threading

import numpy as np

from app.audio.alerts import detect_feedback_severity, detect_pop_severity, detect_wind_severity
from app.network.rchat import RChatBroadcaster, build_rchat_packet


def test_detection_scores_are_calculated_once_per_channel(monkeypatch) -> None:
    from app.audio import alerts

    scores = []

    def score(kind):
        def calculate(*_args):
            scores.append(kind)
            return 0.8
        return calculate

    monkeypatch.setattr(alerts, "_normalised_pop_score", score("pop"))
    monkeypatch.setattr(alerts, "_normalised_wind_score", score("wind"))
    monkeypatch.setattr(alerts, "_normalised_feedback_score", score("feedback"))
    outcomes = alerts._build_detection_outcomes(np.zeros(100, dtype=np.float32), 48_000)

    assert scores == ["pop", "wind", "feedback"]
    assert [outcome.kind for outcome in outcomes] == ["pop", "wind", "feedback"]
    assert all(outcome.severity == "critical" for outcome in outcomes)


def test_slow_alert_detection_leaves_api_loop_responsive(tmp_path, monkeypatch) -> None:
    from app.audio import alerts
    from app.audio.buffer import AudioBuffer

    buffer_path = str(tmp_path / "audio.buffer")
    with AudioBuffer(buffer_path, channels=1, sample_rate=1_000, duration_sec=1, create=True) as writer:
        writer.write(np.zeros((100, 1), dtype=np.int16))

    service = alerts.AlertAnalysisService(buffer_path=buffer_path, sample_rate=1_000, channels=1)
    release = threading.Event()

    async def scenario():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        finished = threading.Event()
        worker_was_released = []

        def slow_detect(*_args):
            loop.call_soon_threadsafe(started.set)
            worker_was_released.append(release.wait(timeout=2))
            finished.set()
            return []

        monkeypatch.setattr(alerts, "_build_detection_outcomes", slow_detect)
        await service.start()
        try:
            await asyncio.wait_for(started.wait(), timeout=3)
            # Stand in for a channel/scene request while detection is running.
            assert not finished.is_set()
            release.set()
            await asyncio.to_thread(finished.wait, 2)
            assert worker_was_released == [True]
        finally:
            release.set()
            await service.stop()

    asyncio.run(scenario())


def test_disabling_alerts_during_analysis_does_not_restore_old_alerts(tmp_path, monkeypatch) -> None:
    from app.audio import alerts
    from app.audio.buffer import AudioBuffer

    buffer_path = str(tmp_path / "audio.buffer")
    with AudioBuffer(buffer_path, channels=1, sample_rate=1_000, duration_sec=1, create=True) as writer:
        writer.write(np.zeros((100, 1), dtype=np.int16))
    service = alerts.AlertAnalysisService(buffer_path=buffer_path, sample_rate=1_000, channels=1)

    async def scenario():
        async def disable_during_work(function, *args):
            service.apply_settings(enabled=False)
            return [[alerts.DetectionOutcome("pop", "critical", 1.0, "Pop", "Pop")]]

        monkeypatch.setattr(alerts.asyncio, "to_thread", disable_during_work)
        await service.start()
        try:
            await asyncio.sleep(0)
            assert service.get_active_alerts() == []
            assert service.latest_alerts == []
        finally:
            await service.stop()

    asyncio.run(scenario())


def test_build_rchat_packet_uses_expected_utf8_wire_format() -> None:
    assert build_rchat_packet("192.0.2.134", "Mic-Wise", "KEYPCafé") == (
        b"RWSENDIP192.0.2.134#USERMic-Wise#KEYPCaf\xc3\xa9"
    )


def test_rchat_broadcaster_sends_one_complete_text_datagram() -> None:
    broadcaster = RChatBroadcaster(sender_ip="192.0.2.134")
    sent_commands: list[str] = []

    async def fake_send_command(command: str) -> None:
        sent_commands.append(command)

    broadcaster._send_command = fake_send_command  # type: ignore[method-assign]

    asyncio.run(broadcaster._send_text("Hello"))

    assert sent_commands == ["KEYPHello"]


def test_rchat_test_message_uses_configured_username_and_flash_command() -> None:
    broadcaster = RChatBroadcaster(sender_ip="192.0.2.134")
    broadcaster.update_settings(enabled=True, flash_enabled=True, hold_seconds=0, username="Sound # 1")
    events: list[tuple[object, ...]] = []

    async def fake_send_text(message: str) -> None:
        events.append(("text", message))

    async def fake_send_command(command: str) -> None:
        events.append(("command", command))

    broadcaster._send_text = fake_send_text  # type: ignore[method-assign]
    broadcaster._send_command = fake_send_command  # type: ignore[method-assign]
    status = asyncio.run(broadcaster.send_test_message())

    assert events == [
        ("text", "Mic-Wise RChat test"),
        ("command", "COMM0"),
    ]
    assert status.username == "Sound   1"


def test_rchat_send_falls_back_when_source_port_is_already_in_use(monkeypatch) -> None:
    broadcaster = RChatBroadcaster(sender_ip="192.0.2.134", destination_address="192.0.2.255")
    broadcaster.update_settings(enabled=True, flash_enabled=False, hold_seconds=0, username="Mic-Wise")
    broadcaster.sender_ip = "192.0.2.134"
    bind_addresses: list[tuple[str, int]] = []
    sent_packets: list[tuple[bytes, tuple[str, int]]] = []

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def setsockopt(self, *_args) -> None:
            return None

        def bind(self, address: tuple[str, int]) -> None:
            bind_addresses.append(address)
            if address[1] == 1090:
                raise OSError("address in use")

        def getsockname(self) -> tuple[str, int]:
            return ("192.0.2.134", 54321)

        def sendto(self, payload: bytes, destination: tuple[str, int]) -> None:
            sent_packets.append((payload, destination))

    monkeypatch.setattr(socket, "socket", lambda *_args: FakeSocket())

    broadcaster._send_command_sync("KEYPHello")

    assert bind_addresses == [("", 1090), ("", 0)]
    assert sent_packets == [
        (b"RWSENDIP192.0.2.134#USERMic-Wise#KEYPHello", ("192.0.2.255", 1090)),
    ]
    assert broadcaster.get_send_status().source_port == 54321


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
