"""Tests for connection resilience and the connectivity self-check (main.py)."""
import pytest

import main
from bot.scanner import ArbitrageScanner
from tests.conftest import FakeClient, FlakyClient


def make_scanner(clients):
    return ArbitrageScanner({c.id: c for c in clients}, ["BTC/USDT"], 0.005)


async def test_all_exchanges_connect_first_try():
    a = FakeClient("a")
    b = FakeClient("b")
    scanner = make_scanner([a, b])
    await main.connect_with_retries(scanner, attempts=3, delay_seconds=0)
    assert set(scanner.clients) == {"a", "b"}
    assert not a.closed and not b.closed
    assert a.load_attempts == 1 and b.load_attempts == 1


async def test_drops_one_dead_exchange_keeps_the_rest():
    a = FakeClient("a")
    b = FakeClient("b")
    dead = FakeClient("dead", load_error=ConnectionError("nope"))
    scanner = make_scanner([a, b, dead])
    await main.connect_with_retries(scanner, attempts=2, delay_seconds=0)
    # Dead one is dropped and properly closed; the others survive.
    assert set(scanner.clients) == {"a", "b"}
    assert dead.closed is True


async def test_only_failing_exchanges_are_retried():
    a = FakeClient("a")
    dead = FakeClient("dead", load_error=ConnectionError("nope"))
    scanner = make_scanner([a, dead])
    # 'a' connects on attempt 1 and must NOT be retried on later attempts.
    # With only 1 survivor this raises (min 2), but we assert the retry counts.
    try:
        await main.connect_with_retries(scanner, attempts=3, delay_seconds=0)
    except RuntimeError:
        pass
    assert a.load_attempts == 1
    assert dead.load_attempts == 3


async def test_flaky_exchange_recovers_before_giving_up():
    a = FakeClient("a")
    flaky = FlakyClient("flaky", fail_times=2)
    scanner = make_scanner([a, flaky])
    await main.connect_with_retries(scanner, attempts=5, delay_seconds=0)
    assert set(scanner.clients) == {"a", "flaky"}
    assert flaky.closed is False
    assert flaky.load_attempts == 3  # failed twice, succeeded on the third


async def test_raises_when_fewer_than_two_exchanges_survive():
    only = FakeClient("only")
    dead = FakeClient("dead", load_error=ConnectionError("nope"))
    scanner = make_scanner([only, dead])
    with pytest.raises(RuntimeError, match="minimum 2"):
        await main.connect_with_retries(scanner, attempts=2, delay_seconds=0)


async def test_raises_when_all_exchanges_fail():
    d1 = FakeClient("d1", load_error=ConnectionError("nope"))
    d2 = FakeClient("d2", load_error=ConnectionError("nope"))
    scanner = make_scanner([d1, d2])
    with pytest.raises(RuntimeError):
        await main.connect_with_retries(scanner, attempts=2, delay_seconds=0)
    assert d1.closed and d2.closed


# --- check_internet_connectivity ------------------------------------------


class _FakeResponse:
    def __init__(self, raise_exc=None):
        self._raise = raise_exc

    async def __aenter__(self):
        if self._raise is not None:
            raise self._raise
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    def __init__(self, outcomes=None, raise_exc=None):
        # outcomes: list of per-call exceptions (None = success). raise_exc:
        # same exception for every call.
        self._outcomes = list(outcomes) if outcomes is not None else None
        self._raise = raise_exc
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, **kwargs):
        exc = self._raise
        if self._outcomes is not None:
            exc = self._outcomes[self.calls] if self.calls < len(self._outcomes) else OSError("down")
        self.calls += 1
        return _FakeResponse(exc)


async def test_connectivity_true_when_any_response_received(monkeypatch):
    monkeypatch.setattr(main.aiohttp, "ClientSession", lambda **kw: _FakeSession())
    assert await main.check_internet_connectivity() is True


async def test_connectivity_false_only_when_every_host_fails(monkeypatch):
    monkeypatch.setattr(
        main.aiohttp,
        "ClientSession",
        lambda **kw: _FakeSession(raise_exc=OSError("network down")),
    )
    assert await main.check_internet_connectivity() is False


async def test_connectivity_true_if_first_host_fails_but_a_later_one_works(monkeypatch):
    # First host blocked/slow, second succeeds — must still report connectivity.
    session = _FakeSession(outcomes=[OSError("blocked"), None, None])
    monkeypatch.setattr(main.aiohttp, "ClientSession", lambda **kw: session)
    assert await main.check_internet_connectivity() is True
    assert session.calls == 2  # stopped at the first success
