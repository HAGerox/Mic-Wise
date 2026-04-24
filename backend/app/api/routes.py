"""REST API routes for the Mic-Wise backend MVP."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Query, Request, Response, status

from app.api.schemas import (
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
	SceneUpdateRequest,
	SettingsResponse,
	SettingsUpdateRequest,
	WebRTCAnswerResponse,
	WebRTCOfferRequest,
)
from app.audio.analysis import build_channel_waveform_preview
from app.database.repository import (
	create_channel,
	create_scene,
	delete_channel,
	delete_scene,
	get_channel,
	get_channels_by_ids,
	get_scene,
	get_settings,
	list_channels,
	list_scenes,
	update_scene,
	update_channel,
	update_settings,
)

router = APIRouter()


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
	changes = payload.model_dump(exclude_unset=True)
	if "active_scene_id" in changes and changes["active_scene_id"] is not None:
		scene = await get_scene(database, int(changes["active_scene_id"]))
		if scene is None:
			raise HTTPException(status_code=404, detail="Scene not found")
	if not changes:
		return await get_settings(database)
	updated_settings = await update_settings(database, changes)
	await request.app.state.scene_sync_service.reload()
	return updated_settings


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
	points: int = Query(default=240, ge=32, le=600),
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
