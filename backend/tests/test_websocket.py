"""Tests for WebSocket meter broadcasting."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from app.api.websocket import WebSocketManager


class SelfDisconnectingWebSocket:
    """Test double that removes itself during a broadcast send."""

    def __init__(self, manager: WebSocketManager) -> None:
        self.manager = manager
        self.payloads: list[dict[str, object]] = []

    async def send_json(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)
        self.manager.disconnect(cast(Any, self))


def test_websocket_manager_broadcast_tolerates_disconnect_during_iteration() -> None:
    manager = WebSocketManager()
    websocket = SelfDisconnectingWebSocket(manager)
    payload = {"channels": []}

    manager._connections.add(cast(Any, websocket))

    asyncio.run(manager.broadcast(payload))

    assert websocket.payloads == [payload]
    assert manager._connections == set()