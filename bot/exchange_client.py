"""Thin async wrapper around ccxt exchanges used by the bot."""
from __future__ import annotations

import logging

# ccxt.pro is a superset of ccxt.async_support: same REST methods, plus
# WebSocket streaming (watch_ticker) for real-time prices.
import ccxt.pro as ccxt

from bot.config import Config
from bot.diagnostics import BLOCKED, NETWORK, TIMEOUT, classify_error

logger = logging.getLogger("arbitrage.exchange")

# Some exchanges publish a mirror domain for networks/regions where their main
# API host is blocked. Bybit's api.bytick.com is the documented alternate for
# api.bybit.com. We fall back to it automatically when the main host is
# unreachable, so a blocked main domain doesn't cost the user the exchange.
ALTERNATE_HOSTNAMES = {"bybit": "bytick.com"}
# Failure categories where trying the alternate domain makes sense.
_FALLBACK_CATEGORIES = {NETWORK, BLOCKED, TIMEOUT}


class ExchangeClient:
    def __init__(self, exchange_id: str, config: Config):
        self.id = exchange_id
        exchange_class = getattr(ccxt, exchange_id)
        creds = config.credentials_for(exchange_id) if not config.dry_run else config.api_keys.get(exchange_id, {})
        params = {
            "apiKey": creds.get("apiKey", ""),
            "secret": creds.get("secret", ""),
            "enableRateLimit": True,
            # ccxt's 10s default is too tight on slow/high-latency
            # connections, where it's the main cause of false
            # "can't connect" failures (the request is in flight,
            # just slow — not actually blocked).
            "timeout": int(config.request_timeout_seconds * 1000),
            # Honour the system/env proxy (HTTP_PROXY/HTTPS_PROXY) like a
            # browser does. On networks where internet is only reachable
            # through a proxy/tunnel, this is what lets the bot connect
            # at all instead of failing with DNS/connection errors.
            "aiohttp_trust_env": True,
        }
        # KuCoin/OKX also need an API passphrase; pass it only when present.
        password = creds.get("password", "")
        if password:
            params["password"] = password
        self._exchange_class = exchange_class
        self._params = params
        self._alt_hostname = ALTERNATE_HOSTNAMES.get(exchange_id)
        self._tried_alt = False
        self.exchange = exchange_class(params)

    async def _switch_to_alternate_domain(self) -> None:
        self._tried_alt = True
        logger.warning(
            "%s injoignable sur son domaine principal — bascule sur le domaine "
            "alternatif api.%s...",
            self.id,
            self._alt_hostname,
        )
        try:
            await self.exchange.close(clean_instance_data=True)
        except Exception:
            pass
        params = dict(self._params)
        params["hostname"] = self._alt_hostname
        self.exchange = self._exchange_class(params)

    async def load_markets(self):
        try:
            return await self.exchange.load_markets()
        except Exception as error:  # noqa: BLE001 — inspect then re-raise
            category, _ = classify_error(error)
            if self._alt_hostname and not self._tried_alt and category in _FALLBACK_CATEGORIES:
                await self._switch_to_alternate_domain()
                return await self.exchange.load_markets()
            raise

    def has_market(self, symbol: str) -> bool:
        """True if this exchange lists the pair. Falls back to True when markets
        aren't loaded yet, so we never wrongly hide a pair before connecting."""
        markets = getattr(self.exchange, "markets", None)
        if not markets:
            return True
        return symbol in markets

    def taker_fee(self, symbol: str) -> float:
        market = self.exchange.markets.get(symbol, {})
        return market.get("taker", 0.001)

    def amount_to_precision(self, symbol: str, amount: float) -> float:
        """Round an order quantity to this exchange's allowed precision so the
        order isn't rejected for having too many decimals. Safe fallback to the
        raw amount if precision info isn't available."""
        try:
            return float(self.exchange.amount_to_precision(symbol, amount))
        except Exception:
            return float(amount)

    def _limit(self, symbol: str, kind: str) -> float | None:
        market = self.exchange.markets.get(symbol, {}) or {}
        limits = market.get("limits", {}) or {}
        return (limits.get(kind, {}) or {}).get("min")

    def min_amount(self, symbol: str) -> float | None:
        """Smallest order quantity the exchange accepts for this pair (or None)."""
        return self._limit(symbol, "amount")

    def min_cost(self, symbol: str) -> float | None:
        """Smallest order value (amount x price) the exchange accepts (or None)."""
        return self._limit(symbol, "cost")

    async def fetch_ticker(self, symbol: str):
        return await self.exchange.fetch_ticker(symbol)

    @property
    def supports_websocket(self) -> bool:
        return bool(self.exchange.has.get("watchTicker"))

    async def watch_ticker(self, symbol: str):
        """Wait for the next real-time ticker update over WebSocket."""
        return await self.exchange.watch_ticker(symbol)

    async def fetch_balance(self):
        return await self.exchange.fetch_balance()

    async def create_market_order(self, symbol: str, side: str, amount: float):
        return await self.exchange.create_order(symbol, "market", side, amount)

    async def close(self):
        # ccxt only releases the underlying aiohttp session/connector when
        # clean_instance_data=True; without it, close() is a no-op for REST
        # and leaves "Unclosed client session" warnings on exit.
        await self.exchange.close(clean_instance_data=True)
