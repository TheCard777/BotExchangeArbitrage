"""Tests for the real-time WebSocket price feed (bot/price_feed.py)."""
import asyncio

from bot.price_feed import RealtimePriceFeed


class FakeWSClient:
    """Minimal stand-in for a ccxt.pro exchange used by the feed."""

    def __init__(self, exchange_id, price, fail_times=0, tick_delay=0.005):
        self.id = exchange_id
        self._price = price
        self._fail_times = fail_times
        self._tick_delay = tick_delay
        self.calls = 0

    async def watch_ticker(self, symbol):
        self.calls += 1
        if self.calls <= self._fail_times:
            raise ConnectionError("stream dropped")
        await asyncio.sleep(self._tick_delay)
        return {"last": self._price}


async def _run_briefly(feed, seconds=0.06):
    feed.start()
    try:
        await asyncio.sleep(seconds)
        return feed.snapshot()
    finally:
        await feed.stop()


async def test_feed_populates_cache_from_stream():
    a = FakeWSClient("a", 100.0)
    b = FakeWSClient("b", 101.5)
    feed = RealtimePriceFeed({"a": a, "b": b}, ["BTC/USDT"])
    snapshot = await _run_briefly(feed)
    assert snapshot["a"]["BTC/USDT"] == 100.0
    assert snapshot["b"]["BTC/USDT"] == 101.5


async def test_feed_reconnects_after_stream_error():
    # Fails twice, then streams fine — the price must still show up.
    flaky = FakeWSClient("flaky", 200.0, fail_times=2)
    steady = FakeWSClient("steady", 199.0)
    feed = RealtimePriceFeed({"flaky": flaky, "steady": steady}, ["BTC/USDT"], reconnect_delay=0.01)
    snapshot = await _run_briefly(feed, seconds=0.1)
    assert snapshot["flaky"]["BTC/USDT"] == 200.0
    assert flaky.calls >= 3  # it retried past the failures


async def test_snapshot_excludes_exchanges_with_no_price_yet():
    good = FakeWSClient("good", 100.0)
    # 'never' keeps failing, so it never has a price.
    never = FakeWSClient("never", 0.0, fail_times=10_000)
    feed = RealtimePriceFeed({"good": good, "never": never}, ["BTC/USDT"], reconnect_delay=0.01)
    snapshot = await _run_briefly(feed)
    assert "good" in snapshot
    assert "never" not in snapshot  # no price → excluded


async def test_stop_cancels_all_tasks():
    a = FakeWSClient("a", 100.0)
    feed = RealtimePriceFeed({"a": a}, ["BTC/USDT", "ETH/USDT"])
    feed.start()
    await asyncio.sleep(0.02)
    await feed.stop()
    assert all(t.done() for t in feed._tasks) or feed._tasks == []


async def test_ignores_non_positive_prices():
    zero = FakeWSClient("zero", 0.0)
    feed = RealtimePriceFeed({"zero": zero}, ["BTC/USDT"])
    snapshot = await _run_briefly(feed)
    # price 0 is never stored, so the exchange stays out of the snapshot
    assert "zero" not in snapshot
