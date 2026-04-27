"""RadioWorld UDP chatbox notification helpers."""

from __future__ import annotations

import asyncio
import socket
import time
from contextlib import suppress
from dataclasses import dataclass

from app.network.interfaces import resolve_broadcast_address


RADIOWORLD_BROADCAST_ADDRESS = "255.255.255.255"
RADIOWORLD_PORT = 1090
RADIOWORLD_REPEAT_DELAY_SECONDS = 0.039
RADIOWORLD_FLASH_SETTLE_DELAY_SECONDS = 0.12


def build_radioworld_packet(sender_ip: str, command: str) -> bytes:
    """Build a RadioWorld UDP payload using the observed wire format."""
    safe_sender_ip = str(sender_ip).strip() or "127.0.0.1"
    safe_command = str(command)
    return f"RWSENDIP{safe_sender_ip}#{safe_command}".encode("ascii", "ignore")


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
class RadioWorldSettings:
    """Runtime configuration for RadioWorld alert messages."""

    enabled: bool = False
    flash_enabled: bool = False
    hold_seconds: int = 8
    interface_ip: str | None = None


@dataclass(slots=True)
class RadioWorldSendStatus:
    """Details for the most recent RadioWorld test transmission."""

    sender_ip: str
    source_port: int
    destinations: list[str]
    destination_port: int

    def to_dict(self) -> dict[str, object]:
        return {
            "sender_ip": self.sender_ip,
            "source_port": self.source_port,
            "destinations": self.destinations,
            "destination_port": self.destination_port,
        }


class RadioWorldBroadcaster:
    """Broadcast alert messages using the reverse-engineered RadioWorld protocol."""

    def __init__(
        self,
        *,
        sender_ip: str | None = None,
        destination_address: str = RADIOWORLD_BROADCAST_ADDRESS,
        port: int = RADIOWORLD_PORT,
        repeat_delay_seconds: float = RADIOWORLD_REPEAT_DELAY_SECONDS,
        flash_settle_delay_seconds: float = RADIOWORLD_FLASH_SETTLE_DELAY_SECONDS,
    ) -> None:
        self.sender_ip = sender_ip or resolve_sender_ip()
        self.destination_address = destination_address
        self.port = port
        self.repeat_delay_seconds = repeat_delay_seconds
        self.flash_settle_delay_seconds = max(0.0, float(flash_settle_delay_seconds))
        self.settings = RadioWorldSettings()
        self._clear_task: asyncio.Task[None] | None = None
        self._message_token = 0
        self._last_flash_enabled = False

    def update_settings(
        self,
        *,
        enabled: bool,
        flash_enabled: bool,
        hold_seconds: int,
        interface_ip: str | None = None,
    ) -> None:
        """Apply the persisted notification settings."""
        self.settings = RadioWorldSettings(
            enabled=bool(enabled),
            flash_enabled=bool(flash_enabled),
            hold_seconds=max(0, int(hold_seconds)),
            interface_ip=str(interface_ip).strip() if interface_ip else None,
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
            await self._enable_flash()
            self._last_flash_enabled = True
        elif self._last_flash_enabled:
            await self._send_command("COMM1")
            self._last_flash_enabled = False

        if self.settings.hold_seconds > 0:
            self._clear_task = asyncio.create_task(
                self._clear_after_delay(current_token, self.settings.hold_seconds),
                name="radioworld-clear-message",
            )

    async def send_test_message(self) -> RadioWorldSendStatus:
        """Broadcast a diagnostic message regardless of the enabled toggle."""
        self._message_token += 1
        current_token = self._message_token
        if self._clear_task is not None:
            self._clear_task.cancel()
            self._clear_task = None

        await self._send_text("Mic-Wise RadioWorld test")
        if self.settings.flash_enabled:
            await self._enable_flash()
            self._last_flash_enabled = True
        if self.settings.hold_seconds > 0:
            self._clear_task = asyncio.create_task(
                self._clear_after_delay(current_token, self.settings.hold_seconds),
                name="radioworld-clear-test-message",
            )
        return self.get_send_status()

    def get_send_status(self) -> RadioWorldSendStatus:
        """Return the current RadioWorld UDP send target details."""
        return RadioWorldSendStatus(
            sender_ip=self.sender_ip,
            source_port=self.port,
            destinations=self._destination_addresses(),
            destination_port=self.port,
        )

    async def clear(self) -> None:
        """Clear the currently displayed RadioWorld message."""
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
        await self._send_command("KEYP")
        await self._send_command(f"KEYP{message}", duplicate=False)
        await self._send_command(f"KEYP{message}\n", duplicate=False)

    async def _enable_flash(self) -> None:
        """Allow the receiver a brief moment to apply text before flashing it."""
        if self.flash_settle_delay_seconds > 0:
            await asyncio.sleep(self.flash_settle_delay_seconds)
        await self._send_command("COMM0")

    async def _send_command(self, command: str, *, duplicate: bool = True) -> None:
        await asyncio.to_thread(self._send_command_sync, command, duplicate)

    def _destination_addresses(self) -> list[str]:
        addresses = [self.destination_address]
        directed_broadcast = resolve_broadcast_address(self.settings.interface_ip)
        if directed_broadcast and directed_broadcast not in addresses:
            addresses.append(directed_broadcast)
        return addresses

    def _send_command_sync(self, command: str, duplicate: bool) -> None:
        payload = build_radioworld_packet(self.sender_ip, command)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as broadcast_socket:
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                with suppress(OSError):
                    broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            broadcast_socket.bind((self.settings.interface_ip or "", self.port))

            for destination_address in self._destination_addresses():
                broadcast_socket.sendto(payload, (destination_address, self.port))
            if duplicate:
                time.sleep(self.repeat_delay_seconds)
                for destination_address in self._destination_addresses():
                    broadcast_socket.sendto(payload, (destination_address, self.port))
