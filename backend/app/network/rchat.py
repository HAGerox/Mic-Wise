"""RChat UDP notification helpers."""

from __future__ import annotations

import asyncio
import socket
from contextlib import suppress
from dataclasses import dataclass

from app.network.interfaces import resolve_broadcast_address


RCHAT_BROADCAST_ADDRESS = "255.255.255.255"
RCHAT_PORT = 1090
RCHAT_DEFAULT_USERNAME = "Mic-Wise"


def _safe_username(username: str) -> str:
    """Return a username that cannot break RChat's hash-delimited envelope."""
    safe_username = str(username).replace("#", " ").replace("\r", " ").replace("\n", " ").strip()
    return safe_username or RCHAT_DEFAULT_USERNAME


def build_rchat_packet(sender_ip: str, username: str, command: str) -> bytes:
    """Build the UTF-8 packet format used by RChat 1.5."""
    safe_sender_ip = str(sender_ip).strip() or "127.0.0.1"
    return f"RWSENDIP{safe_sender_ip}#USER{_safe_username(username)}#{command}".encode("utf-8")


def resolve_sender_ip() -> str:
    """Best-effort resolution of the local IPv4 address for UDP broadcasts."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe_socket:
        try:
            probe_socket.connect(("8.8.8.8", 80))
            resolved_ip = probe_socket.getsockname()[0]
        except OSError:
            resolved_ip = "127.0.0.1"
    return resolved_ip


@dataclass(slots=True)
class RChatSettings:
    """Runtime configuration for RChat alert messages."""

    enabled: bool = False
    flash_enabled: bool = False
    hold_seconds: int = 8
    interface_ip: str | None = None
    username: str = RCHAT_DEFAULT_USERNAME


@dataclass(slots=True)
class RChatSendStatus:
    """Details for the most recent RChat transmission."""

    sender_ip: str
    username: str
    source_port: int
    destinations: list[str]
    destination_port: int
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "sender_ip": self.sender_ip,
            "username": self.username,
            "source_port": self.source_port,
            "destinations": self.destinations,
            "destination_port": self.destination_port,
            "error": self.error,
        }


class RChatBroadcaster:
    """Broadcast alert messages using RChat's UDP protocol."""

    def __init__(
        self,
        *,
        sender_ip: str | None = None,
        destination_address: str = RCHAT_BROADCAST_ADDRESS,
        port: int = RCHAT_PORT,
    ) -> None:
        self.sender_ip = sender_ip or resolve_sender_ip()
        self.destination_address = destination_address
        self.port = port
        self.settings = RChatSettings()
        self._clear_task: asyncio.Task[None] | None = None
        self._message_token = 0
        self._last_flash_enabled = False
        self._last_error: str | None = None
        self._source_port = port

    def update_settings(
        self,
        *,
        enabled: bool,
        flash_enabled: bool,
        hold_seconds: int,
        interface_ip: str | None = None,
        username: str = RCHAT_DEFAULT_USERNAME,
    ) -> None:
        """Apply the persisted notification settings."""
        self.settings = RChatSettings(
            enabled=bool(enabled),
            flash_enabled=bool(flash_enabled),
            hold_seconds=max(0, int(hold_seconds)),
            interface_ip=str(interface_ip).strip() if interface_ip else None,
            username=_safe_username(username),
        )
        self.sender_ip = self.settings.interface_ip or resolve_sender_ip()

    async def notify_alert(self, message: str) -> None:
        """Broadcast a new alert message and schedule a clear if configured."""
        if not self.settings.enabled:
            return

        safe_message = str(message).strip()
        if not safe_message:
            return

        self._message_token += 1
        current_token = self._message_token
        if self._clear_task is not None:
            self._clear_task.cancel()
            self._clear_task = None

        await self._send_text(safe_message)
        if self.settings.flash_enabled:
            await self._send_command("COMM0")
            self._last_flash_enabled = True
        elif self._last_flash_enabled:
            await self._send_command("COMM1")
            self._last_flash_enabled = False

        if self.settings.hold_seconds > 0:
            self._clear_task = asyncio.create_task(
                self._clear_after_delay(current_token, self.settings.hold_seconds),
                name="rchat-clear-message",
            )

    async def send_test_message(self) -> RChatSendStatus:
        """Broadcast a diagnostic message regardless of the enabled toggle."""
        self._last_error = None
        self._message_token += 1
        current_token = self._message_token
        if self._clear_task is not None:
            self._clear_task.cancel()
            self._clear_task = None

        await self._send_text("Mic-Wise RChat test")
        if self.settings.flash_enabled:
            await self._send_command("COMM0")
            self._last_flash_enabled = True
        if self.settings.hold_seconds > 0:
            self._clear_task = asyncio.create_task(
                self._clear_after_delay(current_token, self.settings.hold_seconds),
                name="rchat-clear-test-message",
            )
        return self.get_send_status()

    def get_send_status(self) -> RChatSendStatus:
        """Return the current RChat UDP send target details."""
        return RChatSendStatus(
            sender_ip=self.sender_ip,
            username=self.settings.username,
            source_port=self._source_port,
            destinations=self._destination_addresses(),
            destination_port=self.port,
            error=self._last_error,
        )

    async def clear(self) -> None:
        """Clear the currently displayed RChat message."""
        if self._last_flash_enabled:
            await self._send_command("COMM1")
            self._last_flash_enabled = False
        await self._send_command("COMM8")

    async def close(self) -> None:
        """Cancel pending tasks and stop managing the current message."""
        if self._clear_task is not None:
            self._clear_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._clear_task
            self._clear_task = None

    async def _clear_after_delay(self, token: int, hold_seconds: int) -> None:
        try:
            await asyncio.sleep(max(0, hold_seconds))
            if token != self._message_token:
                return
            await self.clear()
        except asyncio.CancelledError:
            raise

    async def _send_text(self, message: str) -> None:
        await self._send_command(f"KEYP{message}")

    async def _send_command(self, command: str) -> None:
        try:
            await asyncio.to_thread(self._send_command_sync, command)
        except OSError as error:
            self._last_error = str(error)

    def _destination_addresses(self) -> list[str]:
        directed_broadcast = None
        with suppress(Exception):
            directed_broadcast = resolve_broadcast_address(self.settings.interface_ip)
        return [directed_broadcast or self.destination_address]

    def _send_command_sync(self, command: str) -> None:
        payload = build_rchat_packet(self.sender_ip, self.settings.username, command)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as broadcast_socket:
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                with suppress(OSError):
                    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            try:
                broadcast_socket.bind((self.settings.interface_ip or "", self.port))
            except OSError:
                # RChat and Mic-Wise may run on the same host. Its Companion
                # module also uses an ephemeral source port, which receivers accept.
                broadcast_socket.bind((self.settings.interface_ip or "", 0))
            self._source_port = int(broadcast_socket.getsockname()[1])
            broadcast_socket.sendto(payload, (self._destination_addresses()[0], self.port))
