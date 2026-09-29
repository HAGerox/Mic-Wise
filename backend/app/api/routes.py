"""REST API routes for the Mic-Wise backend MVP."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.api.schemas import (
	AudioAlertResponse,
	AudioInputDeviceResponse,
	ChannelCreateRequest,
	ChannelResponse,
	ChannelUpdateRequest,
	ChannelWaveformResponse,
	HealthResponse,
	MeterSnapshotResponse,
	NetworkInterfaceResponse,
	PhotoAssetResponse,
	RChatTestResponse,
	SceneChecklistUpdateRequest,
	SceneCreateRequest,
	SceneSyncEventRequest,
	SceneSyncEventResponse,
	SceneSyncStatusResponse,
	SceneResponse,
	ShowfileImportResponse,
	ShowfilePayload,
	SceneUpdateRequest,
	SettingsResponse,
	SettingsUpdateRequest,
	WebRTCAnswerResponse,
	WebRTCOfferRequest,
)
from app.audio.analysis import build_channel_waveform_preview
from app.audio.devices import list_audio_input_devices, resolve_input_device
from app.database.repository import (
	ASSET_EXTENSIONS,
	SHOWFILE_MEMBER,
	create_channel,
	create_scene,
	delete_channel,
	delete_scene,
	export_show_archive,
	export_showfile,
	get_channel,
	get_channels_by_ids,
	get_scene,
	get_settings,
	import_show_archive,
	import_showfile,
	list_channels,
	list_scenes,
	set_scene_channel_checked,
	store_photo_asset,
	update_scene,
	update_channel,
	update_settings,
)
from app.network.interfaces import list_ipv4_network_interfaces

try:
	from importlib.metadata import version as _package_version

	BACKEND_VERSION = _package_version("mic-wise")
except Exception:
	BACKEND_VERSION = "0.0.0"

router = APIRouter()

RUNTIME_SETTING_FIELDS = {
	"sample_rate",
	"channel_count",
	"buffer_duration_sec",
	"block_size",
	"audio_source_mode",
	"audio_input_device",
}
SYNC_SETTING_FIELDS = {
	"external_sync_enabled",
	"external_sync_transport",
	"external_sync_osc_host",
	"external_sync_osc_port",
	"external_sync_midi_input_name",
}


def _resolve_input_index(channel: ChannelResponse | object) -> int | None:
	"""Resolve the currently patched input index for a display channel."""
	input_index = getattr(channel, "input_index", None)
	if input_index is None:
		return None
	return int(input_index)


@router.get("/health", response_model=HealthResponse)
async def healthcheck(request: Request) -> HealthResponse:
	"""Return a minimal health report for the backend."""
	audio_process = request.app.state.audio_process
	settings = request.app.state.settings
	return HealthResponse(
		app="micwise",
		status="ok",
		version=BACKEND_VERSION,
		show_name=settings.show_name,
		show_filename=settings.show_filename,
		audio_engine_running=audio_process.is_alive(),
	)


@router.get("/settings", response_model=SettingsResponse)
async def read_settings(request: Request) -> SettingsResponse:
	"""Return the active show settings."""
	database = request.app.state.database
	return await get_settings(database)


@router.patch("/settings", response_model=SettingsResponse)
async def patch_settings(
	payload: SettingsUpdateRequest,
	request: Request,
) -> SettingsResponse:
	"""Persist UI-level settings for the active show."""
	database = request.app.state.database
	current_settings = await get_settings(database)
	changes = payload.model_dump(exclude_unset=True)
	if "active_scene_id" in changes and changes["active_scene_id"] is not None:
		scene = await get_scene(database, int(changes["active_scene_id"]))
		if scene is None:
			raise HTTPException(status_code=404, detail="Scene not found")

	if "audio_source_mode" in changes and changes["audio_source_mode"] is not None:
		audio_source_mode = str(changes["audio_source_mode"]).strip().lower()
		if audio_source_mode == "hardware":
			audio_source_mode = "sounddevice"
		if audio_source_mode not in {"synthetic", "sounddevice"}:
			raise HTTPException(status_code=400, detail="Unsupported audio source mode")
		changes["audio_source_mode"] = audio_source_mode

	for field_name in ("sample_rate", "channel_count", "buffer_duration_sec", "block_size", "alert_popup_duration_sec", "rchat_hold_seconds"):
		if field_name in changes and changes[field_name] is not None and int(changes[field_name]) <= 0:
			raise HTTPException(status_code=400, detail=f"{field_name} must be positive")

	candidate_source_mode = str(changes.get("audio_source_mode", current_settings.audio_source_mode)).strip().lower()
	candidate_channel_count = int(changes.get("channel_count", current_settings.channel_count))
	candidate_input_device = changes.get("audio_input_device", current_settings.audio_input_device)
	if candidate_source_mode == "sounddevice" and candidate_input_device:
		try:
			resolve_input_device(candidate_input_device, required_channels=candidate_channel_count)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error

	if not changes:
		return current_settings
	updated_settings = await update_settings(database, changes)
	if set(changes) & RUNTIME_SETTING_FIELDS:
		await request.app.state.restart_audio_runtime(updated_settings)
	else:
		request.app.state.alert_analysis.apply_settings(enabled=bool(updated_settings.alerts_enabled))

	request.app.state.rchat_broadcaster.update_settings(
		enabled=bool(updated_settings.rchat_enabled),
		flash_enabled=bool(updated_settings.rchat_flash_enabled),
		hold_seconds=int(updated_settings.rchat_hold_seconds),
		interface_ip=updated_settings.rchat_interface_ip,
		username=updated_settings.rchat_username,
	)
	if set(changes) & SYNC_SETTING_FIELDS:
		await request.app.state.scene_sync_service.reload()
	return updated_settings


@router.get("/audio/devices", response_model=list[AudioInputDeviceResponse])
async def read_audio_input_devices() -> list[AudioInputDeviceResponse]:
	"""Return the currently available cross-platform audio capture devices."""
	return [AudioInputDeviceResponse(**device.to_dict()) for device in list_audio_input_devices()]


@router.get("/network/interfaces", response_model=list[NetworkInterfaceResponse])
async def read_network_interfaces() -> list[NetworkInterfaceResponse]:
	"""Return IPv4 interfaces that can source RChat UDP broadcasts."""
	return [NetworkInterfaceResponse(**interface.to_dict()) for interface in list_ipv4_network_interfaces()]


@router.get("/channels", response_model=list[ChannelResponse])
async def read_channels(request: Request) -> list[ChannelResponse]:
	"""Return the configured channel list."""
	database = request.app.state.database
	return await list_channels(database)


@router.post("/channels", response_model=ChannelResponse, status_code=status.HTTP_201_CREATED)
async def create_channel_record(
	payload: ChannelCreateRequest,
	request: Request,
) -> ChannelResponse:
	"""Append a new display channel to the show file."""
	database = request.app.state.database
	return await create_channel(database, payload.model_dump(exclude_unset=True))


@router.patch("/channels/{channel_id}", response_model=ChannelResponse)
async def patch_channel(
	channel_id: int,
	payload: ChannelUpdateRequest,
	request: Request,
) -> ChannelResponse:
	"""Update a channel's metadata and UI settings."""
	database = request.app.state.database
	channel = await update_channel(
		database,
		channel_id=channel_id,
		changes=payload.model_dump(exclude_unset=True),
	)
	if channel is None:
		raise HTTPException(status_code=404, detail="Channel not found")
	return channel


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_record(channel_id: int, request: Request) -> Response:
	"""Delete a display channel from the show file."""
	database = request.app.state.database
	deleted = await delete_channel(database, channel_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Channel not found")
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/channels/{channel_id}/waveform", response_model=ChannelWaveformResponse)
async def read_channel_waveform(
	channel_id: int,
	request: Request,
	seconds: float = Query(default=300.0, ge=1.0, le=300.0),
	points: int = Query(default=240, ge=32, le=1200),
) -> ChannelWaveformResponse:
	"""Return a preview waveform for a single display channel."""
	database = request.app.state.database
	settings = await get_settings(database)
	channel = await get_channel(database, channel_id)
	if channel is None:
		raise HTTPException(status_code=404, detail="Channel not found")

	input_index = _resolve_input_index(channel)
	if input_index is None:
		return ChannelWaveformResponse(
			channel_id=channel.id,
			input_index=None,
			seconds=min(seconds, float(settings.buffer_duration_sec)),
			points=[0.0 for _ in range(points)],
		)

	actual_seconds, values = build_channel_waveform_preview(
		buffer_path=str(request.app.state.settings.buffer_path),
		sample_rate=settings.sample_rate,
		input_index=input_index,
		gain_db=float(channel.gain_db + settings.master_gain_db),
		seconds=min(seconds, float(settings.buffer_duration_sec)),
		points=points,
	)
	return ChannelWaveformResponse(
		channel_id=channel.id,
		input_index=input_index,
		seconds=actual_seconds,
		points=values,
	)


@router.get("/scenes", response_model=list[SceneResponse])
async def read_scenes(request: Request) -> list[SceneResponse]:
	"""Return the configured scene list."""
	database = request.app.state.database
	return await list_scenes(database)


@router.post("/scenes", response_model=SceneResponse, status_code=status.HTTP_201_CREATED)
async def create_scene_record(
	payload: SceneCreateRequest,
	request: Request,
) -> SceneResponse:
	"""Append a new scene to the show file."""
	database = request.app.state.database
	return await create_scene(database, payload.model_dump(exclude_unset=True))


@router.patch("/scenes/{scene_id}", response_model=SceneResponse)
async def patch_scene(
	scene_id: int,
	payload: SceneUpdateRequest,
	request: Request,
) -> SceneResponse:
	"""Update scene metadata or per-channel staging states."""
	database = request.app.state.database
	scene = await update_scene(
		database,
		scene_id=scene_id,
		changes=payload.model_dump(exclude_unset=True),
	)
	if scene is None:
		raise HTTPException(status_code=404, detail="Scene not found")
	return scene


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scene_record(scene_id: int, request: Request) -> Response:
	"""Delete a scene from the show file."""
	database = request.app.state.database
	deleted = await delete_scene(database, scene_id)
	if not deleted:
		raise HTTPException(status_code=404, detail="Scene not found")
	return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/scenes/{scene_id}/checklist", response_model=SceneResponse)
async def patch_scene_checklist(
	scene_id: int,
	payload: SceneChecklistUpdateRequest,
	request: Request,
) -> SceneResponse:
	"""Persist a single scene mic-check tick without touching staging state."""
	database = request.app.state.database
	applied = await set_scene_channel_checked(
		database,
		scene_id=scene_id,
		channel_id=payload.channel_id,
		checked=payload.checked,
	)
	if not applied:
		raise HTTPException(status_code=404, detail="Scene or channel not found")
	scene = await get_scene(database, scene_id)
	if scene is None:
		raise HTTPException(status_code=404, detail="Scene not found")
	return scene


@router.get("/sync/status", response_model=SceneSyncStatusResponse)
async def read_scene_sync_status(request: Request) -> SceneSyncStatusResponse:
	"""Return runtime status for optional external scene sync listeners."""
	return SceneSyncStatusResponse(**request.app.state.scene_sync_service.status.to_dict())


@router.get("/alerts/active", response_model=list[AudioAlertResponse])
async def read_active_alerts(request: Request) -> list[AudioAlertResponse]:
	"""Return active alerts mapped onto the currently configured display channels."""
	database = request.app.state.database
	channels = await list_channels(database)
	channels_by_input_index: dict[int, list[ChannelResponse | object]] = {}
	for channel in channels:
		input_index = _resolve_input_index(channel)
		if input_index is None:
			continue
		channels_by_input_index.setdefault(input_index, []).append(channel)

	responses: list[AudioAlertResponse] = []
	for alert in request.app.state.alert_analysis.get_active_alerts():
		mapped_channels = sorted(
			channels_by_input_index.get(int(alert.input_index), []),
			key=lambda channel: int(getattr(channel, "number", 0)),
		)
		responses.append(
			AudioAlertResponse(
				**alert.to_dict(),
				channel_ids=[int(channel.id) for channel in mapped_channels],
				channel_numbers=[int(channel.number) for channel in mapped_channels],
				channel_names=[str(channel.name) for channel in mapped_channels],
			),
		)

	return responses


@router.post("/alerts/test", response_model=AudioAlertResponse)
async def test_alerts(request: Request) -> AudioAlertResponse:
	"""Inject a synthetic alert so the settings UI can test popups."""
	alert = request.app.state.alert_analysis.inject_test_alert()
	return AudioAlertResponse(
		**alert.to_dict(),
		channel_ids=[],
		channel_numbers=[alert.input_index + 1],
		channel_names=[],
	)


@router.post("/rchat/test", response_model=RChatTestResponse)
async def test_rchat(request: Request) -> RChatTestResponse:
	"""Send a synthetic RChat UDP message using current settings."""
	status = await request.app.state.rchat_broadcaster.send_test_message()
	return RChatTestResponse(status="ok" if status.error is None else "error", **status.to_dict())


@router.post("/sync/events", response_model=SceneSyncEventResponse)
async def apply_scene_sync_event_route(
	payload: SceneSyncEventRequest,
	request: Request,
) -> SceneSyncEventResponse:
	"""Apply a normalized external cue event to the active show."""
	result = await request.app.state.scene_sync_service.handle_event(payload.to_event())
	return SceneSyncEventResponse(**asdict(result))


@router.get("/meters/latest", response_model=MeterSnapshotResponse)
async def read_latest_meters(request: Request) -> MeterSnapshotResponse:
	"""Return the latest computed meter snapshot."""
	return request.app.state.meter_analysis.latest_snapshot.to_dict()


@router.post("/streaming/webrtc/offer", response_model=WebRTCAnswerResponse)
async def create_webrtc_offer(
	payload: WebRTCOfferRequest,
	request: Request,
) -> WebRTCAnswerResponse:
	"""Create a WebRTC answer for a browser listener session."""
	database = request.app.state.database
	manager = request.app.state.webrtc_manager
	settings = await get_settings(database)
	channel_records = await get_channels_by_ids(database, payload.channel_ids)
	channel_by_id = {channel.id: channel for channel in channel_records}
	input_sources = [
		(
			int(channel_by_id[channel_id].input_index),
			float(channel_by_id[channel_id].gain_db + settings.master_gain_db),
		)
		for channel_id in payload.channel_ids
		if channel_id in channel_by_id and channel_by_id[channel_id].input_index is not None
	]
	answer = await manager.create_answer(
		sdp=payload.sdp,
		type_=payload.type,
		input_sources=input_sources,
		replay_seconds=payload.replay_seconds,
	)
	return WebRTCAnswerResponse(sdp=answer.sdp, type=answer.type)


def _apply_imported_show(request: Request, updated_settings: object) -> None:
	"""Re-apply runtime services after the show file has been replaced."""
	request.app.state.rchat_broadcaster.update_settings(
		enabled=bool(updated_settings.rchat_enabled),
		flash_enabled=bool(updated_settings.rchat_flash_enabled),
		hold_seconds=int(updated_settings.rchat_hold_seconds),
		interface_ip=updated_settings.rchat_interface_ip,
		username=updated_settings.rchat_username,
	)


@router.get("/showfile/export")
async def download_showfile(
	request: Request,
	format: str = Query(default="archive", pattern="^(archive|json)$"),
) -> Response:
	"""Download the current show as a self-contained archive or plain showfile."""
	database = request.app.state.database
	settings = request.app.state.settings

	if format == "json":
		payload = await export_showfile(database, settings, embed_assets=False)
		payload.pop("_assets", None)
		body = ShowfilePayload(**payload).model_dump_json(indent=2)
		return Response(
			content=body,
			media_type="application/json",
			headers={
				"Content-Disposition": 'attachment; filename="micwise-showfile.micwise.json"',
			},
		)

	archive_bytes = await export_show_archive(database, settings)
	return Response(
		content=archive_bytes,
		media_type="application/zip",
		headers={
			"Content-Disposition": f'attachment; filename="{settings.show_name}.micwise.zip"',
		},
	)


def _archive_counts(data: bytes) -> tuple[int, int, int]:
	"""Return ``(channels, scenes, assets)`` described by a show archive."""
	try:
		archive = zipfile.ZipFile(io.BytesIO(data))
	except zipfile.BadZipFile as error:
		raise ValueError("Show archive is not a valid zip file") from error
	with archive:
		names = archive.namelist()
		if SHOWFILE_MEMBER not in names:
			raise ValueError("Show archive is missing its showfile")
		payload = json.loads(archive.read(SHOWFILE_MEMBER).decode("utf-8"))
		assets = [name for name in names if name.startswith("assets/photos/")]
		return len(payload.get("channels") or []), len(payload.get("scenes") or []), len(assets)


@router.post("/showfile/import", response_model=ShowfileImportResponse)
async def upload_showfile(request: Request) -> ShowfileImportResponse:
	"""Replace the current show with an imported showfile or show archive.

	Accepts a JSON showfile body (legacy) or ``multipart/form-data`` carrying
	either a ``.micwise.zip`` archive or a ``.micwise.json`` showfile.
	"""
	database = request.app.state.database
	settings = request.app.state.settings
	content_type = (request.headers.get("content-type") or "").lower()

	if content_type.startswith("multipart/form-data"):
		form = await request.form()
		upload = next((value for value in form.values() if hasattr(value, "read")), None)
		if upload is None:
			raise HTTPException(status_code=400, detail="Missing show file upload")
		data = await upload.read()
		file_name = str(getattr(upload, "filename", "") or "").lower()
		is_archive = file_name.endswith(".zip") or data[:2] == b"PK"
		try:
			if is_archive:
				updated_settings = await import_show_archive(database, settings, data)
				result_channels, result_scenes, result_assets = _archive_counts(data)
				import_format = "archive"
			else:
				payload = json.loads(data.decode("utf-8"))
				updated_settings = await import_showfile(database, payload, settings)
				result_channels = len(payload.get("channels") or [])
				result_scenes = len(payload.get("scenes") or [])
				result_assets = 0
				import_format = "showfile"
		except (ValueError, UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile) as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
	else:
		try:
			payload = ShowfilePayload(**(await request.json()))
		except Exception as error:
			raise HTTPException(status_code=400, detail="Show file body is not a valid showfile") from error
		try:
			updated_settings = await import_showfile(
				database,
				payload.model_dump(mode="python"),
				settings,
			)
		except ValueError as error:
			raise HTTPException(status_code=400, detail=str(error)) from error
		result_channels = len(payload.channels)
		result_scenes = len(payload.scenes)
		result_assets = 0
		import_format = "showfile"

	await request.app.state.restart_audio_runtime(updated_settings)
	_apply_imported_show(request, updated_settings)
	await request.app.state.scene_sync_service.reload()
	return ShowfileImportResponse(
		status="ok",
		channels=result_channels,
		scenes=result_scenes,
		assets=result_assets,
		format=import_format,
	)


@router.get("/assets/photos/{file_name}")
async def read_photo_asset_route(file_name: str, request: Request) -> FileResponse:
	"""Serve a photo from the show's local asset library."""
	settings = request.app.state.settings
	safe_name = Path(file_name).name
	if not safe_name or "/" in file_name or "\\" in file_name or ".." in file_name:
		raise HTTPException(status_code=400, detail="Invalid photo name")
	path = settings.photos_directory / safe_name
	if not path.is_file():
		raise HTTPException(status_code=404, detail="Photo not found")
	return FileResponse(path)


@router.post("/assets/photos", response_model=PhotoAssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_photo_asset(request: Request, file: UploadFile = File(...)) -> PhotoAssetResponse:
	"""Store a channel photo in the show's local asset library."""
	settings = request.app.state.settings
	source_name = file.filename or "photo.jpg"
	suffix = Path(source_name).suffix.lstrip(".").lower()
	if suffix and suffix not in ASSET_EXTENSIONS:
		raise HTTPException(status_code=400, detail="Unsupported photo type")

	content = await file.read()
	if not content:
		raise HTTPException(status_code=400, detail="Photo payload is empty")
	if len(content) > settings.photo_upload_max_bytes:
		raise HTTPException(status_code=413, detail="Photo is too large")

	try:
		photo_path = store_photo_asset(settings, content, source_name, file.content_type)
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error
	return PhotoAssetResponse(photo_path=photo_path, file_name=photo_path.rsplit("/", 1)[-1])
