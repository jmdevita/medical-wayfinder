"""
SSRF guard for any endpoint that fetches a user-supplied URL.

The extract-departments tool calls `requests.get()` against arbitrary URLs.
Without filtering, an attacker could submit `http://169.254.169.254/...`
(cloud metadata), `http://localhost:9200/...` (internal services), or
`http://10.0.0.5/...` (LAN hosts). This blocks those at the API layer.

Pydantic's HttpUrl already restricts to http/https schemes — this adds
IP-range filtering on top.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_external_url(url: str) -> tuple[bool, str]:
    """Returns (ok, reason). Resolves the host and rejects private ranges."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Only http/https URLs allowed (got {parsed.scheme!r})"
    if not parsed.hostname:
        return False, "URL has no hostname"

    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        return False, f"DNS lookup failed for {parsed.hostname!r}: {exc}"

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return False, f"Could not parse address {addr!r}"
        if (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, f"{parsed.hostname} resolves to {addr}, which is in a blocked range"

    return True, "ok"
