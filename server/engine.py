"""Runs one bot instance per user, server-side.

Each user gets a UserBotEngine: it builds ExchangeClients from that user's
(decrypted) keys, connects, and scans for opportunities on a loop, keeping the
latest results in memory for the API to read. REST scanning (not WebSocket) to
keep many concurrent users simple and robust. Dry-run unless the user explicitly
enabled real trading in their config.
"""
from __future__ import annotations

import asyncio
import dataclasses

from bot.config import Config, LoggingConfig
from bot.dns_fallback import install as install_dns_fallback
from bot.exchange_client import ExchangeClient
from bot.scanner import ArbitrageScanner


def build_config(store, user_id: int) -> Config:
    """Assemble a bot Config from the user's stored keys + preferences."""
    keys = store.decrypted_keys(user_id)
    prefs = store.get_config(user_id)
    return Config(
        dry_run=bool(prefs["dry_run"]),
        scan_interval_seconds=10,
        exchanges=list(keys.keys()),
        pairs=list(prefs["pairs"]),
        min_profit_threshold=float(prefs["min_profit_threshold"]),
        max_trade_size_quote=float(prefs["max_trade_size_quote"]),
        max_balance_fraction_per_trade=0.5,
        max_slippage=0.002,
        logging=LoggingConfig(),
        realtime=False,
        top_movers=int(prefs["top_movers"]),
        api_keys=keys,
    )


async def _default_build_scanner(config: Config):
    install_dns_fallback()
    clients = {eid: ExchangeClient(eid, config) for eid in config.exchanges}
    scanner = ArbitrageScanner(clients, config.pairs, config.min_profit_threshold)
    # Best-effort connect: load markets on each, drop the ones that fail.
    results = await asyncio.gather(
        *(c.load_markets() for c in clients.values()), return_exceptions=True
    )
    for exchange_id, result in zip(list(clients.keys()), results):
        if isinstance(result, Exception):
            await scanner.clients[exchange_id].close()
            del scanner.clients[exchange_id]
    if len(scanner.clients) < 2:
        raise RuntimeError("Moins de 2 exchanges connectes — ajoute des cles API valides.")
    return scanner


def _opportunity_to_dict(opp) -> dict:
    return dataclasses.asdict(opp)


class UserBotEngine:
    def __init__(self, config: Config, build_scanner=None, scan_interval: float = 10.0):
        self.config = config
        self._build_scanner = build_scanner or _default_build_scanner
        self.scan_interval = scan_interval
        self.status = "stopped"
        self.error: str | None = None
        self.opportunities: list[dict] = []
        self.summary: dict = {}
        self._scanner = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        self.status = "connecting"
        self.error = None
        try:
            self._scanner = await self._build_scanner(self.config)
        except Exception as e:  # noqa: BLE001 — surface any connect failure to the user
            self.status = "error"
            self.error = str(e)
            return
        self.status = "running"
        try:
            while not self._stop.is_set():
                try:
                    opps = await self._scanner.scan()
                    self.opportunities = [_opportunity_to_dict(o) for o in opps]
                    best = self._scanner.last_scan_summary.get("best")
                    self.summary = {
                        "exchanges": self._scanner.last_scan_summary.get("exchanges", 0),
                        "best": _opportunity_to_dict(best) if best else None,
                    }
                    self.error = None
                except Exception as e:  # noqa: BLE001 — keep scanning next cycle
                    self.error = str(e)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.scan_interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            await self._close()
            self.status = "stopped"

    async def _close(self) -> None:
        if self._scanner:
            await asyncio.gather(
                *(c.close() for c in self._scanner.clients.values()), return_exceptions=True
            )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    def snapshot(self) -> dict:
        return {
            "status": self.status,
            "error": self.error,
            "dry_run": self.config.dry_run,
            "exchanges": list(self.config.exchanges),
            "opportunities": self.opportunities,
            "summary": self.summary,
        }


class BotManager:
    """Owns the running engines, one per user."""

    def __init__(self, store, engine_factory=None):
        self.store = store
        self._engines: dict[int, UserBotEngine] = {}
        self._engine_factory = engine_factory  # tests inject a fake

    async def start(self, user_id: int) -> UserBotEngine:
        engine = self._engines.get(user_id)
        if engine and engine.status in ("running", "connecting"):
            return engine
        config = build_config(self.store, user_id)
        engine = (self._engine_factory or UserBotEngine)(config)
        self._engines[user_id] = engine
        await engine.start()
        return engine

    async def stop(self, user_id: int) -> None:
        engine = self._engines.get(user_id)
        if engine:
            await engine.stop()

    def snapshot(self, user_id: int) -> dict:
        engine = self._engines.get(user_id)
        if not engine:
            return {"status": "stopped", "error": None, "opportunities": [], "summary": {}}
        return engine.snapshot()

    async def shutdown(self) -> None:
        for engine in list(self._engines.values()):
            await engine.stop()
