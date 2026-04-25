"""Tests for meter analysis timing alignment."""

from __future__ import annotations

import numpy as np

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
