"""mDNS/Zeroconf advertisement for Mic-Wise backend discovery."""

from __future__ import annotations

import socket
from dataclasses import dataclass

from zeroconf import ServiceInfo, Zeroconf


@dataclass(slots=True)
class ZeroconfService:
    """Advertise the Mic-Wise HTTP service on the local network."""

    service_name: str
    port: int
    service_type: str = "_micwise._tcp.local."
    host_ip: str | None = None
    zeroconf: Zeroconf | None = None
    service_info: ServiceInfo | None = None

    def start(self) -> None:
        """Register the service with the local Zeroconf responder."""
        host_ip = self.host_ip or self._detect_host_ip()
        self.zeroconf = Zeroconf()
        self.service_info = ServiceInfo(
            type_=self.service_type,
            name=f"{self.service_name}.{self.service_type}",
            addresses=[socket.inet_aton(host_ip)],
            port=self.port,
            properties={b"path": b"/"},
            server=f"{self.service_name}.local.",
        )
        self.zeroconf.register_service(self.service_info)

    def stop(self) -> None:
        """Unregister and close the Zeroconf responder."""
        if self.zeroconf is not None and self.service_info is not None:
            self.zeroconf.unregister_service(self.service_info)
        if self.zeroconf is not None:
            self.zeroconf.close()
        self.zeroconf = None
        self.service_info = None

    @staticmethod
    def _detect_host_ip() -> str:
        """Determine the host IP used for outbound LAN traffic."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
