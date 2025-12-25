# Shared Memory Ring Buffer
# Implements the mmap-backed circular buffer for audio data.

import mmap
import os
import struct
import numpy as np
from typing import Tuple

HEADER_FORMAT = "<4sIIIIQ" 
HEADER_SIZE = 4096

class AudioBuffer:
    def __init__(self, filename: str, channels: int, sample_rate: int, duration_sec: int, create: bool = False):
        self.filename = filename
        self.header_size = HEADER_SIZE

        if create:
            self.channels = channels
            self.sample_rate = sample_rate
            self.capacity = sample_rate * duration_sec
            data_size = self.capacity * self.channels * 2
            total_size = self.header_size + data_size

            with open(self.filename, "wb") as f:
                f.write(b'\x00' * total_size)

            self.mode = os.O_RDWR
        else:
            self.mode = os.O_RDONLY

        self.fd = os.open(self.filename, self.mode)
        self.mm = mmap.mmap(self.fd, 0, access=mmap.ACCESS_WRITE if create else mmap.ACCESS_READ)

        if create:
            self.write_head = 0
            self._save_header()
        else:
            self._load_header()

        self.data = np.frombuffer(self.mm, dtype=np.int16, offset=self.header_size)
        self.data = self.data.reshape((self.capacity, self.channels))

    def _save_header(self):
        """Packs and writes the metadata to the start of the mmap."""
        header_data = struct.pack(
            HEADER_FORMAT,
            b"MICW",
            1,
            self.channels,
            self.sample_rate,
            self.capacity,
            self.write_head
        )
        self.mm[:struct.calcsize(HEADER_FORMAT)] = header_data

    def _load_header(self):
        """Reads and unpacks metadata from the mmap."""
        header_data = self.mm[:struct.calcsize(HEADER_FORMAT)]
        magic, version, self.channels, self.sample_rate, self.capacity, self.write_head = struct.unpack(HEADER_FORMAT, header_data)
        if magic != b"MICW":
            raise ValueError("Not a valid Mic-Wise buffer file")
        
    def write(self, chunk: np.ndarray):
        """Writes a chunk of audio [frames, channels] to the buffer."""
        frames = chunk.shape[0]

        start_idx = self.write_head % self.capacity

        if start_idx + frames <= self.capacity:
            self.data[start_idx : start_idx + frames] = chunk
        else:
            first_part_size = self.capacity - start_idx
            self.data[start_idx:] = chunk[:first_part_size]
            self.data[:frames - first_part_size] = chunk[first_part_size:]

        self.write_head += frames
        self._save_header()

    def read(self, start_frame: int, count: int) -> np.ndarray:
        """Reads 'count' frames starting from 'start_frame'."""
        self._load_header()

        if start_frame + count > self.write_head:
            count = max(0, self.write_head - start_frame)

        if count <=0:
            return np.zeros((0, self.channels), dtype=np.int16)
        
        start_idx = start_frame % self.capacity

        if start_idx + count <= self.capacity:
            return self.data[start_idx : start_idx + count].copy()
        else:
            first_part_size = self.capacity - start_idx
            return np.concatenate([self.data[start_idx:], self.data[:count - first_part_size]])
        
    def get_latest(self, count) -> np.ndarray:
        """Helper to get the most recent 'count' frames."""
        self._load_header()
        return self.read(self.write_head - count, count)

