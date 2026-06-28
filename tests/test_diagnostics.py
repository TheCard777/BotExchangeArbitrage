"""Tests for connection-error classification (bot/diagnostics.py)."""
from bot.diagnostics import (
    AUTH,
    BLOCKED,
    GEOBLOCK,
    MAINTENANCE,
    NETWORK,
    TIMEOUT,
    UNKNOWN,
    classify_error,
    classify_http_status,
)


def cat(exc):
    return classify_error(exc)[0]


def test_geoblock_from_451_message():
    assert cat(Exception("binance GET ... 451 Service unavailable from a restricted location")) == GEOBLOCK


def test_geoblock_from_restricted_jurisdiction():
    assert cat(Exception("Eligibility: not available in your country")) == GEOBLOCK


def test_timeout_detected():
    assert cat(Exception("kraken GET https://... request timeout (10000 ms)")) == TIMEOUT


def test_forbidden_403_is_blocked():
    assert cat(Exception("403 Forbidden: access denied by firewall")) == BLOCKED


def test_dns_or_network_failure():
    assert cat(Exception("Cannot connect to host api.binance.com:443 ssl:default")) == NETWORK
    assert cat(Exception("[Errno -2] Name or service not known")) == NETWORK


def test_maintenance_detected():
    assert cat(Exception("system maintenance in progress")) == MAINTENANCE


def test_auth_error_detected():
    assert cat(Exception("Invalid API-key, IP, or permissions for action")) == AUTH


def test_unknown_falls_back():
    category, message = classify_error(Exception("something totally weird"))
    assert category == UNKNOWN
    assert "something totally weird" in message


# --- type-based fallback (ccxt exceptions with no keyword in the message) ---


def _make(name, base=Exception):
    return type(name, (base,), {})


def test_exchange_not_available_type_maps_to_network():
    exc = _make("ExchangeNotAvailable")("binance GET https://api.binance.com/api/v3/exchangeInfo")
    assert cat(exc) == NETWORK


def test_request_timeout_type_maps_to_timeout():
    exc = _make("RequestTimeout")("binance GET ...")
    assert cat(exc) == TIMEOUT


def test_ddos_protection_type_maps_to_blocked():
    exc = _make("DDoSProtection")("binance GET ...")
    assert cat(exc) == BLOCKED


def test_authentication_error_type_maps_to_auth():
    exc = _make("AuthenticationError")("binance GET ...")
    assert cat(exc) == AUTH


def test_subclass_of_networkerror_maps_to_network():
    network_base = _make("NetworkError")
    exc = _make("SomeWeirdNetIssue", base=network_base)("binance GET ...")
    assert cat(exc) == NETWORK


# --- classify_http_status (literal status from the raw probe) --------------


def test_status_451_is_geoblock():
    category, message = classify_http_status(451)
    assert category == GEOBLOCK
    assert "451" in message


def test_status_403_is_blocked():
    assert classify_http_status(403)[0] == BLOCKED


def test_status_429_is_blocked():
    assert classify_http_status(429)[0] == BLOCKED


def test_status_5xx_is_maintenance():
    assert classify_http_status(503)[0] == MAINTENANCE


def test_status_200_is_reachable():
    category, message = classify_http_status(200)
    assert category is None
    assert "joignable" in message


def test_status_other_4xx_is_still_reachable():
    # A 400/401/404 still proves the API answered — the host is reachable.
    assert classify_http_status(404)[0] is None


def test_every_category_returns_nonempty_french_message():
    for exc in [
        Exception("451 restricted location"),
        Exception("request timeout"),
        Exception("403 forbidden"),
        Exception("cannot connect to host"),
        Exception("system maintenance"),
        Exception("invalid api-key"),
        Exception("weird"),
    ]:
        _, message = classify_error(exc)
        assert isinstance(message, str) and len(message) > 0
