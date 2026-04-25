"""Tests for streaming-track audio preparation."""

from __future__ import annotations

import numpy as np

from app.audio.buffer import AudioBuffer
from app.streaming.webrtc import BufferAudioStreamTrack, WebRTCStreamManager


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
		input_sources=[(0, 0.0), (2, 0.0)],
	)
	try:
		mixed = track._mix_selected_channels(frames)
		assert mixed.tolist() == [2000, 2500, 3000]
	finally:
		track.stop()


def test_buffer_audio_stream_track_stop_is_idempotent(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"

	with AudioBuffer(
		filename=str(buffer_path),
		channels=1,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(np.array([[1000], [2000]], dtype=np.int16))

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=1,
		sample_rate=48_000,
		input_sources=[(0, 0.0)],
	)

	track.stop()
	track.stop()


def test_buffer_audio_stream_track_applies_gain(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"
	frames = np.array(
		[
			[1000],
			[2000],
			[3000],
		],
		dtype=np.int16,
	)

	with AudioBuffer(
		filename=str(buffer_path),
		channels=1,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(frames)

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=1,
		sample_rate=48_000,
		input_sources=[(0, 6.0)],
	)
	try:
		mixed = track._mix_selected_channels(frames)
		assert mixed.tolist() == [1995, 3991, 5986]
	finally:
		track.stop()


def test_buffer_audio_stream_track_recovers_from_live_edge_underrun(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"
	frames = np.arange(6_000, dtype=np.int16).reshape(-1, 1)

	with AudioBuffer(
		filename=str(buffer_path),
		channels=1,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(frames)

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=1,
		sample_rate=48_000,
		input_sources=[(0, 0.0)],
	)
	try:
		latest = track.buffer.refresh_write_head()
		target_read_head = track._target_live_read_head(latest)
		expected = track.buffer.read(target_read_head, track.samples_per_frame)

		track._read_head = latest
		chunk = track._read_live_chunk(latest)

		assert chunk.shape == (track.samples_per_frame, 1)
		assert np.array_equal(chunk, expected)
		assert track._read_head == target_read_head + track.samples_per_frame
	finally:
		track.stop()


def test_buffer_audio_stream_track_repeats_last_sample_for_partial_frame(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"
	frames = np.arange(10, dtype=np.int16).reshape(-1, 1)

	with AudioBuffer(
		filename=str(buffer_path),
		channels=1,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(frames)

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=1,
		sample_rate=48_000,
		input_sources=[(0, 0.0)],
	)
	try:
		chunk = track._read_live_chunk(track.buffer.refresh_write_head())

		assert chunk.shape == (track.samples_per_frame, 1)
		assert chunk[:10, 0].tolist() == list(range(10))
		assert np.all(chunk[10:, 0] == 9)
	finally:
		track.stop()


def test_buffer_audio_stream_track_updates_selection_without_resetting_live_head(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"
	frames = np.arange(6_000, dtype=np.int16).reshape(-1, 1)

	with AudioBuffer(
		filename=str(buffer_path),
		channels=1,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(frames)

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=1,
		sample_rate=48_000,
		input_sources=[(0, 0.0)],
	)
	try:
		live_read_head = track._read_head
		track.update_selection(input_sources=[(0, 6.0)], replay_seconds=0.0)

		assert track._read_head == live_read_head
		assert track.input_sources[0][0] == 0

		track.update_selection(input_sources=[(0, 6.0)], replay_seconds=0.1)

		assert track._playback_mode == "replay"
		assert track._read_head < live_read_head
	finally:
		track.stop()


def test_buffer_audio_stream_track_crossfades_selection_changes(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"

	with AudioBuffer(
		filename=str(buffer_path),
		channels=1,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(np.full((480, 1), 12_000, dtype=np.int16))

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=1,
		sample_rate=48_000,
		input_sources=[(0, 0.0)],
	)
	try:
		chunk = np.full((track.samples_per_frame, 1), 12_000, dtype=np.int16)
		track.update_selection(input_sources=[], replay_seconds=0.0)
		mixed = track._mix_selected_channels(chunk)

		assert mixed[0] > 0
		assert mixed[min(track.fade_frames - 1, mixed.shape[0] - 1)] < mixed[0]
		assert mixed[-1] == 0
	finally:
		track.stop()


def test_webrtc_manager_handles_control_messages(tmp_path) -> None:
	buffer_path = tmp_path / "audio.buffer"
	with AudioBuffer(
		filename=str(buffer_path),
		channels=2,
		sample_rate=48_000,
		duration_sec=1,
		create=True,
	) as writer:
		writer.write(np.zeros((480, 2), dtype=np.int16))

	track = BufferAudioStreamTrack(
		buffer_path=str(buffer_path),
		total_channels=2,
		sample_rate=48_000,
		input_sources=[],
	)
	manager = WebRTCStreamManager(
		buffer_path=str(buffer_path),
		sample_rate=48_000,
		total_channels=2,
	)
	try:
		manager._handle_control_message(
			track,
			'{"input_sources": [[1, 6.0]], "replay_seconds": 0.0}',
		)

		assert len(track.input_sources) == 1
		assert track.input_sources[0][0] == 1
		assert track._playback_mode == "live"
	finally:
		track.stop()