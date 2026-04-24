"""Shared playback timing helpers for browser monitoring."""

from __future__ import annotations

from aiortc.mediastreams import AUDIO_PTIME

LIVE_EDGE_FRAME_MULTIPLIER = 2


def playback_sync_delay_frames(sample_rate: int) -> int:
    """Return the frame delay used to keep browser audio and metering aligned."""
    samples_per_frame = max(1, int(round(AUDIO_PTIME * sample_rate)))
    return samples_per_frame * LIVE_EDGE_FRAME_MULTIPLIER
