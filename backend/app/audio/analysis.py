"""Meter analysis services for the Mic-Wise backend MVP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np

from app.audio.buffer import AudioBuffer

# RMS history hops are fixed slices of audio time rather than one value per
# poll, so the channel activity trace keeps a steady time axis even when the
# event loop or WebSocket delivery jitters.
METER_HISTORY_HOP_MS = 50
# Never replay more than this much missed history in one snapshot; a longer
# stall restarts the history grid at the live edge.
METER_HISTORY_MAX_BACKLOG_MS = 2_000


def db_to_linear_gain(gain_db: float) -> float:
	"""Convert a gain value in decibels to a linear multiplier."""
	return float(10 ** (gain_db / 20.0))


@dataclass(slots=True)
class MeterSnapshot:
	"""A point-in-time view of per-channel meter values."""

	write_head: int
	window_frames: int
	channels: list[dict[str, object]]
	history_start_frame: int = 0
	history_hop_frames: int = 0

	def to_dict(self) -> dict[str, object]:
		"""Convert the snapshot to a JSON-serialisable dictionary."""
		return {
			"write_head": self.write_head,
			"window_frames": self.window_frames,
			"history_start_frame": self.history_start_frame,
			"history_hop_frames": self.history_hop_frames,
			"channels": self.channels,
		}


class MeterAnalysisService:
	"""Continuously calculates RMS and peak values from the shared buffer."""

	def __init__(
		self,
		*,
		buffer_path: str,
		sample_rate: int,
		channels: int,
		window_ms: int,
		poll_interval_ms: int,
		playback_delay_frames: int = 0,
		broadcaster: object | None = None,
		metrics: object | None = None,
	) -> None:
		self.buffer_path = buffer_path
		self.sample_rate = sample_rate
		self.channels = channels
		self.window_frames = max(1, round(sample_rate * (window_ms / 1000.0)))
		self.poll_interval_seconds = poll_interval_ms / 1000.0
		self.playback_delay_frames = max(0, playback_delay_frames)
		self.broadcaster = broadcaster
		self.metrics = metrics
		self.history_hop_frames = max(1, round(sample_rate * (METER_HISTORY_HOP_MS / 1000.0)))
		self.history_max_backlog_hops = max(1, METER_HISTORY_MAX_BACKLOG_MS // METER_HISTORY_HOP_MS)
		self._history_cursor: int | None = None
		self._task: asyncio.Task[None] | None = None
		self.latest_snapshot = MeterSnapshot(
			write_head=0,
			window_frames=self.window_frames,
			channels=[
				{"channel": channel + 1, "rms": 0.0, "peak": 0.0, "rms_history": []}
				for channel in range(channels)
			],
			history_hop_frames=self.history_hop_frames,
		)

	async def start(self) -> None:
		"""Start the continuous meter analysis loop."""
		if self._task is None:
			self._task = asyncio.create_task(self._run(), name="meter-analysis")

	async def stop(self) -> None:
		"""Stop the background meter analysis loop."""
		if self._task is None:
			return

		self._task.cancel()
		try:
			await self._task
		except asyncio.CancelledError:
			pass
		finally:
			self._task = None

	async def _run(self) -> None:
		"""Poll the shared buffer and publish meter updates."""
		with AudioBuffer(self.buffer_path) as buffer:
			while True:
				self.latest_snapshot = self._calculate_snapshot(buffer)
				if self.metrics is not None:
					self.metrics.record_meter_snapshot(self.latest_snapshot)
				if self.broadcaster is not None:
					await self.broadcaster.broadcast(self.latest_snapshot.to_dict())
				await asyncio.sleep(self.poll_interval_seconds)

	def _calculate_snapshot(self, buffer: AudioBuffer) -> MeterSnapshot:
		"""Calculate per-channel RMS and peak values for the playback-synchronised window."""
		latest_write_head = buffer.refresh_write_head()
		window_end = max(0, latest_write_head - self.playback_delay_frames)
		window_start = max(0, window_end - self.window_frames)
		history_start, history_rms = self._calculate_history(buffer, window_end)
		chunk = buffer.read(window_start, self.window_frames)
		if chunk.size == 0:
			return MeterSnapshot(
				write_head=window_end,
				window_frames=self.window_frames,
				channels=[
					{
						"channel": channel + 1,
						"rms": 0.0,
						"peak": 0.0,
						"rms_history": history_rms[:, channel].tolist(),
					}
					for channel in range(self.channels)
				],
				history_start_frame=history_start,
				history_hop_frames=self.history_hop_frames,
			)

		normalized = chunk.astype(np.float32) / 32_768.0
		rms_values = np.sqrt(np.mean(np.square(normalized), axis=0))
		peak_values = np.max(np.abs(normalized), axis=0)
		return MeterSnapshot(
			write_head=window_end,
			window_frames=int(chunk.shape[0]),
			channels=[
				{
					"channel": channel + 1,
					"rms": float(rms_values[channel]),
					"peak": float(peak_values[channel]),
					"rms_history": history_rms[:, channel].tolist(),
				}
				for channel in range(self.channels)
			],
			history_start_frame=history_start,
			history_hop_frames=self.history_hop_frames,
		)

	def _calculate_history(self, buffer: AudioBuffer, window_end: int) -> tuple[int, np.ndarray]:
		"""Return RMS for every complete history hop finished since the last snapshot.

		Hops sit on a fixed grid of absolute frame positions, so each slice of
		audio is measured exactly once regardless of poll timing.
		"""
		hop = self.history_hop_frames
		live_edge_hop = (window_end // hop) * hop
		cursor = self._history_cursor
		if cursor is None or cursor > window_end:
			# First pass, or the engine restarted with a fresh buffer.
			cursor = live_edge_hop
		cursor = max(cursor, live_edge_hop - (self.history_max_backlog_hops * hop))

		hop_count = (window_end - cursor) // hop
		self._history_cursor = cursor + (hop_count * hop)
		empty = np.zeros((0, self.channels), dtype=np.float32)
		if hop_count <= 0:
			return cursor, empty

		chunk = buffer.read(cursor, hop_count * hop)
		if chunk.shape[0] != hop_count * hop:
			# The requested span fell outside the retained window.
			return self._history_cursor, empty

		normalized = chunk.astype(np.float32).reshape(hop_count, hop, self.channels) / 32_768.0
		return cursor, np.sqrt(np.mean(np.square(normalized), axis=1))


def build_channel_waveform_preview(
	*,
	buffer_path: str,
	sample_rate: int,
	input_index: int,
	gain_db: float,
	seconds: float,
	points: int,
) -> tuple[float, list[float]]:
	"""Build a channel peak waveform preview over the requested time window."""
	frame_count = max(1, int(round(sample_rate * seconds)))
	with AudioBuffer(buffer_path) as buffer:
		samples = buffer.read_latest_channel(frame_count, input_index)

	if samples.size == 0:
		return 0.0, [0.0 for _ in range(points)]

	normalized = samples.astype(np.float32) / 32_768.0
	normalized = np.clip(normalized * db_to_linear_gain(gain_db), -1.0, 1.0)
	boundaries = np.linspace(0, normalized.shape[0], num=points + 1, dtype=int)
	values: list[float] = []
	for index in range(points):
		start = boundaries[index]
		end = boundaries[index + 1]
		if end <= start:
			segment = normalized[start : start + 1]
		else:
			segment = normalized[start:end]
		values.append(float(np.max(np.abs(segment))) if segment.size > 0 else 0.0)

	return samples.shape[0] / float(sample_rate), values
