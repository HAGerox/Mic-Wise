"""Helpers for starting and restarting audio-related runtime services."""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass

from fastapi import FastAPI

from app.api.websocket import WebSocketManager
from app.audio.alerts import AlertAnalysisService
from app.audio.analysis import MeterAnalysisService
from app.audio.buffer import AudioBuffer
from app.audio.engine import AudioEngineConfig, AudioEngineProcess
from app.audio.playback import playback_sync_delay_frames
from app.core.settings import MicWiseSettings
from app.streaming.webrtc import WebRTCStreamManager


@dataclass(slots=True)
class AudioRuntimeHandle:
    """In-process references to the running audio services."""

    audio_process: AudioEngineProcess
    audio_stop_event: mp.Event
    webrtc_manager: WebRTCStreamManager
    meter_analysis: MeterAnalysisService
    alert_analysis: AlertAnalysisService


async def start_audio_runtime(
    *,
    settings: MicWiseSettings,
    show_settings: object,
    websocket_manager: WebSocketManager,
    alert_notifier: object | None = None,
) -> AudioRuntimeHandle:
    """Create the shared buffer, audio process, and analysis services."""
    with AudioBuffer(
        filename=str(settings.buffer_path),
        channels=int(getattr(show_settings, "channel_count")),
        sample_rate=int(getattr(show_settings, "sample_rate")),
        duration_sec=int(getattr(show_settings, "buffer_duration_sec")),
        create=True,
    ):
        pass

    stop_event = mp.Event()
    audio_process = AudioEngineProcess(
        AudioEngineConfig(
            buffer_path=str(settings.buffer_path),
            channels=int(getattr(show_settings, "channel_count")),
            sample_rate=int(getattr(show_settings, "sample_rate")),
            buffer_duration_sec=int(getattr(show_settings, "buffer_duration_sec")),
            block_size=int(getattr(show_settings, "block_size")),
            source_mode=str(getattr(show_settings, "audio_source_mode", "synthetic")),
            input_device=getattr(show_settings, "audio_input_device", None),
        ),
        stop_event=stop_event,
    )
    audio_process.start()

    webrtc_manager = WebRTCStreamManager(
        buffer_path=str(settings.buffer_path),
        sample_rate=int(getattr(show_settings, "sample_rate")),
        total_channels=int(getattr(show_settings, "channel_count")),
    )
    meter_analysis = MeterAnalysisService(
        buffer_path=str(settings.buffer_path),
        sample_rate=int(getattr(show_settings, "sample_rate")),
        channels=int(getattr(show_settings, "channel_count")),
        window_ms=settings.meter_window_ms,
        poll_interval_ms=settings.meter_poll_interval_ms,
        playback_delay_frames=playback_sync_delay_frames(int(getattr(show_settings, "sample_rate"))),
        broadcaster=websocket_manager,
    )
    await meter_analysis.start()

    alert_analysis = AlertAnalysisService(
        buffer_path=str(settings.buffer_path),
        sample_rate=int(getattr(show_settings, "sample_rate")),
        channels=int(getattr(show_settings, "channel_count")),
        enabled=bool(getattr(show_settings, "alerts_enabled", True)),
        notifier=getattr(alert_notifier, "notify_alert", None),
    )
    await alert_analysis.start()

    return AudioRuntimeHandle(
        audio_process=audio_process,
        audio_stop_event=stop_event,
        webrtc_manager=webrtc_manager,
        meter_analysis=meter_analysis,
        alert_analysis=alert_analysis,
    )


async def stop_audio_runtime(runtime: AudioRuntimeHandle | None) -> None:
    """Stop the running audio services and worker process."""
    if runtime is None:
        return

    await runtime.webrtc_manager.close_all()
    await runtime.meter_analysis.stop()
    await runtime.alert_analysis.stop()
    runtime.audio_stop_event.set()
    runtime.audio_process.join(timeout=2.0)
    if runtime.audio_process.is_alive():
        runtime.audio_process.terminate()
        runtime.audio_process.join(timeout=1.0)


async def restart_audio_runtime(app: FastAPI, show_settings: object) -> None:
    """Recreate the audio process and attached runtime services for the app."""
    current_runtime = getattr(app.state, "audio_runtime", None)
    if current_runtime is not None:
        await stop_audio_runtime(current_runtime)

    runtime = await start_audio_runtime(
        settings=app.state.settings,
        show_settings=show_settings,
        websocket_manager=app.state.websocket_manager,
        alert_notifier=getattr(app.state, "radioworld_broadcaster", None),
    )
    app.state.audio_runtime = runtime
    app.state.audio_process = runtime.audio_process
    app.state.audio_stop_event = runtime.audio_stop_event
    app.state.webrtc_manager = runtime.webrtc_manager
    app.state.meter_analysis = runtime.meter_analysis
    app.state.alert_analysis = runtime.alert_analysis
