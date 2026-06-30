"""Make the bot's DNS resolution behave like curl/the browser.

Two real-world failures seen on a client's machine, both fixed here:

1. aiohttp (and therefore ccxt) defaults to the c-ares resolver (the `aiodns`
   package) when it is installed. On some networks c-ares fails to resolve
   ("ClientConnectorDNSError") even though the OS resolver works fine — proven
   by `curl https://api.binance.com/...` returning 200 on the same machine
   where the bot failed. force_os_resolver() makes aiohttp use the OS resolver
   (getaddrinfo), exactly what curl and the browser use.

2. On machines whose system DNS is itself broken (browser still works via its
   own DNS-over-HTTPS), install_doh_fallback() wraps socket.getaddrinfo so it
   falls back to public DoH resolvers (1.1.1.1, 8.8.8.8, reached by IP) only
   when the system resolver fails — system-first, so it never regresses a
   machine whose DNS already works.

install() applies both. Stdlib only for the DoH part (urllib + ssl).
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


def force_os_resolver() -> bool:
    """Make aiohttp/ccxt resolve via the OS (getaddrinfo) instead of c-ares.

    This is the fix for networks where the c-ares resolver (aiodns) fails but
    the OS resolver works (curl/browser work, the bot doesn't). Returns True if
    the resolver was switched. Safe no-op if aiohttp isn't importable.
    """
    try:
        import aiohttp
        import aiohttp.connector as connector

        connector.DefaultResolver = aiohttp.ThreadedResolver
        return True
    except Exception:
        return False


def install() -> None:
    """Apply both DNS fixes process-wide. Idempotent and safe: if anything goes
    wrong it leaves the standard resolver untouched."""
    global _installed
    if _installed:
        return
    force_os_resolver()
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
