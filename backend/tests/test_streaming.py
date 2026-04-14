"""Tests for streaming-track audio preparation."""

from __future__ import annotations

import numpy as np

from app.audio.buffer import AudioBuffer
from app.streaming.webrtc import BufferAudioStreamTrack


def test_buffer_audio_stream_track_mixes_selected_channels(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"
	frames = np.array(
		[
			[1000, -1000, 3000],
			[2000, -2000, 3000],
			[3000, -3000, 3000],
		],
		dtype=np.int16,
	)

	with AudioBuffer(
		filename=str(buffer_path),
		channels=3,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(frames)

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=3,
		sample_rate=48_000,
		channel_numbers=[1, 3],
	)
	try:
		mixed = track._mix_selected_channels(frames)
		assert mixed.tolist() == [2000, 2500, 3000]
	finally:
		track.stop()