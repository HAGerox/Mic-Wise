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