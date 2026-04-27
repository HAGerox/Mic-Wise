"""FastAPI application entry point for the Mic-Wise backend MVP."""

from __future__ import annotations

import multiprocessing as mp
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router
from app.api.websocket import WebSocketManager, router as websocket_router
from app.audio.runtime import restart_audio_runtime, stop_audio_runtime
from app.core.settings import MicWiseSettings
from app.database.repository import initialise_show_file
from app.database.session import DatabaseManager
from app.network.discovery import ZeroconfService
from app.network.radioworld import RadioWorldBroadcaster
from app.sync.service import SceneSyncService


@asynccontextmanager
async def lifespan(app: FastAPI):
	"""Initialise shared state and background services for the backend."""
	settings = MicWiseSettings()
	settings.ensure_directories()

	database = DatabaseManager(settings.show_path)
	show_settings = await initialise_show_file(database, settings)

	websocket_manager = WebSocketManager()

	discovery_service = None
	if settings.zeroconf_enabled:
		discovery_service = ZeroconfService(
			service_name="Mic-Wise",
			port=settings.port,
		)
		discovery_service.start()

	app.state.settings = settings
	app.state.database = database
	app.state.websocket_manager = websocket_manager
	app.state.discovery_service = discovery_service
	radioworld_broadcaster = RadioWorldBroadcaster()
	radioworld_broadcaster.update_settings(
		enabled=bool(show_settings.radioworld_enabled),
		flash_enabled=bool(show_settings.radioworld_flash_enabled),
		hold_seconds=int(show_settings.radioworld_hold_seconds),
		interface_ip=show_settings.radioworld_interface_ip,
	)
	app.state.radioworld_broadcaster = radioworld_broadcaster

	async def bound_restart_audio_runtime(updated_show_settings: object) -> None:
		await restart_audio_runtime(app, updated_show_settings)

	app.state.restart_audio_runtime = bound_restart_audio_runtime
	await app.state.restart_audio_runtime(show_settings)
	scene_sync_service = SceneSyncService(database)
	await scene_sync_service.start()
	app.state.scene_sync_service = scene_sync_service

	try:
		yield
	finally:
		await scene_sync_service.stop()
		await radioworld_broadcaster.close()
		await stop_audio_runtime(getattr(app.state, "audio_runtime", None))
		if discovery_service is not None:
			discovery_service.stop()
		await database.dispose()


def create_app() -> FastAPI:
	"""Create and configure the FastAPI application."""
	app = FastAPI(title="Mic-Wise Backend", lifespan=lifespan)
	app.include_router(api_router, prefix="/api")
	app.include_router(websocket_router)
	frontend_root = Path(__file__).resolve().parents[2] / "frontend"
	frontend_directory = frontend_root / "dist"
	if not (frontend_directory / "index.html").exists():
		frontend_directory = frontend_root
	if frontend_directory.exists():
		app.mount(
			"/",
			StaticFiles(directory=str(frontend_directory), html=True),
			name="frontend",
		)
	return app


app = create_app()
