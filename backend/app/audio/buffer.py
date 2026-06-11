"""Memory-mapped circular audio buffer for shared-process PCM audio.

The buffer file is split into two sections:

1. A fixed-size header stored at the start of the mmap. The header contains
   metadata required for every process to interpret the file consistently.
2. A contiguous interleaved PCM data section stored immediately after the
   header. This section is exposed as a NumPy array with shape
   ``(capacity_frames, channels)`` and dtype ``int16``.

The ``write_head`` stored in the header is a monotonic frame counter. Readers
use it to determine both the latest available frame and the earliest frame that
is still retained in the rolling window.
"""

from __future__ import annotations

import errno
import mmap
import os
import struct
from pathlib import Path
from typing import Final

import numpy as np
import numpy.typing as npt

MAGIC: Final[bytes] = b"MICW"
HEADER_VERSION: Final[int] = 1
HEADER_SIZE: Final[int] = 4096
SAMPLE_DTYPE: Final[np.dtype[np.int16]] = np.dtype(np.int16)
BYTES_PER_SAMPLE: Final[int] = SAMPLE_DTYPE.itemsize

# Header layout:
#   4s  magic
#   I   version
#   I   header_size
#   I   channels
#   I   sample_rate
#   Q   capacity_frames
#   Q   write_head_frames
HEADER_STRUCT: Final[struct.Struct] = struct.Struct("<4sIIIIQQ")
WRITE_HEAD_OFFSET: Final[int] = struct.calcsize("<4sIIIIQ")

AudioChunk = npt.NDArray[np.int16]


class AudioBuffer:
    """Shared memory ring buffer storing interleaved ``int16`` PCM frames.

    Args:
        filename: Path to the backing mmap file.
        channels: Number of audio channels. Required when ``create=True``.
        sample_rate: Audio sample rate in Hz. Required when ``create=True``.
        duration_sec: Rolling buffer duration in seconds. Required when
            ``create=True``.
        create: Whether to create and initialize a new buffer file.

    Raises:
        FileNotFoundError: If ``create`` is ``False`` and the file does not
            exist.
        ValueError: If the file header is invalid or creation arguments are not
            usable.
    """

    def __init__(
        self,
        filename: str,
        channels: int = 0,
        sample_rate: int = 0,
        duration_sec: int = 0,
        create: bool = False,
        writable: bool = False,
    ) -> None:
        self.path = Path(filename)
        self.header_size = HEADER_SIZE
        self._writable = create or writable
        self._closed = False

        self.channels: int
        self.sample_rate: int
        self.capacity: int
        self.write_head: int = 0

        if create:
            self._validate_creation_arguments(
                channels=channels,
                sample_rate=sample_rate,
                duration_sec=duration_sec,
            )
            self.channels = channels
            self.sample_rate = sample_rate
            self.capacity = sample_rate * duration_sec
            data_size = self.capacity * self.channels * BYTES_PER_SAMPLE
            total_size = self.header_size + data_size

            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("wb") as file_handle:
                file_handle.truncate(total_size)

            access = mmap.ACCESS_WRITE
            open_mode = os.O_RDWR
        else:
            access = mmap.ACCESS_WRITE if writable else mmap.ACCESS_READ
            open_mode = os.O_RDWR if writable else os.O_RDONLY

        # Windows fds default to text mode; PCM data must stay binary.
        open_mode |= getattr(os, "O_BINARY", 0)

        self.fd = os.open(os.fspath(self.path), open_mode)
        self.mm = mmap.mmap(self.fd, 0, access=access)

        if create:
            self._write_full_header()
        else:
            self._load_header()

        self.data: AudioChunk = np.frombuffer(
            self.mm,
            dtype=SAMPLE_DTYPE,
            offset=self.header_size,
        ).reshape((self.capacity, self.channels))

    @staticmethod
    def _validate_creation_arguments(
        *,
        channels: int,
        sample_rate: int,
        duration_sec: int,
    ) -> None:
        """Validate parameters needed when creating a new buffer."""
        if channels <= 0:
            raise ValueError("channels must be a positive integer")
        if sample_rate <= 0:
            raise ValueError("sample_rate must be a positive integer")
        if duration_sec <= 0:
            raise ValueError("duration_sec must be a positive integer")

    def _write_full_header(self) -> None:
        """Write the static header fields plus the current write head."""
        HEADER_STRUCT.pack_into(
            self.mm,
            0,
            MAGIC,
            HEADER_VERSION,
            self.header_size,
            self.channels,
            self.sample_rate,
            self.capacity,
            self.write_head,
        )

    def _write_head_only(self) -> None:
        """Update the monotonic write head in-place.

        Updating only the write head avoids rewriting the full header on every
        audio callback while still making new data visible to readers.
        """
        struct.pack_into("<Q", self.mm, WRITE_HEAD_OFFSET, self.write_head)

    def _load_header(self) -> None:
        """Read and validate the header from an existing buffer file."""
        (
            magic,
            version,
            header_size,
            self.channels,
            self.sample_rate,
            self.capacity,
            self.write_head,
        ) = HEADER_STRUCT.unpack_from(self.mm, 0)

        if magic != MAGIC:
            raise ValueError("Not a valid Mic-Wise audio buffer file")
        if version != HEADER_VERSION:
            raise ValueError(
                f"Unsupported buffer version {version}; expected {HEADER_VERSION}",
            )
        if header_size != self.header_size:
            raise ValueError(
                f"Unexpected header size {header_size}; expected {self.header_size}",
            )

    def refresh_write_head(self) -> int:
        """Refresh and return the latest write head from the shared header."""
        (self.write_head,) = struct.unpack_from("<Q", self.mm, WRITE_HEAD_OFFSET)
        return self.write_head

    @property
    def frames_available(self) -> int:
        """Return the number of readable frames currently retained."""
        return min(self.refresh_write_head(), self.capacity)

    def available_frame_range(self) -> tuple[int, int]:
        """Return the absolute readable frame range as ``(start, end)``.

        The ``end`` value is exclusive and equal to the current write head.
        """
        latest = self.refresh_write_head()
        earliest = max(0, latest - self.capacity)
        return earliest, latest

    def seconds_to_frames(self, seconds: float) -> int:
        """Convert seconds to frames using the configured sample rate."""
        if seconds < 0:
            raise ValueError("seconds must be non-negative")
        return int(round(seconds * self.sample_rate))

    def frames_to_seconds(self, frames: int) -> float:
        """Convert a frame count to seconds."""
        if frames < 0:
            raise ValueError("frames must be non-negative")
        return frames / float(self.sample_rate)

    def write(self, chunk: AudioChunk) -> int:
        """Write an audio chunk into the rolling buffer.

        Args:
            chunk: Interleaved PCM frames with shape ``(frames, channels)`` and
                dtype ``int16``.

        Returns:
            The updated absolute write head after the write completes.

        Raises:
            RuntimeError: If the buffer was opened read-only.
            TypeError: If ``chunk`` is not ``int16``.
            ValueError: If ``chunk`` has the wrong shape.
        """
        if not self._writable:
            raise RuntimeError("Cannot write to a read-only AudioBuffer")
        if chunk.dtype != SAMPLE_DTYPE:
            raise TypeError("chunk must have dtype int16")
        if chunk.ndim != 2:
            raise ValueError("chunk must have shape (frames, channels)")
        if chunk.shape[1] != self.channels:
            raise ValueError(
                f"chunk has {chunk.shape[1]} channels; expected {self.channels}",
            )

        frames = int(chunk.shape[0])
        if frames == 0:
            return self.write_head

        if frames > self.capacity:
            chunk = chunk[-self.capacity :]
            frames = self.capacity

        start_idx = self.write_head % self.capacity
        end_idx = start_idx + frames

        if end_idx <= self.capacity:
            self.data[start_idx:end_idx] = chunk
        else:
            first_part_size = self.capacity - start_idx
            self.data[start_idx:] = chunk[:first_part_size]
            self.data[: frames - first_part_size] = chunk[first_part_size:]

        self.write_head += frames
        self._write_head_only()
        return self.write_head

    def read(self, start_frame: int, count: int) -> AudioChunk:
        """Read a frame range from the rolling buffer.

        Args:
            start_frame: Absolute frame index to start from.
            count: Number of frames requested.

        Returns:
            A copied NumPy array containing the readable portion of the request.
            If the request falls fully outside the retained window, an empty
            array with shape ``(0, channels)`` is returned.
        """
        if count < 0:
            raise ValueError("count must be non-negative")
        if count == 0:
            return np.zeros((0, self.channels), dtype=SAMPLE_DTYPE)

        latest = self.refresh_write_head()
        earliest = max(0, latest - self.capacity)

        clamped_start = max(start_frame, earliest)
        clamped_end = min(start_frame + count, latest)
        if clamped_end <= clamped_start:
            return np.zeros((0, self.channels), dtype=SAMPLE_DTYPE)

        readable_count = clamped_end - clamped_start
        start_idx = clamped_start % self.capacity
        end_idx = start_idx + readable_count

        if end_idx <= self.capacity:
            return self.data[start_idx:end_idx].copy()

        first_part_size = self.capacity - start_idx
        return np.concatenate(
            (
                self.data[start_idx:],
                self.data[: readable_count - first_part_size],
            ),
            axis=0,
        )

    def read_latest(self, count: int) -> AudioChunk:
        """Read the most recently written frames from the buffer."""
        latest = self.refresh_write_head()
        return self.read(latest - count, count)

    def read_channel(self, start_frame: int, count: int, channel_index: int) -> AudioChunk:
        """Read a single channel from a frame range in the rolling buffer."""
        if not 0 <= channel_index < self.channels:
            raise ValueError(
                f"channel_index must be in range 0..{self.channels - 1}",
            )
        if count < 0:
            raise ValueError("count must be non-negative")
        if count == 0:
            return np.zeros((0,), dtype=SAMPLE_DTYPE)

        latest = self.refresh_write_head()
        earliest = max(0, latest - self.capacity)

        clamped_start = max(start_frame, earliest)
        clamped_end = min(start_frame + count, latest)
        if clamped_end <= clamped_start:
            return np.zeros((0,), dtype=SAMPLE_DTYPE)

        readable_count = clamped_end - clamped_start
        start_idx = clamped_start % self.capacity
        end_idx = start_idx + readable_count

        if end_idx <= self.capacity:
            return self.data[start_idx:end_idx, channel_index].copy()

        first_part_size = self.capacity - start_idx
        return np.concatenate(
            (
                self.data[start_idx:, channel_index],
                self.data[: readable_count - first_part_size, channel_index],
            ),
            axis=0,
        )

    def read_latest_channel(self, count: int, channel_index: int) -> AudioChunk:
        """Read the most recent samples for a single channel."""
        latest = self.refresh_write_head()
        return self.read_channel(latest - count, count, channel_index)

    def header_snapshot(self) -> dict[str, int]:
        """Return a dictionary view of the current header values."""
        latest = self.refresh_write_head()
        return {
            "version": HEADER_VERSION,
            "header_size": self.header_size,
            "channels": self.channels,
            "sample_rate": self.sample_rate,
            "capacity": self.capacity,
            "write_head": latest,
        }

    def flush(self) -> None:
        """Flush pending memory changes to the backing file."""
        self.mm.flush()

    def close(self) -> None:
        """Release the NumPy view, unmap the file, and close the descriptor.

        Calling ``close`` multiple times is safe.
        """
        if self._closed:
            return

        if hasattr(self, "data"):
            del self.data

        mm_obj = getattr(self, "mm", None)
        if mm_obj is not None and not mm_obj.closed:
            mm_obj.close()
        self.mm = None

        fd = getattr(self, "fd", None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
            finally:
                self.fd = None

        self._closed = True

    def __enter__(self) -> "AudioBuffer":
        """Enter context manager scope."""
        return self

    def __exit__(self, exc_type: object, exc: object, exc_tb: object) -> None:
        """Ensure the underlying mmap resources are released."""
        self.close()

