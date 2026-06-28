from __future__ import annotations

import ipaddress
import re

CLIENT_IP_ACCESS_PUBLIC = "public"
CLIENT_IP_ACCESS_RESTRICTED = "restricted"
CLIENT_IP_ACCESS_MODES = {CLIENT_IP_ACCESS_PUBLIC, CLIENT_IP_ACCESS_RESTRICTED}


def normalize_client_ip_access_mode(value: str | None) -> str:
    mode = (value or CLIENT_IP_ACCESS_PUBLIC).strip().lower()
    if mode not in CLIENT_IP_ACCESS_MODES:
        raise ValueError("Client IP access mode must be public or restricted")
    return mode


def normalize_client_ip_allowlist(value: str) -> str:
    entries: list[str] = []
    seen: set[str] = set()
    for candidate in re.split(r"[\s,]+", value.strip()):
        if not candidate:
            continue
        try:
            normalized = (
                str(ipaddress.ip_network(candidate, strict=False))
                if "/" in candidate
                else str(ipaddress.ip_address(candidate))
            )
        except ValueError as exc:
            raise ValueError("Client IP allowlist must contain only IP addresses or CIDR ranges") from exc
        if normalized not in seen:
            entries.append(normalized)
            seen.add(normalized)
    return "\n".join(entries)


def client_ip_allowlist_networks(value: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in normalize_client_ip_allowlist(value).splitlines():
        networks.append(ipaddress.ip_network(entry, strict=False))
    return networks


def client_ip_allowed(client_host: str, allowlist: str) -> bool:
    if not client_host.strip():
        return False
    try:
        client_ip = ipaddress.ip_address(client_host.strip())
    except ValueError:
        return False
    return any(client_ip in network for network in client_ip_allowlist_networks(allowlist))
