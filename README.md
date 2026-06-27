# Crypto Arbitrage Bot

Scans configured exchanges for inter-exchange arbitrage opportunities on a
set of trading pairs, and (optionally) executes them automatically.

## ⚠️ Read before running with real money

- This bot can place **real market orders with real funds** when
  `dry_run: false`. Market orders can fill at worse prices than expected,
  exchange APIs can fail mid-sequence, and the buy leg can fill while the
  sell leg fails, leaving you with an unhedged position.
- Inter-exchange arbitrage requires balances **already sitting on both
  exchanges** (quote currency on the buy side, base currency on the sell
  side) — there's no time to transfer crypto between exchanges before the
  price gap disappears.
- Start with `dry_run: true` and small `max_trade_size_quote` values. Watch
  the logs for at least a few days before considering live trading.
- You are solely responsible for any funds you trade with this bot.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your real API keys
```

Edit `config.yaml`:

- `exchanges`: ccxt exchange ids to compare (must match `.env` key prefixes)
- `pairs`: trading pairs to watch, ccxt symbol format (e.g. `BTC/USDT`)
- `min_profit_threshold`: minimum net profit (after both exchanges' taker
  fees) required to act, as a fraction (`0.005` = 0.5%)
- `max_trade_size_quote`: cap on quote-currency size per trade
- `dry_run`: keep `true` until you've validated behavior in the logs

API keys only need **trading** permissions — never enable withdrawal
permissions on keys used by this bot.

## Run

```bash
python main.py
```

Logs are written to stdout and to the file configured under `logging.file`
(default `logs/arbitrage.log`).

## Tests

```bash
pytest
```

Tests cover the profit/fee math and opportunity filtering only — they don't
hit any exchange API.

## How it works

1. `bot/scanner.py` polls the last price for each configured pair on every
   exchange and computes the net profit (after taker fees) of buying on one
   exchange and selling on another.
2. Opportunities above `min_profit_threshold` are passed to
   `bot/executor.py`.
3. In `dry_run` mode the executor only logs what it *would* do. In live
   mode it: checks available balances, re-checks prices for slippage versus
   `max_slippage`, then places a market buy on the cheap exchange and a
   market sell on the expensive one.

## Limitations / not handled

- No order book depth analysis — uses last trade price, so real fills may
  differ from the scanned price (mitigated by the slippage check, not
  eliminated).
- No automatic rebalancing of funds between exchanges.
- No persistence/state across restarts (no open-position tracking beyond
  what each exchange reports).
