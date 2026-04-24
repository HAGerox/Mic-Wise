"""WebSocket endpoints for live meter updates."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class WebSocketManager:
	"""Tracks active WebSocket clients and broadcasts JSON payloads."""

	def __init__(self) -> None:
		self._connections: set[WebSocket] = set()

	async def connect(self, websocket: WebSocket) -> None:
		"""Accept and register a new WebSocket connection."""
		await websocket.accept()
		self._connections.add(websocket)

	def disconnect(self, websocket: WebSocket) -> None:
		"""Remove a WebSocket connection from the active set."""
		self._connections.discard(websocket)

	async def broadcast(self, payload: dict[str, object]) -> None:
		"""Broadcast a JSON payload to all currently connected clients."""
		stale_connections: list[WebSocket] = []
		for websocket in self._connections:
			try:
				await websocket.send_json(payload)
			except Exception:
				stale_connections.append(websocket)

		for websocket in stale_connections:
			self.disconnect(websocket)


@router.websocket("/ws/meters")
async def meters_websocket(websocket: WebSocket) -> None:
	"""Stream live meter updates to the frontend."""
	manager: WebSocketManager = websocket.app.state.websocket_manager
	await manager.connect(websocket)
	await websocket.send_json(websocket.app.state.meter_analysis.latest_snapshot.to_dict())

	try:
		while True:
			await websocket.receive_text()
	except WebSocketDisconnect:
		manager.disconnect(websocket)
