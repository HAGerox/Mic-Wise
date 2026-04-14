"""REST API routes for the Mic-Wise backend MVP."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.schemas import (
	ChannelResponse,
	ChannelUpdateRequest,
	ChannelWaveformResponse,
	HealthResponse,
	MeterSnapshotResponse,
	SceneResponse,
	SettingsResponse,
	SettingsUpdateRequest,
	WebRTCAnswerResponse,
	WebRTCOfferRequest,
)
from app.audio.analysis import build_channel_waveform_preview
from app.database.repository import (
	get_channel,
	get_channels_by_ids,
	get_settings,
	list_channels,
	list_scenes,
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
	if not changes:
		return await get_settings(database)
	return await update_settings(database, changes)


@router.get("/channels", response_model=list[ChannelResponse])
async def read_channels(request: Request) -> list[ChannelResponse]:
	"""Return the configured channel list."""
	database = request.app.state.database
	return await list_channels(database)


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
	channel_records = await get_channels_by_ids(database, payload.channel_ids)
	channel_by_id = {channel.id: channel for channel in channel_records}
	input_indices = [
		channel_by_id[channel_id].input_index
		for channel_id in payload.channel_ids
		if channel_id in channel_by_id and channel_by_id[channel_id].input_index is not None
	]
	answer = await manager.create_answer(
		sdp=payload.sdp,
		type_=payload.type,
		input_indices=input_indices,
		replay_seconds=payload.replay_seconds,
	)
	return WebRTCAnswerResponse(sdp=answer.sdp, type=answer.type)
