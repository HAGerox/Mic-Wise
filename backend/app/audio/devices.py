"""Cross-platform audio device discovery helpers built on sounddevice."""

from __future__ import annotations

import os
from dataclasses import dataclass

os.environ.setdefault("SD_ENABLE_ASIO", "1")

import sounddevice as sd

AUTO_INPUT_DEVICE_SELECTOR = "auto"


@dataclass(slots=True)
class AudioInputDeviceInfo:
    """Serializable description of an available capture device."""

    selector: str
    name: str
    hostapi_name: str
    max_input_channels: int
    default_sample_rate: int
    is_default: bool

    @property
    def display_name(self) -> str:
        """Return a concise label suitable for the frontend."""
        default_suffix = " (default)" if self.is_default else ""
        return f"{self.hostapi_name} · {self.name}{default_suffix}"

    def to_dict(self) -> dict[str, object]:
        """Convert the device info into an API-friendly mapping."""
        return {
            "selector": self.selector,
            "name": self.name,
            "hostapi_name": self.hostapi_name,
            "display_name": self.display_name,
            "max_input_channels": self.max_input_channels,
            "default_sample_rate": self.default_sample_rate,
            "is_default": self.is_default,
        }


def build_input_device_selector(hostapi_name: str, device_name: str) -> str:
    """Create a portable selector string from host API and device names."""
    safe_hostapi = str(hostapi_name).strip()
    safe_device = str(device_name).strip()
    if not safe_hostapi or not safe_device:
        raise ValueError("hostapi_name and device_name are required")
    return f"{safe_hostapi}::{safe_device}"


def split_input_device_selector(selector: str | None) -> tuple[str, str] | None:
    """Parse a stored selector string back into host API and device names."""
    if selector is None:
        return None

    raw_selector = str(selector).strip()
    if not raw_selector or raw_selector.lower() == AUTO_INPUT_DEVICE_SELECTOR:
        return None

    hostapi_name, separator, device_name = raw_selector.partition("::")
    if not separator or not hostapi_name.strip() or not device_name.strip():
        return None
    return hostapi_name.strip(), device_name.strip()


def _default_input_device_index() -> int | None:
    default_device = getattr(sd.default, "device", None)
    if default_device is None:
        return None
    if isinstance(default_device, (list, tuple)) and default_device:
        try:
            return int(default_device[0])
        except (TypeError, ValueError):
            return None
    try:
        return int(default_device)
    except (TypeError, ValueError):
        return None


def list_audio_input_devices() -> list[AudioInputDeviceInfo]:
    """Return the available capture devices across all host APIs."""
    try:
        devices = sd.query_devices()
        hostapis = sd.query_hostapis()
    except Exception:
        return []

    default_input_index = _default_input_device_index()
    available_devices: list[AudioInputDeviceInfo] = []
    for device_index, device in enumerate(devices):
        max_input_channels = int(device.get("max_input_channels", 0) or 0)
        if max_input_channels <= 0:
            continue

        raw_hostapi_index = device.get("hostapi", -1)
        hostapi_index = int(raw_hostapi_index if raw_hostapi_index is not None else -1)
        hostapi_name = "Unknown"
        if 0 <= hostapi_index < len(hostapis):
            hostapi_name = str(hostapis[hostapi_index].get("name") or "Unknown")

        device_name = str(device.get("name") or f"Input {device_index}")
        available_devices.append(
            AudioInputDeviceInfo(
                selector=build_input_device_selector(hostapi_name, device_name),
                name=device_name,
                hostapi_name=hostapi_name,
                max_input_channels=max_input_channels,
                default_sample_rate=int(round(float(device.get("default_samplerate", 48_000) or 48_000))),
                is_default=device_index == default_input_index,
            ),
        )

    available_devices.sort(
        key=lambda device: (
            not device.is_default,
            device.hostapi_name.lower(),
            device.name.lower(),
        ),
    )
    return available_devices


def resolve_input_device(
    selector: str | int | None,
    *,
    required_channels: int = 1,
) -> int | None:
    """Resolve a stored selector back to a sounddevice device index."""
    if selector is None:
        return None
    if isinstance(selector, int):
        return selector

    raw_selector = str(selector).strip()
    if not raw_selector or raw_selector.lower() == AUTO_INPUT_DEVICE_SELECTOR:
        return None
    if raw_selector.isdigit():
        return int(raw_selector)

    parsed = split_input_device_selector(raw_selector)
    if parsed is None:
        raise ValueError(f"Unrecognised audio input selector: {selector}")

    hostapi_name, device_name = parsed
    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    safe_required_channels = max(1, int(required_channels))
    for device_index, device in enumerate(devices):
        max_input_channels = int(device.get("max_input_channels", 0) or 0)
        if max_input_channels < safe_required_channels:
            continue

        raw_hostapi_index = device.get("hostapi", -1)
        device_hostapi_index = int(raw_hostapi_index if raw_hostapi_index is not None else -1)
        resolved_hostapi_name = "Unknown"
        if 0 <= device_hostapi_index < len(hostapis):
            resolved_hostapi_name = str(hostapis[device_hostapi_index].get("name") or "Unknown")

        resolved_device_name = str(device.get("name") or "")
        if resolved_hostapi_name == hostapi_name and resolved_device_name == device_name:
            return device_index

    raise ValueError(
        f"Audio input device '{device_name}' on host API '{hostapi_name}' is unavailable",
    )
