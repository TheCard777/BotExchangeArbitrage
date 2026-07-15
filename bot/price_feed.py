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

    def start(self) -> None:
        """Launch one background streaming task per (exchange, pair)."""
        for exchange_id, client in self.clients.items():
            for pair in self.pairs:
                self._tasks.append(
                    asyncio.create_task(self._watch(exchange_id, client, pair))
                )
        logger.info(
            "Flux temps reel (WebSocket) demarre : %d exchange(s) x %d paire(s).",
            len(self.clients),
            len(self.pairs),
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
