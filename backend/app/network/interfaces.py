"""Network interface discovery helpers."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import IPv4Interface

import ifaddr


@dataclass(slots=True)
class NetworkInterface:
	"""An IPv4 address that can be used as a UDP broadcast source."""

	name: str
	display_name: str
	ipv4_address: str
	broadcast_address: str | None
	is_loopback: bool

	def to_dict(self) -> dict[str, object]:
		return {
			"name": self.name,
			"display_name": self.display_name,
			"ipv4_address": self.ipv4_address,
			"broadcast_address": self.broadcast_address,
			"is_loopback": self.is_loopback,
		}


def _broadcast_address(ip_address: str, prefix_length: int | None) -> str | None:
	if prefix_length is None:
		return None
	try:
		return str(IPv4Interface(f"{ip_address}/{prefix_length}").network.broadcast_address)
	except ValueError:
		return None


def list_ipv4_network_interfaces() -> list[NetworkInterface]:
	"""Return configured IPv4 network interfaces for user selection."""
	interfaces: list[NetworkInterface] = []
	for adapter in ifaddr.get_adapters():
		for ip in adapter.ips:
			if not isinstance(ip.ip, str) or ":" in ip.ip:
				continue
			is_loopback = ip.ip.startswith("127.")
			interfaces.append(
				NetworkInterface(
					name=adapter.name,
					display_name=f"{adapter.nice_name} ({ip.ip})",
					ipv4_address=ip.ip,
					broadcast_address=_broadcast_address(ip.ip, getattr(ip, "network_prefix", None)),
					is_loopback=is_loopback,
				),
			)
	return sorted(interfaces, key=lambda item: (item.is_loopback, item.display_name.lower()))


def resolve_broadcast_address(interface_ip: str | None) -> str | None:
	"""Find the directed broadcast address for a selected IPv4 interface."""
	if not interface_ip:
		return None
	for network_interface in list_ipv4_network_interfaces():
		if network_interface.ipv4_address == interface_ip:
			return network_interface.broadcast_address
	return None
