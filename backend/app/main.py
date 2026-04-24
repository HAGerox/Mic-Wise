"""FastAPI application entry point for the Mic-Wise backend MVP."""

from __future__ import annotations

import multiprocessing as mp
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.api.websocket import WebSocketManager, router as websocket_router
from app.audio.analysis import MeterAnalysisService
from app.audio.buffer import AudioBuffer
from app.audio.engine import AudioEngineConfig, AudioEngineProcess
from app.audio.playback import playback_sync_delay_frames
from app.core.settings import MicWiseSettings
from app.database.repository import initialise_show_file
from app.database.session import DatabaseManager
from app.network.discovery import ZeroconfService
from app.streaming.webrtc import WebRTCStreamManager
from app.sync.service import SceneSyncService


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Initialise shared state and background services for the backend."""
	settings = MicWiseSettings()
	settings.ensure_directories()

	database = DatabaseManager(settings.show_path)
	show_settings = await initialise_show_file(database, settings)

	with AudioBuffer(
		filename=str(settings.buffer_path),
		channels=show_settings.channel_count,
		sample_rate=show_settings.sample_rate,
		duration_sec=show_settings.buffer_duration_sec,
		create=True,
	):
		pass

	stop_event = mp.Event()
	audio_process = AudioEngineProcess(
		AudioEngineConfig(
			buffer_path=str(settings.buffer_path),
			channels=show_settings.channel_count,
			sample_rate=show_settings.sample_rate,
			buffer_duration_sec=show_settings.buffer_duration_sec,
			block_size=show_settings.block_size,
			source_mode=show_settings.audio_source_mode,
		),
		stop_event=stop_event,
	)
	audio_process.start()

	websocket_manager = WebSocketManager()
	webrtc_manager = WebRTCStreamManager(
		buffer_path=str(settings.buffer_path),
		sample_rate=show_settings.sample_rate,
		total_channels=show_settings.channel_count,
	)
	meter_analysis = MeterAnalysisService(
		buffer_path=str(settings.buffer_path),
		sample_rate=show_settings.sample_rate,
		channels=show_settings.channel_count,
		window_ms=settings.meter_window_ms,
		poll_interval_ms=settings.meter_poll_interval_ms,
		playback_delay_frames=playback_sync_delay_frames(show_settings.sample_rate),
		broadcaster=websocket_manager,
	)
	await meter_analysis.start()

	discovery_service = None
	if settings.zeroconf_enabled:
		discovery_service = ZeroconfService(
			service_name="Mic-Wise",
			port=settings.port,
		)
		discovery_service.start()

	app.state.settings = settings
	app.state.database = database
	app.state.audio_process = audio_process
	app.state.audio_stop_event = stop_event
	app.state.websocket_manager = websocket_manager
	app.state.webrtc_manager = webrtc_manager
	app.state.meter_analysis = meter_analysis
	app.state.discovery_service = discovery_service
	scene_sync_service = SceneSyncService(database)
	await scene_sync_service.start()
	app.state.scene_sync_service = scene_sync_service

	try:
		yield
	finally:
		await scene_sync_service.stop()
		await webrtc_manager.close_all()
		await meter_analysis.stop()
		if discovery_service is not None:
			discovery_service.stop()
		stop_event.set()
		audio_process.join(timeout=2.0)
		if audio_process.is_alive():
			audio_process.terminate()
			audio_process.join(timeout=1.0)
		await database.dispose()


def create_app() -> FastAPI:
	"""Create and configure the FastAPI application."""
	app = FastAPI(title="Mic-Wise Backend", lifespan=lifespan)
	app.include_router(api_router, prefix="/api")
	app.include_router(websocket_router)
	frontend_directory = Path(__file__).resolve().parents[2] / "frontend"
	if frontend_directory.exists():
		app.mount(
			"/",
			StaticFiles(directory=str(frontend_directory), html=True),
			name="frontend",
		)
	return app


app = create_app()
