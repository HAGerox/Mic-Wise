"""WebRTC audio streaming sourced from the shared audio buffer."""

from __future__ import annotations

import asyncio
import fractions
import json
import time

import numpy as np
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AUDIO_PTIME, AudioStreamTrack, MediaStreamError
from av import AudioFrame

from app.audio.buffer import AudioBuffer
from app.audio.playback import playback_sync_delay_frames


def db_to_linear_gain(gain_db: float) -> float:
	"""Convert a gain value in decibels to a linear multiplier."""
	return float(10 ** (gain_db / 20.0))


class BufferAudioStreamTrack(AudioStreamTrack):
	"""A WebRTC audio track reading and mixing frames from ``AudioBuffer``."""

	def __init__(
		self,
		*,
		buffer_path: str,
		total_channels: int,
		sample_rate: int,
		input_sources: list[tuple[int, float]],
		replay_seconds: float = 0.0,
	) -> None:
		super().__init__()
		self.buffer = AudioBuffer(buffer_path)
		self.total_channels = total_channels
		self.sample_rate = sample_rate
		self.samples_per_frame = max(1, int(round(AUDIO_PTIME * sample_rate)))
		self.live_edge_frames = playback_sync_delay_frames(sample_rate)
		self.input_sources: list[tuple[int, float]] = []
		self._playback_mode = "live"
		self._read_head = 0
		self.update_selection(input_sources=input_sources, replay_seconds=replay_seconds, reset_read_head=True)
		self._buffer_closed = False

	def _normalise_input_sources(
		self,
		input_sources: list[tuple[int, float]] | list[list[float | int]],
	) -> list[tuple[int, float]]:
		"""Convert incoming selection payloads into validated channel/gain pairs."""
		normalised: list[tuple[int, float]] = []
		for source in input_sources:
			if len(source) != 2:
				continue
			input_index, gain_db = source
			input_index = int(input_index)
			if 0 <= input_index < self.total_channels:
				normalised.append((input_index, db_to_linear_gain(float(gain_db))))
		return normalised

	def update_selection(
		self,
		*,
		input_sources: list[tuple[int, float]] | list[list[float | int]],
		replay_seconds: float = 0.0,
		reset_read_head: bool = False,
	) -> None:
		"""Update the mixed input selection without rebuilding the WebRTC transport."""
		self.input_sources = self._normalise_input_sources(input_sources)
		latest = self.buffer.refresh_write_head()
		earliest = max(0, latest - self.buffer.capacity)
		replay_frames = max(0, int(round(float(replay_seconds) * self.sample_rate)))

		if replay_frames > 0:
			self._playback_mode = "replay"
			self._read_head = max(earliest, latest - replay_frames)
			return

		if reset_read_head or self._playback_mode != "live":
			self._read_head = self._target_live_read_head(latest)
		self._playback_mode = "live"

	def _target_live_read_head(self, latest: int) -> int:
		"""Return a stable live-edge read position with a small safety cushion."""
		earliest = max(0, latest - self.buffer.capacity)
		return max(earliest, latest - self.live_edge_frames)

	def _read_live_chunk(self, latest: int) -> np.ndarray:
		"""Read a full frame from the buffer, recovering cleanly from underruns."""
		earliest = max(0, latest - self.buffer.capacity)
		target_read_head = self._target_live_read_head(latest)

		if self._read_head < earliest:
			self._read_head = target_read_head
		elif self._read_head + self.samples_per_frame > latest:
			self._read_head = target_read_head

		chunk = self.buffer.read(self._read_head, self.samples_per_frame)
		if chunk.shape[0] < self.samples_per_frame and latest > 0:
			self._read_head = target_read_head
			chunk = self.buffer.read(self._read_head, self.samples_per_frame)

		self._read_head += self.samples_per_frame
		if chunk.shape[0] >= self.samples_per_frame:
			return chunk

		if chunk.shape[0] == 0:
			return np.zeros((self.samples_per_frame, self.total_channels), dtype=np.int16)

		padding = np.repeat(chunk[-1:, :], self.samples_per_frame - chunk.shape[0], axis=0)
		return np.concatenate((chunk, padding), axis=0)

	async def recv(self) -> AudioFrame:
		"""Produce the next audio frame for transmission."""
		if self.readyState != "live":
			raise MediaStreamError

		if hasattr(self, "_timestamp"):
			self._timestamp += self.samples_per_frame
			wait = self._start + (self._timestamp / self.sample_rate) - time.perf_counter()
			await asyncio.sleep(max(0.0, wait))
		else:
			self._start = time.perf_counter()
			self._timestamp = 0

		latest = self.buffer.refresh_write_head()
		chunk = self._read_live_chunk(latest)

		mono = self._mix_selected_channels(chunk)
		frame = AudioFrame(format="s16", layout="mono", samples=self.samples_per_frame)
		frame.planes[0].update(mono.tobytes())
		frame.pts = self._timestamp
		frame.sample_rate = self.sample_rate
		frame.time_base = fractions.Fraction(1, self.sample_rate)
		return frame

	def _mix_selected_channels(self, chunk: np.ndarray) -> np.ndarray:
		"""Mix the selected input channels down to a mono program stream."""
		if not self.input_sources:
			return np.zeros(self.samples_per_frame, dtype=np.int16)

		selected = [
			chunk[:, input_index].astype(np.float32) * gain_linear
			for input_index, gain_linear in self.input_sources
		]
		if len(selected) == 1:
			mono = selected[0]
		else:
			mono = np.mean(np.stack(selected, axis=1), axis=1)

		return np.clip(np.round(mono), -32_768, 32_767).astype(np.int16)

	def stop(self) -> None:
		"""Release the shared buffer when the track ends."""
		if not self._buffer_closed:
			self.buffer.close()
			self._buffer_closed = True
		if self.readyState != "ended":
			super().stop()


class WebRTCStreamManager:
	"""Create and clean up peer connections for browser audio listeners."""

	def __init__(self, *, buffer_path: str, sample_rate: int, total_channels: int) -> None:
		self.buffer_path = buffer_path
		self.sample_rate = sample_rate
		self.total_channels = total_channels
		self._peer_connections: dict[RTCPeerConnection, BufferAudioStreamTrack] = {}

	async def create_answer(
		self,
		*,
		sdp: str,
		type_: str,
		input_sources: list[tuple[int, float]],
		replay_seconds: float = 0.0,
	) -> RTCSessionDescription:
		"""Create an SDP answer for a new listener connection."""
		peer_connection = RTCPeerConnection(configuration=RTCConfiguration(iceServers=[]))
		track = BufferAudioStreamTrack(
			buffer_path=self.buffer_path,
			total_channels=self.total_channels,
			sample_rate=self.sample_rate,
			input_sources=input_sources,
			replay_seconds=replay_seconds,
		)
		self._peer_connections[peer_connection] = track

		@peer_connection.on("datachannel")
		def on_datachannel(channel) -> None:
			@channel.on("message")
			def on_message(message: str | bytes) -> None:
				if not isinstance(message, str):
					return
				self._handle_control_message(track, message)

		@peer_connection.on("connectionstatechange")
		async def on_connectionstatechange() -> None:
			if peer_connection.connectionState in {"failed", "closed"}:
				await self._cleanup_connection(peer_connection)

		await peer_connection.setRemoteDescription(
			RTCSessionDescription(sdp=sdp, type=type_),
		)
		peer_connection.addTrack(track)
		answer = await peer_connection.createAnswer()
		await peer_connection.setLocalDescription(answer)
		assert peer_connection.localDescription is not None
		return peer_connection.localDescription

	def _handle_control_message(self, track: BufferAudioStreamTrack, message: str) -> None:
		"""Apply live selection updates sent over the persistent control channel."""
		try:
			payload = json.loads(message)
		except json.JSONDecodeError:
			return

		input_sources = payload.get("input_sources", [])
		replay_seconds = payload.get("replay_seconds", 0.0)
		if not isinstance(input_sources, list):
			return

		track.update_selection(
			input_sources=input_sources,
			replay_seconds=float(replay_seconds),
		)

	async def close_all(self) -> None:
		"""Close all active peer connections and release their tracks."""
		for peer_connection in list(self._peer_connections):
			await self._cleanup_connection(peer_connection)

	async def _cleanup_connection(self, peer_connection: RTCPeerConnection) -> None:
		"""Close a single peer connection and release its resources."""
		track = self._peer_connections.pop(peer_connection, None)
		if track is not None:
			track.stop()
		await peer_connection.close()
		await asyncio.sleep(0.05)
