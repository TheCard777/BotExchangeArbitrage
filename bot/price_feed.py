"""Real-time price feed over WebSocket (ccxt.pro).

Instead of polling each exchange every few seconds (REST), this keeps a live
WebSocket subscription per (exchange, pair) and updates an in-memory price
cache on every tick. The scanner then reads that cache with zero network cost.

Design goals:
- Resilient: if a stream drops (common on a flaky connection), the task logs
  it and reconnects automatically, without taking down the others.
- Non-blocking: one background task per (exchange, pair); a slow or dead
  exchange only affects its own prices.
- Safe shutdown: stop() cancels every task and waits for them to finish.
"""
from __future__ import annotations

import asyncio
import logging

from bot.diagnostics import classify_error

logger = logging.getLogger("arbitrage.feed")


class RealtimePriceFeed:
    def __init__(self, clients: dict, pairs: list[str], reconnect_delay: float = 2.0):
        self.clients = clients
        self.pairs = pairs
        self.reconnect_delay = reconnect_delay
        self.prices: dict[str, dict[str, float]] = {eid: {} for eid in clients}
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    async def _watch(self, exchange_id: str, client, pair: str) -> None:
        while not self._stop.is_set():
            try:
                ticker = await client.watch_ticker(pair)
                last = (ticker or {}).get("last")
                if last is not None:
                    price = float(last)
                    if price > 0:
                        self.prices[exchange_id][pair] = price
            except asyncio.CancelledError:
                raise
            except (TypeError, ValueError):
                continue
            except Exception as error:  # noqa: BLE001 — reconnect on any stream error
                # A pair the exchange simply doesn't list will never recover, so
                # stop instead of reconnecting forever (which spams the log).
                text = f"{type(error).__name__}: {error}".lower()
                if "badsymbol" in text or "does not have market" in text:
                    logger.info("%s ne propose pas %s — paire ignoree.", exchange_id, pair)
                    self.prices[exchange_id].pop(pair, None)
                    return
                _, reason = classify_error(error)
                logger.warning(
                    "Flux temps reel %s %s interrompu — %s. Reconnexion dans %.0fs...",
                    exchange_id,
                    pair,
                    reason,
                    self.reconnect_delay,
                )
                # Drop the stale price so we don't act on an old value.
                self.prices[exchange_id].pop(pair, None)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.reconnect_delay)
                except asyncio.TimeoutError:
                    pass

    @staticmethod
    def _client_has_pair(client, pair: str) -> bool:
        # Skip (exchange, pair) combos the exchange doesn't list, so we never
        # open a doomed stream. Fakes without has_market are always watched.
        has_market = getattr(client, "has_market", None)
        return has_market(pair) if callable(has_market) else True

    def start(self) -> None:
        """Launch one background streaming task per (exchange, pair) that the
        exchange actually lists."""
        watched = 0
        for exchange_id, client in self.clients.items():
            for pair in self.pairs:
                if not self._client_has_pair(client, pair):
                    continue
                watched += 1
                self._tasks.append(
                    asyncio.create_task(self._watch(exchange_id, client, pair))
                )
        logger.info(
            "Flux temps reel (WebSocket) demarre : %d abonnement(s) sur %d exchange(s).",
            watched,
            len(self.clients),
        )

    def snapshot(self) -> dict[str, dict[str, float]]:
        """Return a copy of the latest prices, excluding exchanges with none yet."""
        return {eid: dict(prices) for eid, prices in self.prices.items() if prices}

    async def stop(self) -> None:
        self._stop.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
