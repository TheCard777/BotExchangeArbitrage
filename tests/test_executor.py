"""Tests for the trade executor's safety checks (bot/executor.py)."""
import pytest

from bot.config import Config, LoggingConfig
from bot.executor import TradeAborted, TradeExecutor
from bot.scanner import Opportunity
from tests.conftest import FakeClient


def make_config(
    dry_run=False,
    max_trade_size_quote=100.0,
    max_balance_fraction_per_trade=1.0,
    max_slippage=0.002,
):
    return Config(
        dry_run=dry_run,
        scan_interval_seconds=10,
        exchanges=["a", "b"],
        pairs=["BTC/USDT"],
        min_profit_threshold=0.005,
        max_trade_size_quote=max_trade_size_quote,
        max_balance_fraction_per_trade=max_balance_fraction_per_trade,
        max_slippage=max_slippage,
        logging=LoggingConfig(),
        api_keys={},
    )


def make_opportunity(buy="a", sell="b", buy_price=100.0, sell_price=105.0, profit=0.04):
    return Opportunity(
        pair="BTC/USDT",
        buy_exchange=buy,
        sell_exchange=sell,
        buy_price=buy_price,
        sell_price=sell_price,
        net_profit_fraction=profit,
    )


async def test_dry_run_places_no_orders():
    buy = FakeClient("a", prices={"BTC/USDT": 100.0})
    sell = FakeClient("b", prices={"BTC/USDT": 105.0})
    executor = TradeExecutor({"a": buy, "b": sell}, make_config(dry_run=True))
    await executor.execute(make_opportunity())
    assert buy.orders == []
    assert sell.orders == []


async def test_executes_both_legs_when_funded():
    buy = FakeClient(
        "a",
        prices={"BTC/USDT": 100.0},
        balance={"USDT": {"free": 1000.0}},
    )
    sell = FakeClient(
        "b",
        prices={"BTC/USDT": 105.0},
        balance={"BTC": {"free": 10.0}},
    )
    executor = TradeExecutor({"a": buy, "b": sell}, make_config(max_trade_size_quote=50.0))
    await executor.execute(make_opportunity())
    # 50 USDT cap / 100 price = 0.5 BTC on each leg.
    assert buy.orders == [("BTC/USDT", "buy", 0.5)]
    assert sell.orders == [("BTC/USDT", "sell", 0.5)]


async def test_trade_size_capped_by_balance_fraction():
    buy = FakeClient("a", prices={"BTC/USDT": 100.0}, balance={"USDT": {"free": 100.0}})
    sell = FakeClient("b", prices={"BTC/USDT": 105.0}, balance={"BTC": {"free": 10.0}})
    config = make_config(max_trade_size_quote=1000.0, max_balance_fraction_per_trade=0.5)
    executor = TradeExecutor({"a": buy, "b": sell}, config)
    await executor.execute(make_opportunity())
    # min(100 USDT, 10*105 in quote) * 0.5 fraction = 50 quote / 100 price = 0.5 BTC
    assert buy.orders == [("BTC/USDT", "buy", 0.5)]


async def test_aborts_when_balance_is_zero():
    buy = FakeClient("a", prices={"BTC/USDT": 100.0}, balance={"USDT": {"free": 0.0}})
    sell = FakeClient("b", prices={"BTC/USDT": 105.0}, balance={"BTC": {"free": 0.0}})
    executor = TradeExecutor({"a": buy, "b": sell}, make_config())
    with pytest.raises(TradeAborted, match="Insufficient balance"):
        await executor.execute(make_opportunity())
    assert buy.orders == []


async def test_aborts_when_balance_keys_missing():
    # Exchange returns a balance dict without the relevant currencies.
    buy = FakeClient("a", prices={"BTC/USDT": 100.0}, balance={})
    sell = FakeClient("b", prices={"BTC/USDT": 105.0}, balance={})
    executor = TradeExecutor({"a": buy, "b": sell}, make_config())
    with pytest.raises(TradeAborted):
        await executor.execute(make_opportunity())


async def test_aborts_when_slippage_too_high():
    # Price has moved so the fresh profit is far below what was scanned.
    buy = FakeClient("a", prices={"BTC/USDT": 104.0}, balance={"USDT": {"free": 1000.0}})
    sell = FakeClient("b", prices={"BTC/USDT": 105.0}, balance={"BTC": {"free": 10.0}})
    executor = TradeExecutor({"a": buy, "b": sell}, make_config(max_slippage=0.002))
    # Scanned profit claimed 4%, but fresh prices barely have a spread.
    with pytest.raises(TradeAborted, match="Slippage"):
        await executor.execute(make_opportunity(profit=0.04))
    assert buy.orders == []
    assert sell.orders == []


async def test_sell_leg_failure_propagates_after_buy():
    buy = FakeClient("a", prices={"BTC/USDT": 100.0}, balance={"USDT": {"free": 1000.0}})
    sell = FakeClient(
        "b",
        prices={"BTC/USDT": 105.0},
        balance={"BTC": {"free": 10.0}},
        order_error=RuntimeError("exchange rejected order"),
    )
    executor = TradeExecutor({"a": buy, "b": sell}, make_config(max_trade_size_quote=50.0))
    with pytest.raises(RuntimeError, match="exchange rejected order"):
        await executor.execute(make_opportunity())
    # Buy leg did fill before the sell leg blew up — the warning path.
    assert buy.orders == [("BTC/USDT", "buy", 0.5)]
