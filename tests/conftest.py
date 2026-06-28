"""Shared test doubles for the async parts of the bot.

FakeClient mimics the slice of ExchangeClient that the scanner and executor
actually use, so we can test their logic without touching a real exchange.
"""
from __future__ import annotations


class FakeClient:
    def __init__(
        self,
        exchange_id: str,
        prices: dict[str, float] | None = None,
        fees: dict[str, float] | None = None,
        balance: dict | None = None,
        load_error: Exception | None = None,
        ticker_error: Exception | None = None,
        order_error: Exception | None = None,
    ):
        self.id = exchange_id
        self._prices = prices or {}
        self._fees = fees or {}
        self._balance = balance or {}
        self._load_error = load_error
        self._ticker_error = ticker_error
        self._order_error = order_error
        self.closed = False
        self.orders: list[tuple] = []
        self.load_attempts = 0

    async def load_markets(self):
        self.load_attempts += 1
        if self._load_error is not None:
            raise self._load_error
        return {}

    def taker_fee(self, symbol: str) -> float:
        return self._fees.get(symbol, 0.001)

    async def fetch_ticker(self, symbol: str):
        if self._ticker_error is not None:
            raise self._ticker_error
        if symbol not in self._prices:
            raise KeyError(symbol)
        return {"last": self._prices[symbol]}

    async def fetch_balance(self):
        return self._balance

    async def create_market_order(self, symbol: str, side: str, amount: float):
        if self._order_error is not None:
            raise self._order_error
        self.orders.append((symbol, side, amount))
        return {"id": f"{self.id}-{side}-{len(self.orders)}"}

    async def close(self):
        self.closed = True


class FlakyClient(FakeClient):
    """Fails load_markets() for the first `fail_times` calls, then succeeds."""

    def __init__(self, exchange_id: str, fail_times: int, **kwargs):
        super().__init__(exchange_id, **kwargs)
        self._fail_times = fail_times

    async def load_markets(self):
        self.load_attempts += 1
        if self.load_attempts <= self._fail_times:
            raise ConnectionError(f"{self.id} not reachable yet")
        return {}
