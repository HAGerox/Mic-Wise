"""REST API routes for the Mic-Wise backend MVP."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.api.schemas import (
	AudioAlertResponse,
	AudioInputDeviceResponse,
	ChannelCreateRequest,
	ChannelResponse,
	ChannelUpdateRequest,
	ChannelWaveformResponse,
	HealthResponse,
	MeterSnapshotResponse,
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
	create_channel,
	create_scene,
	delete_channel,
	delete_scene,
	export_showfile,
	get_channel,
	get_channels_by_ids,
	get_scene,
	get_settings,
	import_showfile,
	list_channels,
	list_scenes,
	update_scene,
	update_channel,
	update_settings,
)

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
	return HealthResponse(
		status="ok",
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

	for field_name in ("sample_rate", "channel_count", "buffer_duration_sec", "block_size", "alert_popup_duration_sec", "radioworld_hold_seconds"):
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

	request.app.state.radioworld_broadcaster.update_settings(
		enabled=bool(updated_settings.radioworld_enabled),
		flash_enabled=bool(updated_settings.radioworld_flash_enabled),
		hold_seconds=int(updated_settings.radioworld_hold_seconds),
	)
	if set(changes) & SYNC_SETTING_FIELDS:
		await request.app.state.scene_sync_service.reload()
	return updated_settings


@router.get("/audio/devices", response_model=list[AudioInputDeviceResponse])
async def read_audio_input_devices() -> list[AudioInputDeviceResponse]:
	"""Return the currently available cross-platform audio capture devices."""
	return [AudioInputDeviceResponse(**device.to_dict()) for device in list_audio_input_devices()]


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


@router.get("/showfile/export")
async def download_showfile(request: Request) -> Response:
	"""Download the current show as a portable JSON showfile."""
	database = request.app.state.database
	payload = ShowfilePayload(**(await export_showfile(database)))
	return Response(
		content=payload.model_dump_json(indent=2),
		media_type="application/json",
		headers={
			"Content-Disposition": 'attachment; filename="micwise-showfile.micwise.json"',
		},
	)


@router.post("/showfile/import", response_model=ShowfileImportResponse)
async def upload_showfile(payload: ShowfilePayload, request: Request) -> ShowfileImportResponse:
	"""Replace the current show with an imported portable showfile."""
	database = request.app.state.database
	updated_settings = await import_showfile(database, payload.model_dump(mode="python"))
	await request.app.state.restart_audio_runtime(updated_settings)
	request.app.state.radioworld_broadcaster.update_settings(
		enabled=bool(updated_settings.radioworld_enabled),
		flash_enabled=bool(updated_settings.radioworld_flash_enabled),
		hold_seconds=int(updated_settings.radioworld_hold_seconds),
	)
	await request.app.state.scene_sync_service.reload()
	return ShowfileImportResponse(status="ok", channels=len(payload.channels), scenes=len(payload.scenes))
