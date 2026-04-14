"""Tests for the mmap-backed audio buffer."""

from __future__ import annotations

import numpy as np
import pytest

from app.audio.buffer import AudioBuffer


def test_create_write_and_reopen_buffer(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"
    frames = np.array(
        [
            [1, 10],
            [2, 20],
            [3, 30],
        ],
        dtype=np.int16,
    )

    with AudioBuffer(
        filename=str(buffer_path),
        channels=2,
        sample_rate=4,
        duration_sec=5,
        create=True,
    ) as writer:
        writer.write(frames)
        assert writer.header_snapshot()["write_head"] == 3

    with AudioBuffer(filename=str(buffer_path)) as reader:
        assert reader.channels == 2
        assert reader.sample_rate == 4
        np.testing.assert_array_equal(reader.read(0, 3), frames)


def test_wraparound_read_latest_returns_retained_window(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"

    first_chunk = np.array(
        [
            [1, 10],
            [2, 20],
            [3, 30],
            [4, 40],
            [5, 50],
            [6, 60],
        ],
        dtype=np.int16,
    )
    second_chunk = np.array(
        [
            [7, 70],
            [8, 80],
            [9, 90],
            [10, 100],
        ],
        dtype=np.int16,
    )
    expected = np.array(
        [
            [3, 30],
            [4, 40],
            [5, 50],
            [6, 60],
            [7, 70],
            [8, 80],
            [9, 90],
            [10, 100],
        ],
        dtype=np.int16,
    )

    with AudioBuffer(
        filename=str(buffer_path),
        channels=2,
        sample_rate=4,
        duration_sec=2,
        create=True,
    ) as writer:
        writer.write(first_chunk)
        writer.write(second_chunk)
        np.testing.assert_array_equal(writer.read_latest(8), expected)


def test_read_clamps_to_available_frame_range(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"
    frames = np.array(
        [
            [11, 21],
            [12, 22],
            [13, 23],
            [14, 24],
        ],
        dtype=np.int16,
    )

    with AudioBuffer(
        filename=str(buffer_path),
        channels=2,
        sample_rate=4,
        duration_sec=4,
        create=True,
    ) as writer:
        writer.write(frames)
        np.testing.assert_array_equal(writer.read(-10, 40), frames)
        empty = writer.read(100, 10)
        assert empty.shape == (0, 2)


def test_write_larger_than_capacity_keeps_latest_audio(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"
    oversized = np.array(
        [
            [1],
            [2],
            [3],
            [4],
            [5],
            [6],
            [7],
        ],
        dtype=np.int16,
    )

    with AudioBuffer(
        filename=str(buffer_path),
        channels=1,
        sample_rate=1,
        duration_sec=5,
        create=True,
    ) as writer:
        writer.write(oversized)
        expected = np.array([[3], [4], [5], [6], [7]], dtype=np.int16)
        np.testing.assert_array_equal(writer.read_latest(5), expected)


def test_write_validates_dtype_and_shape(tmp_path) -> None:
    buffer_path = tmp_path / "audio.buffer"

    with AudioBuffer(
        filename=str(buffer_path),
        channels=2,
        sample_rate=4,
        duration_sec=2,
        create=True,
    ) as writer:
        with pytest.raises(TypeError):
            writer.write(np.zeros((4, 2), dtype=np.float32))
        with pytest.raises(ValueError):
            writer.write(np.zeros((4,), dtype=np.int16))
        with pytest.raises(ValueError):
            writer.write(np.zeros((4, 1), dtype=np.int16))
