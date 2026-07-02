"""Pure profit math plus the async loop that polls exchanges for prices."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

from bot.exchange_client import ExchangeClient


@dataclass
class Opportunity:
    pair: str
    buy_exchange: str
    sell_exchange: str
    buy_price: float
    sell_price: float
    net_profit_fraction: float


def net_profit_fraction(buy_price: float, sell_price: float, buy_fee: float, sell_fee: float) -> float:
    """Profit fraction of buying on one exchange and selling on another,
    net of both exchanges' taker fees. Does not account for withdrawal
    fees/time, since this bot assumes pre-funded balances on each exchange.
    """
    if buy_price <= 0:
        return 0.0
    cost = buy_price * (1 + buy_fee)
    proceeds = sell_price * (1 - sell_fee)
    return (proceeds - cost) / cost


def find_opportunities(
    tickers: dict[str, dict[str, float]],
    fees: dict[str, dict[str, float]],
    pairs: list[str],
    min_profit_threshold: float,
) -> list[Opportunity]:
    """tickers[exchange_id][pair] = last price. fees[exchange_id][pair] = taker fee fraction."""
    opportunities = []
    exchange_ids = list(tickers.keys())

    for pair in pairs:
        for buy_ex in exchange_ids:
            buy_price = tickers[buy_ex].get(pair)
            if buy_price is None:
                continue
            for sell_ex in exchange_ids:
                if buy_ex == sell_ex:
                    continue
                sell_price = tickers[sell_ex].get(pair)
                if sell_price is None:
                    continue

                profit = net_profit_fraction(
                    buy_price,
                    sell_price,
                    fees[buy_ex].get(pair, 0.001),
                    fees[sell_ex].get(pair, 0.001),
                )
                if profit >= min_profit_threshold:
                    opportunities.append(
                        Opportunity(
                            pair=pair,
                            buy_exchange=buy_ex,
                            sell_exchange=sell_ex,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            net_profit_fraction=profit,
                        )
                    )

    opportunities.sort(key=lambda o: o.net_profit_fraction, reverse=True)
    return opportunities


class ArbitrageScanner:
    def __init__(self, clients: dict[str, ExchangeClient], pairs: list[str], min_profit_threshold: float):
        self.clients = clients
        self.pairs = pairs
        self.min_profit_threshold = min_profit_threshold
        # Summary of the most recent scan, so the bot can show a heartbeat
        # (it's alive, and the best spread it saw) even when nothing beats the
        # profit threshold — which is the normal case most of the time.
        self.last_scan_summary: dict = {}

    async def load_markets(self):
        await asyncio.gather(*(client.load_markets() for client in self.clients.values()))

    async def _fetch_all_tickers(self) -> dict[str, dict[str, float]]:
        async def fetch_for_exchange(exchange_id: str, client: ExchangeClient):
            results = {}
            for pair in self.pairs:
                try:
                    ticker = await client.fetch_ticker(pair)
                    last = (ticker or {}).get("last")
                    # Only keep usable, strictly-positive prices: some
                    # exchanges return None/0 for an illiquid or unlisted
                    # pair, which would otherwise poison the profit math.
                    price = float(last)
                    if price > 0:
                        results[pair] = price
                except (TypeError, ValueError):
                    continue
                except Exception:
                    continue
            return exchange_id, results

        results = await asyncio.gather(
            *(fetch_for_exchange(eid, c) for eid, c in self.clients.items()),
            return_exceptions=True,
        )
        return {
            exchange_id: prices
            for item in results
            if not isinstance(item, Exception)
            for exchange_id, prices in [item]
        }

    def _fee_table(self) -> dict[str, dict[str, float]]:
        return {
            exchange_id: {pair: client.taker_fee(pair) for pair in self.pairs}
            for exchange_id, client in self.clients.items()
        }

    async def scan(self) -> list[Opportunity]:
        tickers = await self._fetch_all_tickers()
        fees = self._fee_table()
        # Compute every spread (unfiltered) once, so we can both return the
        # profitable ones and report the best one seen for the heartbeat.
        all_spreads = find_opportunities(tickers, fees, self.pairs, float("-inf"))
        priced_pairs = {pair for prices in tickers.values() for pair in prices}
        self.last_scan_summary = {
            "exchanges": len(tickers),
            "pairs_priced": len(priced_pairs),
            "best": all_spreads[0] if all_spreads else None,
        }
        return [o for o in all_spreads if o.net_profit_fraction >= self.min_profit_threshold]
