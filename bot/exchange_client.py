"""Thin async wrapper around ccxt exchanges used by the bot."""
from __future__ import annotations

import ccxt.async_support as ccxt

from bot.config import Config


class ExchangeClient:
    def __init__(self, exchange_id: str, config: Config):
        self.id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        creds = config.credentials_for(exchange_id) if not config.dry_run else config.api_keys.get(exchange_id, {})
        self.exchange = exchange_class(
            {
                "apiKey": creds.get("apiKey", ""),
                "secret": creds.get("secret", ""),
                "enableRateLimit": True,
            }
        )

    async def load_markets(self):
        return await self.exchange.load_markets()

    def taker_fee(self, symbol: str) -> float:
        market = self.exchange.markets.get(symbol, {})
        return market.get("taker", 0.001)

    async def fetch_ticker(self, symbol: str):
        return await self.exchange.fetch_ticker(symbol)

    async def fetch_balance(self):
        return await self.exchange.fetch_balance()

    async def create_market_order(self, symbol: str, side: str, amount: float):
        return await self.exchange.create_order(symbol, "market", side, amount)

    async def close(self):
        await self.exchange.close()
