"""Entrypoint: scan configured exchanges/pairs for arbitrage and act on them."""
from __future__ import annotations

import asyncio
import logging
import signal

from bot.config import load_config
from bot.exchange_client import ExchangeClient
from bot.executor import TradeAborted, TradeExecutor
from bot.logger import setup_logging
from bot.scanner import ArbitrageScanner

logger = logging.getLogger("arbitrage.main")


async def run() -> None:
    config = load_config()
    setup_logging(config.logging)

    if config.dry_run:
        logger.info("Starting in DRY RUN mode — no real orders will be placed.")
    else:
        logger.warning("Starting in LIVE mode — real orders will be placed with real funds.")

    clients = {eid: ExchangeClient(eid, config) for eid in config.exchanges}
    scanner = ArbitrageScanner(clients, config.pairs, config.min_profit_threshold)
    executor = TradeExecutor(clients, config)

    await scanner.load_markets()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        while not stop_event.is_set():
            try:
                opportunities = await scanner.scan()
            except Exception:
                logger.exception("Scan failed, retrying next cycle")
                opportunities = []

            for opportunity in opportunities:
                try:
                    await executor.execute(opportunity)
                except TradeAborted as e:
                    logger.warning("Trade aborted: %s", e)
                except Exception:
                    logger.exception("Unexpected error executing opportunity")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=config.scan_interval_seconds)
            except asyncio.TimeoutError:
                pass
    finally:
        await asyncio.gather(*(client.close() for client in clients.values()))


if __name__ == "__main__":
    asyncio.run(run())
