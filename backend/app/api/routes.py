"""REST API routes for the Mic-Wise backend MVP."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.schemas import (
	ChannelResponse,
	ChannelUpdateRequest,
	HealthResponse,
	MeterSnapshotResponse,
	SceneResponse,
	SettingsResponse,
	WebRTCAnswerResponse,
	WebRTCOfferRequest,
)
from app.database.repository import get_settings, list_channels, list_scenes, update_channel

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def healthcheck(request: Request) -> HealthResponse:
	"""Return a minimal health report for the backend."""
	analyzer = request.app.state.meter_analysis
	audio_process = request.app.state.audio_process
	return HealthResponse(
		status="ok",
		audio_engine_running=audio_process.is_alive(),
		buffer_write_head=analyzer.latest_snapshot.write_head,
	)


@router.get("/settings", response_model=SettingsResponse)
async def read_settings(request: Request) -> SettingsResponse:
	"""Return the active show settings."""
	database = request.app.state.database
	return await get_settings(database)


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
	manager = request.app.state.webrtc_manager
	answer = await manager.create_answer(
		sdp=payload.sdp,
		type_=payload.type,
		channel_numbers=payload.channel_numbers,
		replay_seconds=payload.replay_seconds,
	)
	return WebRTCAnswerResponse(sdp=answer.sdp, type=answer.type)
