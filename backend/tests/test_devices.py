"""Tests for cross-platform audio device discovery helpers."""

from __future__ import annotations

from app.audio.devices import (
    AUTO_INPUT_DEVICE_SELECTOR,
    build_input_device_selector,
    list_audio_input_devices,
    resolve_input_device,
)


class DummySoundDeviceModule:
    def __init__(self) -> None:
        self.default = type("DummyDefault", (), {"device": (1, -1)})()
        self._devices = [
            {
                "name": "Built-in Output",
                "hostapi": 0,
                "max_input_channels": 0,
                "default_samplerate": 48_000,
            },
            {
                "name": "Built-in Microphone",
                "hostapi": 0,
                "max_input_channels": 2,
                "default_samplerate": 48_000,
            },
            {
                "name": "USB Rack",
                "hostapi": 1,
                "max_input_channels": 8,
                "default_samplerate": 48_000,
            },
        ]
        self._hostapis = [
            {"name": "Core Audio"},
            {"name": "ASIO"},
        ]

    def query_devices(self):
        return self._devices

    def query_hostapis(self):
        return self._hostapis



def test_list_audio_input_devices_returns_hostapi_enriched_options(monkeypatch) -> None:
    dummy_sd = DummySoundDeviceModule()
    monkeypatch.setattr("app.audio.devices.sd", dummy_sd)

    devices = list_audio_input_devices()

    assert [device.name for device in devices] == ["Built-in Microphone", "USB Rack"]
    assert devices[0].is_default is True
    assert devices[0].display_name == "Core Audio · Built-in Microphone (default)"



def test_resolve_input_device_uses_hostapi_and_name(monkeypatch) -> None:
    dummy_sd = DummySoundDeviceModule()
    monkeypatch.setattr("app.audio.devices.sd", dummy_sd)

    selector = build_input_device_selector("ASIO", "USB Rack")

    assert resolve_input_device(selector, required_channels=4) == 2
    assert resolve_input_device(AUTO_INPUT_DEVICE_SELECTOR, required_channels=1) is None
