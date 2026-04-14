"""Meter analysis services for the Mic-Wise backend MVP."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import numpy as np

from app.audio.buffer import AudioBuffer


@dataclass(slots=True)
class MeterSnapshot:
	"""A point-in-time view of per-channel meter values."""

	write_head: int
	window_frames: int
	channels: list[dict[str, float | int]]

	def to_dict(self) -> dict[str, object]:
		"""Convert the snapshot to a JSON-serialisable dictionary."""
		return {
			"write_head": self.write_head,
			"window_frames": self.window_frames,
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
		broadcaster: object | None = None,
	) -> None:
		self.buffer_path = buffer_path
		self.sample_rate = sample_rate
		self.channels = channels
		self.window_frames = max(1, round(sample_rate * (window_ms / 1000.0)))
		self.poll_interval_seconds = poll_interval_ms / 1000.0
		self.broadcaster = broadcaster
		self._task: asyncio.Task[None] | None = None
		self.latest_snapshot = MeterSnapshot(
			write_head=0,
			window_frames=self.window_frames,
			channels=[
				{"channel": channel + 1, "rms": 0.0, "peak": 0.0}
				for channel in range(channels)
			],
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
				if self.broadcaster is not None:
					await self.broadcaster.broadcast(self.latest_snapshot.to_dict())
				await asyncio.sleep(self.poll_interval_seconds)

	def _calculate_snapshot(self, buffer: AudioBuffer) -> MeterSnapshot:
		"""Calculate per-channel RMS and peak values for the current window."""
		chunk = buffer.read_latest(self.window_frames)
		write_head = buffer.refresh_write_head()
		if chunk.size == 0:
			return MeterSnapshot(
				write_head=write_head,
				window_frames=self.window_frames,
				channels=[
					{"channel": channel + 1, "rms": 0.0, "peak": 0.0}
					for channel in range(self.channels)
				],
			)

		normalized = chunk.astype(np.float32) / 32_768.0
		rms_values = np.sqrt(np.mean(np.square(normalized), axis=0))
		peak_values = np.max(np.abs(normalized), axis=0)
		return MeterSnapshot(
			write_head=write_head,
			window_frames=int(chunk.shape[0]),
			channels=[
				{
					"channel": channel + 1,
					"rms": float(rms_values[channel]),
					"peak": float(peak_values[channel]),
				}
				for channel in range(self.channels)
			],
		)


def build_channel_waveform_preview(
	*,
	buffer_path: str,
	sample_rate: int,
	input_index: int,
	seconds: float,
	points: int,
) -> tuple[float, list[float]]:
	"""Build a channel RMS waveform preview over the requested time window."""
	frame_count = max(1, int(round(sample_rate * seconds)))
	with AudioBuffer(buffer_path) as buffer:
		samples = buffer.read_latest_channel(frame_count, input_index)

	if samples.size == 0:
		return 0.0, [0.0 for _ in range(points)]

	normalized = samples.astype(np.float32) / 32_768.0
	boundaries = np.linspace(0, normalized.shape[0], num=points + 1, dtype=int)
	values: list[float] = []
	for index in range(points):
		start = boundaries[index]
		end = boundaries[index + 1]
		if end <= start:
			segment = normalized[start : start + 1]
		else:
			segment = normalized[start:end]
		values.append(float(np.sqrt(np.mean(np.square(segment)))))

	return samples.shape[0] / float(sample_rate), values
