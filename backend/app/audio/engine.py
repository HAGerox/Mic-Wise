"""Audio engine process responsible for filling the shared audio buffer."""

from __future__ import annotations

import os
import multiprocessing as mp
import sys
import time
import traceback
from dataclasses import dataclass

import numpy as np

os.environ.setdefault("SD_ENABLE_ASIO", "1")

import sounddevice as sd

from app.audio.buffer import AudioBuffer
from app.audio.devices import resolve_input_device

# The engine always uses the spawn start method so behaviour is identical on
# macOS, Windows, and Linux. Forking the FastAPI parent (Linux default) would
# duplicate its asyncio loop, sqlite handles, and PortAudio state into the
# audio child.
SPAWN_CONTEXT = mp.get_context("spawn")


def create_engine_stop_event() -> mp.Event:
	"""Create a stop event compatible with the engine's spawn context."""
	return SPAWN_CONTEXT.Event()


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


class AudioEngineProcess(SPAWN_CONTEXT.Process):
	"""Background process writing audio into the rolling buffer."""

	def __init__(self, config: AudioEngineConfig, stop_event: mp.Event) -> None:
		super().__init__(name="micwise-audio-engine", daemon=True)
		self.config = config
		self.stop_event = stop_event

	def run(self) -> None:
		"""Start the configured audio source loop."""
		try:
			with AudioBuffer(self.config.buffer_path, writable=True) as buffer:
				if self.config.source_mode == "synthetic":
					self._run_synthetic(buffer)
					return
				if self.config.source_mode in {"sounddevice", "hardware"}:
					self._run_sounddevice(buffer)
					return

				raise ValueError(
					f"Unsupported audio source mode: {self.config.source_mode}",
				)
		except Exception:
			# A dead engine is surfaced via /api/health; make the cause visible
			# in the server log instead of dying silently.
			print(
				f"Audio engine failed (source_mode={self.config.source_mode}, "
				f"input_device={self.config.input_device!r}):",
				file=sys.stderr,
			)
			traceback.print_exc()
			raise

	def _wait_for_next_block(self, next_deadline: float, block_duration: float) -> float | None:
		"""Wait until the next synthetic block deadline without accumulating drift."""
		next_deadline += block_duration
		remaining = next_deadline - time.perf_counter()
		if remaining > 0 and self.stop_event.wait(remaining):
			return None
		return next_deadline

	def _run_synthetic(self, buffer: AudioBuffer) -> None:
		"""Generate deterministic tone data for MVP development and testing."""
		channel_frequencies = (
			self.config.synthetic_base_frequency_hz
			+ np.arange(self.config.channels, dtype=np.float64)
			* self.config.synthetic_step_frequency_hz
		)
		phase = np.zeros(self.config.channels, dtype=np.float64)
		phase_step = (2.0 * np.pi * channel_frequencies) / self.config.sample_rate
		amplitude_lfo_rates = 0.05 + (np.arange(self.config.channels, dtype=np.float64) * 0.015)
		amplitude_lfo_phase = np.zeros(self.config.channels, dtype=np.float64)
		amplitude_lfo_step = (2.0 * np.pi * amplitude_lfo_rates) / self.config.sample_rate
		accent_lfo_rates = 0.22 + (np.arange(self.config.channels, dtype=np.float64) * 0.01)
		accent_lfo_phase = np.zeros(self.config.channels, dtype=np.float64)
		accent_lfo_step = (2.0 * np.pi * accent_lfo_rates) / self.config.sample_rate
		frame_index = np.arange(self.config.block_size, dtype=np.float64)[:, None]
		block_duration = self.config.block_size / self.config.sample_rate
		next_deadline = time.perf_counter()

		while not self.stop_event.is_set():
			tone = np.sin(phase[None, :] + frame_index * phase_step[None, :])
			amplitude_envelope = 0.2 + 0.8 * (
				(np.sin(amplitude_lfo_phase[None, :] + frame_index * amplitude_lfo_step[None, :]) + 1.0)
				/ 2.0
			)
			accent_envelope = 0.85 + 0.15 * np.sin(
				accent_lfo_phase[None, :] + frame_index * accent_lfo_step[None, :],
			)
			waveform = tone * amplitude_envelope * accent_envelope
			chunk = np.clip(
				np.round(waveform * self.config.synthetic_amplitude),
				-32_768,
				32_767,
			).astype(np.int16)
			buffer.write(chunk)
			phase = (phase + self.config.block_size * phase_step) % (2.0 * np.pi)
			amplitude_lfo_phase = (
				amplitude_lfo_phase + self.config.block_size * amplitude_lfo_step
			) % (2.0 * np.pi)
			accent_lfo_phase = (
				accent_lfo_phase + self.config.block_size * accent_lfo_step
			) % (2.0 * np.pi)
			next_deadline = self._wait_for_next_block(next_deadline, block_duration)
			if next_deadline is None:
				break

	def _run_sounddevice(self, buffer: AudioBuffer) -> None:
		"""Capture audio from a PortAudio device and write it to the buffer."""
		resolved_input_device = resolve_input_device(
			self.config.input_device,
			required_channels=self.config.channels,
		)

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
			device=resolved_input_device,
			latency="low",
			callback=callback,
		):
			while not self.stop_event.wait(0.25):
				pass
