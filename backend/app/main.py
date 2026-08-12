"""FastAPI application entry point for the Mic-Wise backend MVP."""

from __future__ import annotations

import multiprocessing as mp
import sys
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
from app.network.rchat import RChatBroadcaster
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
	rchat_broadcaster = RChatBroadcaster()
	rchat_broadcaster.update_settings(
		enabled=bool(show_settings.rchat_enabled),
		flash_enabled=bool(show_settings.rchat_flash_enabled),
		hold_seconds=int(show_settings.rchat_hold_seconds),
		interface_ip=show_settings.rchat_interface_ip,
		username=show_settings.rchat_username,
	)
	app.state.rchat_broadcaster = rchat_broadcaster

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
		await rchat_broadcaster.close()
		await stop_audio_runtime(getattr(app.state, "audio_runtime", None))
		if discovery_service is not None:
			discovery_service.stop()
		await database.dispose()


def _frontend_directory() -> Path | None:
	"""Locate the built frontend for both source checkouts and frozen builds."""
	candidates: list[Path] = []
	if getattr(sys, "frozen", False):
		bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
		candidates.append(bundle_root / "frontend" / "dist")
		candidates.append(Path(sys.executable).parent / "frontend" / "dist")

	frontend_root = Path(__file__).resolve().parents[2] / "frontend"
	candidates.append(frontend_root / "dist")
	candidates.append(frontend_root)

	for candidate in candidates:
		if (candidate / "index.html").exists():
			return candidate
	return None


def create_app() -> FastAPI:
	"""Create and configure the FastAPI application."""
	app = FastAPI(title="Mic-Wise Backend", lifespan=lifespan)
	app.include_router(api_router, prefix="/api")
	app.include_router(websocket_router)
	frontend_directory = _frontend_directory()
	if frontend_directory is not None:
		app.mount(
			"/",
			StaticFiles(directory=str(frontend_directory), html=True),
			name="frontend",
		)
	return app


app = create_app()
