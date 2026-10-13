"""Tests for meter analysis timing alignment."""

from __future__ import annotations

import numpy as np
import pytest

from app.audio.analysis import MeterAnalysisService, build_channel_waveform_preview
from app.audio.buffer import AudioBuffer


def test_meter_analysis_service_uses_playback_delay_frames(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"
    frames = np.concatenate(
        (
            np.zeros((100, 1), dtype=np.int16),
            np.full((100, 1), 12_000, dtype=np.int16),
        ),
        axis=0,
    )

    with AudioBuffer(
        filename=str(buffer_path),
        channels=1,
        sample_rate=1_000,
        duration_sec=2,
        create=True,
    ) as writer:
        writer.write(frames)

    service = MeterAnalysisService(
        buffer_path=str(buffer_path),
        sample_rate=1_000,
        channels=1,
        window_ms=100,
        poll_interval_ms=50,
        playback_delay_frames=100,
    )

    with AudioBuffer(str(buffer_path)) as reader:
        snapshot = service._calculate_snapshot(reader)

    assert snapshot.write_head == 100
    assert snapshot.channels[0]["rms"] == 0.0
    assert snapshot.channels[0]["peak"] == 0.0


def test_build_channel_waveform_preview_uses_peak_values_for_more_detail(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"
    frames = np.array(
        [
            [0],
            [4_000],
            [16_000],
            [2_000],
            [0],
            [8_000],
        ],
        dtype=np.int16,
    )

    with AudioBuffer(
        filename=str(buffer_path),
        channels=1,
        sample_rate=6,
        duration_sec=2,
        create=True,
    ) as writer:
        writer.write(frames)

    seconds, values = build_channel_waveform_preview(
        buffer_path=str(buffer_path),
        sample_rate=6,
        input_index=0,
        gain_db=0.0,
        seconds=1.0,
        points=3,
    )

    assert seconds == 1.0
    assert values == [4_000 / 32_768, 16_000 / 32_768, 8_000 / 32_768]


def test_meter_history_measures_each_fixed_hop_exactly_once(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"
    with AudioBuffer(
        filename=str(buffer_path),
        channels=1,
        sample_rate=1_000,
        duration_sec=10,
        create=True,
    ) as writer:
        service = MeterAnalysisService(
            buffer_path=str(buffer_path),
            sample_rate=1_000,
            channels=1,
            window_ms=100,
            poll_interval_ms=50,
        )
        with AudioBuffer(str(buffer_path)) as reader:
            writer.write(np.zeros((120, 1), dtype=np.int16))
            first = service._calculate_snapshot(reader)
            # The first pass starts the grid at the live edge without replaying history.
            assert first.history_hop_frames == 50
            assert first.channels[0]["rms_history"] == []

            # Irregular poll spacing still yields one value per completed 50-frame hop.
            writer.write(np.full((30, 1), 16_384, dtype=np.int16))
            writer.write(np.full((50, 1), 8_192, dtype=np.int16))
            second = service._calculate_snapshot(reader)
            assert second.history_start_frame == 100
            assert second.channels[0]["rms_history"] == pytest.approx([np.sqrt(0.6 * 0.25), 0.25])

            third = service._calculate_snapshot(reader)
            assert third.channels[0]["rms_history"] == []

            writer.write(np.full((70, 1), 16_384, dtype=np.int16))
            fourth = service._calculate_snapshot(reader)
            assert fourth.history_start_frame == 200
            assert fourth.channels[0]["rms_history"] == pytest.approx([0.5])


def test_meter_history_skips_ahead_after_long_stall(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"
    with AudioBuffer(
        filename=str(buffer_path),
        channels=1,
        sample_rate=1_000,
        duration_sec=30,
        create=True,
    ) as writer:
        service = MeterAnalysisService(
            buffer_path=str(buffer_path),
            sample_rate=1_000,
            channels=1,
            window_ms=100,
            poll_interval_ms=50,
        )
        with AudioBuffer(str(buffer_path)) as reader:
            service._calculate_snapshot(reader)
            writer.write(np.zeros((10_000, 1), dtype=np.int16))
            snapshot = service._calculate_snapshot(reader)

    assert snapshot.history_start_frame == 8_000
    assert len(snapshot.channels[0]["rms_history"]) == 40
