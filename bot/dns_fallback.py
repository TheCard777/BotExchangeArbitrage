"""System-first DNS with a DNS-over-HTTPS (DoH) fallback.

On some machines (seen on slow/limited mobile connections) the *system* DNS
is broken or blocked, yet the browser still works because it resolves names
over HTTPS (DoH). Plain Python then fails every connection with a DNS error
while the browser is fine.

This module installs a wrapper around socket.getaddrinfo that keeps using the
system resolver normally, and only when it fails falls back to querying public
DoH resolvers (Cloudflare 1.1.1.1, Google 8.8.8.8) — reached by IP, so no
working system DNS is needed. Because it is system-first, it adds nothing to
the normal path and cannot regress a machine whose DNS already works.

Stdlib only (urllib + ssl), so no extra dependency to install.
"""
from __future__ import annotations

import json
import socket
import ssl
import urllib.request

# Public DoH resolvers, reached by IP so they work even with broken system DNS.
# Cloudflare and Google both serve a JSON DoH API and hold valid TLS certs for
# their resolver IPs.
_DOH_URLS = (
    "https://1.1.1.1/dns-query",
    "https://8.8.8.8/resolve",
)
_DOH_TIMEOUT = 5

_real_getaddrinfo = socket.getaddrinfo
_installed = False


def doh_lookup(host: str) -> list[str]:
    """Resolve a hostname to IPv4 addresses via public DoH resolvers.

    Returns a (possibly empty) list of IP strings; never raises.
    """
    context = ssl.create_default_context()
    for base in _DOH_URLS:
        try:
            url = f"{base}?name={host}&type=A"
            request = urllib.request.Request(url, headers={"accept": "application/dns-json"})
            with urllib.request.urlopen(request, timeout=_DOH_TIMEOUT, context=context) as response:
                payload = json.load(response)
            ips = [
                answer["data"]
                for answer in payload.get("Answer", [])
                if answer.get("type") == 1 and answer.get("data")  # type 1 = A record
            ]
            if ips:
                return ips
        except Exception:
            continue
    return []


def _patched_getaddrinfo(host, port, *args, **kwargs):
    try:
        return _real_getaddrinfo(host, port, *args, **kwargs)
    except socket.gaierror:
        # System resolver failed — try DoH before giving up.
        if not isinstance(host, str):
            raise
        ips = doh_lookup(host)
        if not ips:
            raise
        resolved_port = port if isinstance(port, int) else 0
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, resolved_port))
            for ip in ips
        ]


def install() -> None:
    """Activate the DoH fallback process-wide. Idempotent and safe: if anything
    goes wrong it leaves the standard resolver untouched."""
    global _installed
    if _installed:
        return
    try:
        socket.getaddrinfo = _patched_getaddrinfo
        _installed = True
    except Exception:
        socket.getaddrinfo = _real_getaddrinfo


def uninstall() -> None:
    """Restore the original resolver (used by tests)."""
    global _installed
    socket.getaddrinfo = _real_getaddrinfo
    _installed = False
