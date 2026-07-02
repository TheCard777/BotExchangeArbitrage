"""Tests for the async scanning path (bot/scanner.py)."""
from bot.scanner import ArbitrageScanner
from tests.conftest import FakeClient


def make_scanner(clients, pairs, threshold=0.0):
    return ArbitrageScanner({c.id: c for c in clients}, pairs, threshold)


async def test_fetch_all_tickers_collects_prices():
    a = FakeClient("a", prices={"BTC/USDT": 100.0, "ETH/USDT": 5.0})
    b = FakeClient("b", prices={"BTC/USDT": 101.0, "ETH/USDT": 5.1})
    scanner = make_scanner([a, b], ["BTC/USDT", "ETH/USDT"])
    tickers = await scanner._fetch_all_tickers()
    assert tickers == {
        "a": {"BTC/USDT": 100.0, "ETH/USDT": 5.0},
        "b": {"BTC/USDT": 101.0, "ETH/USDT": 5.1},
    }


async def test_fetch_skips_failing_pair_but_keeps_others():
    # 'a' has a price for BTC only; ETH raises KeyError and must be skipped.
    a = FakeClient("a", prices={"BTC/USDT": 100.0})
    b = FakeClient("b", prices={"BTC/USDT": 101.0, "ETH/USDT": 5.1})
    scanner = make_scanner([a, b], ["BTC/USDT", "ETH/USDT"])
    tickers = await scanner._fetch_all_tickers()
    assert tickers["a"] == {"BTC/USDT": 100.0}
    assert tickers["b"] == {"BTC/USDT": 101.0, "ETH/USDT": 5.1}


async def test_fetch_drops_none_and_non_positive_prices():
    a = FakeClient("a", prices={"BTC/USDT": None, "ETH/USDT": 0})
    b = FakeClient("b", prices={"BTC/USDT": 101.0})
    scanner = make_scanner([a, b], ["BTC/USDT", "ETH/USDT"])
    tickers = await scanner._fetch_all_tickers()
    # None and 0 are poison for profit math, so they must not appear.
    assert tickers["a"] == {}
    assert tickers["b"] == {"BTC/USDT": 101.0}


async def test_fetch_survives_exchange_wide_failure():
    a = FakeClient("a", ticker_error=ConnectionError("down"))
    b = FakeClient("b", prices={"BTC/USDT": 101.0})
    scanner = make_scanner([a, b], ["BTC/USDT"])
    tickers = await scanner._fetch_all_tickers()
    assert tickers["a"] == {}
    assert tickers["b"] == {"BTC/USDT": 101.0}


async def test_fee_table_uses_client_fees_with_default():
    a = FakeClient("a", fees={"BTC/USDT": 0.002})
    b = FakeClient("b")  # falls back to 0.001 default
    scanner = make_scanner([a, b], ["BTC/USDT"])
    fees = scanner._fee_table()
    assert fees["a"]["BTC/USDT"] == 0.002
    assert fees["b"]["BTC/USDT"] == 0.001


async def test_scan_end_to_end_finds_profitable_spread():
    a = FakeClient("a", prices={"BTC/USDT": 100.0}, fees={"BTC/USDT": 0.0})
    b = FakeClient("b", prices={"BTC/USDT": 105.0}, fees={"BTC/USDT": 0.0})
    scanner = make_scanner([a, b], ["BTC/USDT"], threshold=0.005)
    opportunities = await scanner.scan()
    assert len(opportunities) == 1
    opp = opportunities[0]
    assert opp.buy_exchange == "a"
    assert opp.sell_exchange == "b"
    assert opp.net_profit_fraction > 0.005


async def test_scan_returns_empty_when_no_spread():
    a = FakeClient("a", prices={"BTC/USDT": 100.0})
    b = FakeClient("b", prices={"BTC/USDT": 100.0})
    scanner = make_scanner([a, b], ["BTC/USDT"], threshold=0.005)
    assert await scanner.scan() == []


async def test_scan_summary_reports_best_spread_even_below_threshold():
    # Spread is real but below the 0.5% threshold: nothing returned, yet the
    # heartbeat summary should still report the best spread it saw.
    a = FakeClient("a", prices={"BTC/USDT": 100.0}, fees={"BTC/USDT": 0.0})
    b = FakeClient("b", prices={"BTC/USDT": 100.1}, fees={"BTC/USDT": 0.0})
    scanner = make_scanner([a, b], ["BTC/USDT"], threshold=0.005)
    opportunities = await scanner.scan()
    assert opportunities == []
    summary = scanner.last_scan_summary
    assert summary["exchanges"] == 2
    assert summary["best"] is not None
    assert summary["best"].buy_exchange == "a" and summary["best"].sell_exchange == "b"
    assert 0 < summary["best"].net_profit_fraction < 0.005


async def test_scan_summary_best_is_none_when_no_prices():
    a = FakeClient("a", ticker_error=ConnectionError("down"))
    b = FakeClient("b", ticker_error=ConnectionError("down"))
    scanner = make_scanner([a, b], ["BTC/USDT"], threshold=0.005)
    assert await scanner.scan() == []
    assert scanner.last_scan_summary["best"] is None
