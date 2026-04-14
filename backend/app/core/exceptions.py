"""Custom exception hierarchy for Mic-Wise."""

from __future__ import annotations


class MicWiseError(Exception):
    """Base exception for Mic-Wise backend errors."""


class BufferConfigurationError(MicWiseError):
    """Raised when the audio buffer cannot be configured safely."""


class ShowConfigurationError(MicWiseError):
    """Raised when the show file or its settings are invalid."""
