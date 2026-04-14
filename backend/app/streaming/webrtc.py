"""WebRTC audio streaming sourced from the shared audio buffer."""

from __future__ import annotations

import asyncio
import fractions
import time

import numpy as np
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import AUDIO_PTIME, AudioStreamTrack, MediaStreamError
from av import AudioFrame

from app.audio.buffer import AudioBuffer


class BufferAudioStreamTrack(AudioStreamTrack):
	"""A WebRTC audio track reading and mixing frames from ``AudioBuffer``."""

	def __init__(
		self,
		*,
		buffer_path: str,
		total_channels: int,
		sample_rate: int,
		channel_numbers: list[int],
		replay_seconds: float = 0.0,
	) -> None:
		super().__init__()
		self.buffer = AudioBuffer(buffer_path)
		self.total_channels = total_channels
		self.sample_rate = sample_rate
		self.samples_per_frame = max(1, int(round(AUDIO_PTIME * sample_rate)))
		self.selected_indices = [
			channel_number - 1
			for channel_number in sorted(set(channel_numbers))
			if 1 <= channel_number <= total_channels
		]

		latest = self.buffer.refresh_write_head()
		replay_frames = max(0, int(round(replay_seconds * sample_rate)))
		if replay_frames > 0:
			self._read_head = max(0, latest - replay_frames)
		else:
			self._read_head = max(0, latest - (self.samples_per_frame * 4))

	async def recv(self) -> AudioFrame:
		"""Produce the next audio frame for transmission."""
		if self.readyState != "live":
			raise MediaStreamError

		if hasattr(self, "_timestamp"):
			self._timestamp += self.samples_per_frame
			wait = self._start + (self._timestamp / self.sample_rate) - time.time()
			await asyncio.sleep(max(0.0, wait))
		else:
			self._start = time.time()
			self._timestamp = 0

		latest = self.buffer.refresh_write_head()
		earliest = max(0, latest - self.buffer.capacity)
		if self._read_head < earliest:
			self._read_head = earliest

		chunk = self.buffer.read(self._read_head, self.samples_per_frame)
		self._read_head += self.samples_per_frame
		if chunk.shape[0] < self.samples_per_frame:
			padding = np.zeros(
				(self.samples_per_frame - chunk.shape[0], self.total_channels),
				dtype=np.int16,
			)
			chunk = np.concatenate((chunk, padding), axis=0)

		mono = self._mix_selected_channels(chunk)
		frame = AudioFrame(format="s16", layout="mono", samples=self.samples_per_frame)
		frame.planes[0].update(mono.tobytes())
		frame.pts = self._timestamp
		frame.sample_rate = self.sample_rate
		frame.time_base = fractions.Fraction(1, self.sample_rate)
		return frame

	def _mix_selected_channels(self, chunk: np.ndarray) -> np.ndarray:
		"""Mix the selected input channels down to a mono program stream."""
		if not self.selected_indices:
			return np.zeros(self.samples_per_frame, dtype=np.int16)

		selected = chunk[:, self.selected_indices].astype(np.float32)
		if selected.ndim == 1 or selected.shape[1] == 1:
			mono = selected.reshape(-1)
		else:
			mono = np.mean(selected, axis=1)

		return np.clip(np.round(mono), -32_768, 32_767).astype(np.int16)

	def stop(self) -> None:
		"""Release the shared buffer when the track ends."""
		self.buffer.close()
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
		channel_numbers: list[int],
		replay_seconds: float = 0.0,
	) -> RTCSessionDescription:
		"""Create an SDP answer for a new listener connection."""
		peer_connection = RTCPeerConnection()
		track = BufferAudioStreamTrack(
			buffer_path=self.buffer_path,
			total_channels=self.total_channels,
			sample_rate=self.sample_rate,
			channel_numbers=channel_numbers,
			replay_seconds=replay_seconds,
		)
		self._peer_connections[peer_connection] = track

		@peer_connection.on("connectionstatechange")
		async def on_connectionstatechange() -> None:
			if peer_connection.connectionState in {"failed", "closed", "disconnected"}:
				await self._cleanup_connection(peer_connection)

		await peer_connection.setRemoteDescription(
			RTCSessionDescription(sdp=sdp, type=type_),
		)
		peer_connection.addTrack(track)
		answer = await peer_connection.createAnswer()
		await peer_connection.setLocalDescription(answer)
		await self._await_ice_completion(peer_connection)
		assert peer_connection.localDescription is not None
		return peer_connection.localDescription

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

	@staticmethod
	async def _await_ice_completion(peer_connection: RTCPeerConnection) -> None:
		"""Wait until aiortc has finished gathering local ICE candidates."""
		while peer_connection.iceGatheringState != "complete":
			await asyncio.sleep(0.05)
