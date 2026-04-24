"""Tests for meter analysis timing alignment."""

from __future__ import annotations

import numpy as np

from app.audio.analysis import MeterAnalysisService
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
