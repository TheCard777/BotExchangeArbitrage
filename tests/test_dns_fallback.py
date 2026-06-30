"""Tests for the system-first DNS-over-HTTPS fallback (bot/dns_fallback.py)."""
import io
import socket

import pytest

from bot import dns_fallback


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_doh_lookup_parses_a_records(monkeypatch):
    payload = b'{"Answer": [{"type": 1, "data": "1.2.3.4"}, {"type": 1, "data": "5.6.7.8"}]}'
    monkeypatch.setattr(
        dns_fallback.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
    )
    assert dns_fallback.doh_lookup("api.binance.com") == ["1.2.3.4", "5.6.7.8"]


def test_doh_lookup_ignores_non_a_records(monkeypatch):
    payload = b'{"Answer": [{"type": 5, "data": "cname.example"}, {"type": 1, "data": "9.9.9.9"}]}'
    monkeypatch.setattr(
        dns_fallback.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(payload)
    )
    assert dns_fallback.doh_lookup("host") == ["9.9.9.9"]


def test_doh_lookup_returns_empty_and_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("no route")

    monkeypatch.setattr(dns_fallback.urllib.request, "urlopen", boom)
    assert dns_fallback.doh_lookup("host") == []


def test_patched_getaddrinfo_uses_system_when_it_works(monkeypatch):
    sentinel = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))]
    monkeypatch.setattr(dns_fallback, "_real_getaddrinfo", lambda *a, **k: sentinel)
    called = {"doh": False}
    monkeypatch.setattr(
        dns_fallback, "doh_lookup", lambda host: called.__setitem__("doh", True) or []
    )
    result = dns_fallback._patched_getaddrinfo("api.binance.com", 443)
    assert result is sentinel
    assert called["doh"] is False  # system worked, no DoH needed


def test_patched_getaddrinfo_falls_back_to_doh(monkeypatch):
    def fail(*a, **k):
        raise socket.gaierror("system DNS broken")

    monkeypatch.setattr(dns_fallback, "_real_getaddrinfo", fail)
    monkeypatch.setattr(dns_fallback, "doh_lookup", lambda host: ["1.2.3.4"])
    result = dns_fallback._patched_getaddrinfo("api.binance.com", 443)
    assert result == [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("1.2.3.4", 443))
    ]


def test_patched_getaddrinfo_reraises_when_doh_also_fails(monkeypatch):
    def fail(*a, **k):
        raise socket.gaierror("system DNS broken")

    monkeypatch.setattr(dns_fallback, "_real_getaddrinfo", fail)
    monkeypatch.setattr(dns_fallback, "doh_lookup", lambda host: [])
    with pytest.raises(socket.gaierror):
        dns_fallback._patched_getaddrinfo("api.binance.com", 443)


def test_install_and_uninstall_are_idempotent():
    was_installed = dns_fallback._installed
    try:
        dns_fallback.uninstall()
        assert socket.getaddrinfo is dns_fallback._real_getaddrinfo
        dns_fallback.install()
        assert socket.getaddrinfo is dns_fallback._patched_getaddrinfo
        dns_fallback.install()  # second call is a no-op
        assert socket.getaddrinfo is dns_fallback._patched_getaddrinfo
    finally:
        # Restore whatever state the rest of the suite expects.
        if was_installed:
            dns_fallback.install()
        else:
            dns_fallback.uninstall()


def test_force_os_resolver_switches_aiohttp_to_threaded():
    import aiohttp
    import aiohttp.connector as connector

    original = connector.DefaultResolver
    try:
        assert dns_fallback.force_os_resolver() is True
        # aiohttp/ccxt now resolve via the OS (getaddrinfo), like curl does,
        # instead of c-ares which fails on some networks.
        assert connector.DefaultResolver is aiohttp.ThreadedResolver
    finally:
        connector.DefaultResolver = original


def test_real_resolution_still_works_after_install():
    # Installing must not break normal localhost resolution.
    try:
        dns_fallback.install()
        result = socket.getaddrinfo("localhost", 80)
        assert result  # got at least one address
    finally:
        dns_fallback.uninstall()
