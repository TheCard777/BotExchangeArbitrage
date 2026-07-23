"""Places real orders for a detected opportunity, with safety checks.

Assumes balances are pre-funded on each exchange (quote currency on the buy
side, base currency on the sell side) since moving crypto between exchanges
takes time the price gap won't survive.
"""
from __future__ import annotations

import logging

from bot.config import Config
from bot.exchange_client import ExchangeClient
from bot.scanner import Opportunity, net_profit_fraction

logger = logging.getLogger("arbitrage.executor")


class TradeAborted(Exception):
    pass


class TradeExecutor:
    def __init__(self, clients: dict[str, ExchangeClient], config: Config):
        self.clients = clients
        self.config = config

    async def execute(self, opportunity: Opportunity) -> None:
        if self.config.dry_run:
            logger.info(
                "[DRY RUN] %s: buy on %s @ %.6f, sell on %s @ %.6f, net profit %.3f%%",
                opportunity.pair,
                opportunity.buy_exchange,
                opportunity.buy_price,
                opportunity.sell_exchange,
                opportunity.sell_price,
                opportunity.net_profit_fraction * 100,
            )
            return

        base, quote = opportunity.pair.split("/")
        buy_client = self.clients[opportunity.buy_exchange]
        sell_client = self.clients[opportunity.sell_exchange]

        trade_size_quote = await self._size_trade(opportunity, base, quote, buy_client, sell_client)
        amount = trade_size_quote / opportunity.buy_price

        # Round to a quantity valid on BOTH exchanges (double-rounding gives a
        # value both accept), then check each exchange's minimums — so a real
        # order is never rejected for bad precision or being too small.
        amount = buy_client.amount_to_precision(opportunity.pair, amount)
        amount = sell_client.amount_to_precision(opportunity.pair, amount)
        self._check_order_minimums(opportunity, amount, buy_client, sell_client)

        await self._check_slippage(opportunity, buy_client, sell_client)

        logger.info(
            "Executing arbitrage: buy %.6f %s on %s, sell on %s (size %.2f %s)",
            amount,
            base,
            opportunity.buy_exchange,
            opportunity.sell_exchange,
            trade_size_quote,
            quote,
        )

        buy_order = await buy_client.create_market_order(opportunity.pair, "buy", amount)
        try:
            sell_order = await sell_client.create_market_order(opportunity.pair, "sell", amount)
        except Exception:
            logger.exception(
                "Sell leg failed after buy filled on %s — manual intervention required, position is unhedged",
                opportunity.buy_exchange,
            )
            raise

        logger.info("Buy order: %s", buy_order.get("id"))
        logger.info("Sell order: %s", sell_order.get("id"))

    async def _size_trade(
        self,
        opportunity: Opportunity,
        base: str,
        quote: str,
        buy_client: ExchangeClient,
        sell_client: ExchangeClient,
    ) -> float:
        buy_balance = await buy_client.fetch_balance()
        sell_balance = await sell_client.fetch_balance()

        quote_free = buy_balance.get(quote, {}).get("free", 0) or 0
        base_free = sell_balance.get(base, {}).get("free", 0) or 0
        base_free_in_quote = base_free * opportunity.sell_price

        available = min(quote_free, base_free_in_quote) * self.config.max_balance_fraction_per_trade
        trade_size_quote = min(self.config.max_trade_size_quote, available)

        if trade_size_quote <= 0:
            raise TradeAborted(
                f"Insufficient balance: {quote_free:.2f} {quote} on {opportunity.buy_exchange}, "
                f"{base_free:.6f} {base} on {opportunity.sell_exchange}"
            )
        return trade_size_quote

    def _check_order_minimums(
        self,
        opportunity: Opportunity,
        amount: float,
        buy_client: ExchangeClient,
        sell_client: ExchangeClient,
    ) -> None:
        if amount <= 0:
            raise TradeAborted(
                f"Montant nul pour {opportunity.pair} apres arrondi a la precision de l'exchange "
                "(trade trop petit)."
            )
        for client, price, name in (
            (buy_client, opportunity.buy_price, opportunity.buy_exchange),
            (sell_client, opportunity.sell_price, opportunity.sell_exchange),
        ):
            min_amount = client.min_amount(opportunity.pair)
            if min_amount and amount < min_amount:
                raise TradeAborted(
                    f"Montant {amount} sous le minimum {min_amount} sur {name} pour {opportunity.pair}."
                )
            min_cost = client.min_cost(opportunity.pair)
            if min_cost and amount * price < min_cost:
                raise TradeAborted(
                    f"Valeur du trade ({amount * price:.2f}) sous le minimum {min_cost} sur {name}."
                )

    async def _check_slippage(
        self, opportunity: Opportunity, buy_client: ExchangeClient, sell_client: ExchangeClient
    ) -> None:
        fresh_buy = await buy_client.fetch_ticker(opportunity.pair)
        fresh_sell = await sell_client.fetch_ticker(opportunity.pair)

        buy_last = (fresh_buy or {}).get("last")
        sell_last = (fresh_sell or {}).get("last")
        if not buy_last or not sell_last or buy_last <= 0 or sell_last <= 0:
            # Can't confirm a fresh price on both sides — abort rather than
            # trade blind with real money.
            raise TradeAborted(
                f"Prix frais indisponibles pour {opportunity.pair} — trade annule par securite."
            )

        fresh_profit = net_profit_fraction(
            buy_last,
            sell_last,
            buy_client.taker_fee(opportunity.pair),
            sell_client.taker_fee(opportunity.pair),
        )
        drift = opportunity.net_profit_fraction - fresh_profit
        if drift > self.config.max_slippage:
            raise TradeAborted(
                f"Slippage too high for {opportunity.pair}: scanned profit "
                f"{opportunity.net_profit_fraction:.4f}, now {fresh_profit:.4f}"
            )
