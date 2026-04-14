"""Audio engine process responsible for filling the shared audio buffer."""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

from app.audio.buffer import AudioBuffer


@dataclass(slots=True)
class AudioEngineConfig:
	"""Runtime configuration for the audio engine."""

	buffer_path: str
	channels: int
	sample_rate: int
	buffer_duration_sec: int
	block_size: int
	source_mode: str = "synthetic"
	input_device: str | int | None = None
	synthetic_base_frequency_hz: float = 180.0
	synthetic_step_frequency_hz: float = 15.0
	synthetic_amplitude: int = 12_000


class AudioEngineProcess(mp.Process):
	"""Background process writing audio into the rolling buffer."""

	def __init__(self, config: AudioEngineConfig, stop_event: mp.Event) -> None:
		super().__init__(name="micwise-audio-engine", daemon=True)
		self.config = config
		self.stop_event = stop_event

	def run(self) -> None:
		"""Start the configured audio source loop."""
		with AudioBuffer(self.config.buffer_path, writable=True) as buffer:
			if self.config.source_mode == "synthetic":
				self._run_synthetic(buffer)
				return
			if self.config.source_mode == "sounddevice":
				self._run_sounddevice(buffer)
				return

			raise ValueError(
				f"Unsupported audio source mode: {self.config.source_mode}",
			)

	def _run_synthetic(self, buffer: AudioBuffer) -> None:
		"""Generate deterministic tone data for MVP development and testing."""
		channel_frequencies = (
			self.config.synthetic_base_frequency_hz
			+ np.arange(self.config.channels, dtype=np.float64)
			* self.config.synthetic_step_frequency_hz
		)
		phase = np.zeros(self.config.channels, dtype=np.float64)
		phase_step = (2.0 * np.pi * channel_frequencies) / self.config.sample_rate
		frame_index = np.arange(self.config.block_size, dtype=np.float64)[:, None]
		sleep_duration = self.config.block_size / self.config.sample_rate

		while not self.stop_event.is_set():
			waveform = np.sin(phase[None, :] + frame_index * phase_step[None, :])
			chunk = np.clip(
				np.round(waveform * self.config.synthetic_amplitude),
				-32_768,
				32_767,
			).astype(np.int16)
			buffer.write(chunk)
			phase = (phase + self.config.block_size * phase_step) % (2.0 * np.pi)
			self.stop_event.wait(sleep_duration)

	def _run_sounddevice(self, buffer: AudioBuffer) -> None:
		"""Capture audio from a PortAudio device and write it to the buffer."""

		def callback(
			indata: np.ndarray,
			frames: int,
			time_info: object,
			status: sd.CallbackFlags,
		) -> None:
			del frames, time_info
			if status:
				# For the MVP we keep logging simple and avoid extra dependencies.
				print(f"Audio callback status: {status}")
			buffer.write(indata)

		with sd.InputStream(
			samplerate=self.config.sample_rate,
			channels=self.config.channels,
			blocksize=self.config.block_size,
			dtype="int16",
			device=self.config.input_device,
			callback=callback,
		):
			while not self.stop_event.wait(0.25):
				pass
