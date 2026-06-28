from __future__ import annotations

import ipaddress


def normalize_proxy_ip_list(value: str) -> str:
    if not value:
        return ""
    networks: list[str] = []
    seen: set[str] = set()
    for part in value.split(","):
        candidate = part.strip()
        if not candidate:
            continue
        normalized = str(ipaddress.ip_network(candidate, strict=False))
        if normalized in seen:
            continue
        seen.add(normalized)
        networks.append(normalized)
    return ",".join(networks)


def combined_trusted_proxy_ips(compose_app_subnet: str, trusted_proxy_ips: str) -> str:
    return normalize_proxy_ip_list(",".join(part for part in [compose_app_subnet, trusted_proxy_ips] if part.strip()))
