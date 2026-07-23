"""Entrypoint: scan configured exchanges/pairs for arbitrage and act on them."""
from __future__ import annotations

import asyncio
import logging
import signal
import socket

import aiohttp

from bot import __version__
from bot.config import load_config
from bot.diagnostics import AUTH, GEOBLOCK, classify_error
from bot.dns_fallback import install as install_dns_fallback
from bot.exchange_client import ExchangeClient
from bot.executor import TradeAborted, TradeExecutor
from bot.logger import setup_logging
from bot.price_feed import RealtimePriceFeed
from bot.scanner import ArbitrageScanner

logger = logging.getLogger("arbitrage.main")

# How often the automatic top-movers mode re-picks the most volatile pairs.
TOP_MOVERS_REFRESH_SECONDS = 900  # 15 minutes


# A few independent, highly-reliable endpoints. We try several so one blocked
# or slow host (some networks block specific domains) can't produce a false
# "no internet" verdict — reaching ANY of them proves the path works.
CONNECTIVITY_CHECK_URLS = (
    "https://www.cloudflare.com/cdn-cgi/trace",
    "https://www.google.com/generate_204",
    "https://www.gstatic.com/generate_204",
)


async def check_internet_connectivity(per_host_timeout: float = 6) -> bool:
    """Quick, exchange-independent reachability check used to tell apart
    'no internet at all' from 'internet works but exchanges don't' when
    every configured exchange fails to connect. Returns True if ANY of a
    handful of reliable hosts answers — receiving any HTTP response (even an
    error status) proves the network path works; only exceptions on every
    host (timeout, DNS failure, connection refused) mean no connectivity.
    """
    timeout = aiohttp.ClientTimeout(total=per_host_timeout)
    try:
        # trust_env=True so a system/env proxy is used, matching the browser.
        async with aiohttp.ClientSession(trust_env=True) as session:
            for url in CONNECTIVITY_CHECK_URLS:
                try:
                    async with session.get(url, timeout=timeout):
                        return True
                except Exception:
                    continue
            return False
    except Exception:
        return False


async def select_top_movers(clients: dict, pairs: list[str], count: int) -> list[str]:
    """Keep the `count` most volatile pairs (largest absolute 24h price change).
    Volatile pairs are where the widest cross-exchange spreads tend to appear.

    Only pairs available on at least TWO connected exchanges are eligible —
    a pair listed on a single exchange can never produce an arbitrage
    opportunity, so watching it would be pointless. Falls back to all pairs if
    nothing qualifies (e.g. no 24h data)."""
    async def probe(exchange_id: str, client, pair: str):
        try:
            ticker = await client.fetch_ticker(pair)
            pct = (ticker or {}).get("percentage")
            volatility = abs(float(pct)) if pct is not None else 0.0
            return pair, True, volatility
        except Exception:
            return pair, False, 0.0

    results = await asyncio.gather(
        *(probe(eid, c, p) for eid, c in clients.items() for p in pairs),
        return_exceptions=True,
    )
    available: dict[str, int] = {}   # pair -> number of exchanges that list it
    volatility: dict[str, float] = {}  # pair -> max abs 24h change
    for item in results:
        if isinstance(item, Exception):
            continue
        pair, listed, vol = item
        if listed:
            available[pair] = available.get(pair, 0) + 1
            volatility[pair] = max(volatility.get(pair, 0.0), vol)

    tradeable = [p for p in pairs if available.get(p, 0) >= 2]
    if not tradeable:
        return pairs  # nothing comparable across exchanges — keep the universe
    tradeable.sort(key=lambda p: volatility.get(p, 0.0), reverse=True)
    return tradeable[:count]


async def connect_with_retries(
    scanner: ArbitrageScanner,
    attempts: int = 5,
    delay_seconds: float = 5,
    timeout_seconds: float = 45,
) -> None:
    """Connect to every configured exchange, retrying only the ones still
    failing on each attempt. An exchange that never connects is dropped
    instead of blocking the others — one flaky/unreachable exchange
    shouldn't stop the bot from running on the rest. Each exchange has a hard
    timeout so a single stalled connection can't freeze startup, and progress
    is logged per exchange so a slow link looks like progress, not a freeze.
    """
    async def connect_one(exchange_id: str, client) -> None:
        await asyncio.wait_for(client.load_markets(), timeout=timeout_seconds)
        logger.info("Connecte a %s", exchange_id)

    remaining = dict(scanner.clients)
    for attempt in range(1, attempts + 1):
        logger.info(
            "Connexion aux exchanges en cours (%s) — essai %d/%d. Cela peut prendre "
            "jusqu'a %ds par exchange sur une connexion lente, patiente...",
            ", ".join(remaining),
            attempt,
            attempts,
            int(timeout_seconds),
        )
        results = await asyncio.gather(
            *(connect_one(exchange_id, client) for exchange_id, client in remaining.items()),
            return_exceptions=True,
        )
        failures = {
            exchange_id: result
            for exchange_id, result in zip(remaining.keys(), results)
            if isinstance(result, Exception)
        }
        if not failures:
            logger.info("Tous les exchanges sont connectes : %s", ", ".join(scanner.clients))
            return

        # Split failures: a bad API key or a geo-block won't fix itself on
        # retry, so drop those immediately with a clear message instead of
        # wasting five attempts on them.
        transient = {}
        for exchange_id, error in failures.items():
            category, reason = classify_error(error)
            if category in (AUTH, GEOBLOCK):
                logger.warning("%s ignore pour cette session — %s", exchange_id, reason)
                await scanner.clients[exchange_id].close()
                del scanner.clients[exchange_id]
            else:
                transient[exchange_id] = error

        if not transient:
            break

        if attempt == attempts:
            for exchange_id, error in transient.items():
                _, reason = classify_error(error)
                logger.warning(
                    "%s injoignable apres %d tentatives — %s (exchange ignore pour cette session)",
                    exchange_id,
                    attempts,
                    reason,
                )
                await scanner.clients[exchange_id].close()
                del scanner.clients[exchange_id]
            break

        logger.warning(
            "Connexion aux exchanges impossible (essai %d/%d) : %s — nouvelle tentative dans %ds",
            attempt,
            attempts,
            ", ".join(transient),
            delay_seconds,
        )
        remaining = {exchange_id: remaining[exchange_id] for exchange_id in transient}
        await asyncio.sleep(delay_seconds)

    if len(scanner.clients) < 2:
        raise RuntimeError("Pas assez d'exchanges connectes (minimum 2) pour comparer les prix.")

    logger.info(
        "Demarrage avec %d exchange(s) connecte(s) : %s",
        len(scanner.clients),
        ", ".join(scanner.clients),
    )


def _dns_self_test(host: str = "api.binance.com") -> str:
    """Resolve a known host via the OS resolver and return a short verdict, so
    the log shows whether DNS works at runtime (and which resolver is active)."""
    try:
        import aiohttp.connector as _connector

        resolver = _connector.DefaultResolver.__name__
    except Exception:
        resolver = "?"
    try:
        socket.getaddrinfo(host, 443)
        return f"resolveur={resolver}, test {host}=OK"
    except Exception as e:
        return f"resolveur={resolver}, test {host}=ECHEC ({type(e).__name__})"


async def run() -> None:
    # Make DNS resilient (OS resolver like curl + DoH fallback) before any
    # network call, so a broken/third-party DNS can't stop the bot.
    install_dns_fallback()

    config = load_config()
    setup_logging(config.logging)

    logger.info("Bot d'arbitrage version %s", __version__)
    logger.info("Diagnostic DNS : %s", _dns_self_test())

    if config.dry_run:
        logger.info("Demarrage en mode DEMONSTRATION — aucun ordre reel ne sera passe.")
    else:
        logger.warning("Demarrage en mode REEL — des ordres reels seront passes avec de l'argent reel.")

    clients = {eid: ExchangeClient(eid, config) for eid in config.exchanges}
    scanner = ArbitrageScanner(clients, config.pairs, config.min_profit_threshold)
    executor = TradeExecutor(clients, config)

    try:
        # Give each exchange a bit more than its own request timeout, so a
        # large market download on a slow link isn't cut off prematurely.
        await connect_with_retries(scanner, timeout_seconds=config.request_timeout_seconds + 20)
    except RuntimeError:
        if await check_internet_connectivity():
            raise RuntimeError(
                "Internet fonctionne sur cette machine, mais aucun exchange crypto n'est joignable "
                "depuis ce reseau (operateur/pare-feu qui bloque l'acces aux sites crypto, ou connexion "
                "trop lente). Essaie un autre reseau (Wi-Fi au lieu de 4G, ou inversement) ou un VPN."
            ) from None
        raise RuntimeError(
            "Aucune connexion internet detectee sur cette machine. Verifie ton Wi-Fi/4G "
            "(et coupe ton VPN si tu en as un), puis relance ./start.sh."
        ) from None

    # Top-movers mode: the full configured list is the "universe"; the bot
    # automatically focuses on the most volatile pairs from it, and re-picks
    # them periodically while running (see the loop below).
    universe = list(scanner.pairs)
    top_movers_on = bool(config.top_movers) and config.top_movers < len(universe)
    if top_movers_on:
        scanner.pairs = await select_top_movers(scanner.clients, universe, config.top_movers)
        logger.info(
            "Mode automatique top-movers — le bot suit les %d paires les plus volatiles : %s",
            len(scanner.pairs),
            ", ".join(scanner.pairs),
        )

    # Real-time mode: stream prices over WebSocket from the surviving exchanges
    # and scan the live cache fast. Falls back to REST polling if disabled.
    price_feed = None
    if config.realtime:
        price_feed = RealtimePriceFeed(scanner.clients, scanner.pairs)
        price_feed.start()
        scanner.price_feed = price_feed
        loop_interval = 1.0
    else:
        logger.info("Mode temps reel desactive — scan REST toutes les %ss.", config.scan_interval_seconds)
        loop_interval = config.scan_interval_seconds

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    heartbeat_every = 10.0  # seconds between heartbeat log lines
    last_heartbeat = 0.0
    last_movers_refresh = loop.time()

    try:
        while not stop_event.is_set():
            # Automatic top-movers refresh: periodically re-pick the most
            # volatile pairs from the universe and re-point the feed at them, so
            # the bot follows the market on its own without any manual change.
            if top_movers_on and loop.time() - last_movers_refresh >= TOP_MOVERS_REFRESH_SECONDS:
                last_movers_refresh = loop.time()
                new_pairs = await select_top_movers(scanner.clients, universe, config.top_movers)
                if set(new_pairs) != set(scanner.pairs):
                    logger.info("Top-movers reajustes automatiquement : %s", ", ".join(new_pairs))
                    scanner.pairs = new_pairs
                    if price_feed is not None:
                        await price_feed.stop()
                        price_feed = RealtimePriceFeed(scanner.clients, new_pairs)
                        price_feed.start()
                        scanner.price_feed = price_feed

            try:
                opportunities = await scanner.scan()
            except Exception:
                logger.exception("Echec du scan, nouvelle tentative au prochain cycle")
                opportunities = []

            # Heartbeat: show the bot is alive and the best spread it sees,
            # even when nothing beats the threshold (the normal case) — so an
            # idle-looking screen is clearly "working, no opportunity" not
            # "frozen". Throttled so fast real-time scanning doesn't spam.
            now = loop.time()
            summary = scanner.last_scan_summary
            best = summary.get("best")
            if now - last_heartbeat >= heartbeat_every:
                last_heartbeat = now
                if best is not None:
                    logger.info(
                        "Scan OK (%d exchanges) — meilleur ecart net : %+.3f%% sur %s (%s->%s) | seuil %.3f%% | %d opportunite(s) exploitable(s)",
                        summary.get("exchanges", 0),
                        best.net_profit_fraction * 100,
                        best.pair,
                        best.buy_exchange,
                        best.sell_exchange,
                        scanner.min_profit_threshold * 100,
                        len(opportunities),
                    )
                else:
                    logger.info("Scan OK — en attente de prix exploitables depuis les exchanges...")

            for opportunity in opportunities:
                try:
                    await executor.execute(opportunity)
                except TradeAborted as e:
                    logger.warning("Trade annule : %s", e)
                except Exception:
                    logger.exception("Erreur inattendue lors de l'execution d'une opportunite")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=loop_interval)
            except asyncio.TimeoutError:
                pass
    finally:
        if price_feed is not None:
            await price_feed.stop()
        # Close every client even if one close() fails — return_exceptions
        # keeps a single bad shutdown from leaking the other sessions.
        await asyncio.gather(
            *(client.close() for client in clients.values()),
            return_exceptions=True,
        )


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("Bot arrete.")
    except FileNotFoundError:
        print("Configuration introuvable. Lance d'abord : ./install.sh")
    except ValueError as e:
        print(f"Probleme de configuration : {e}")
        print("Relance ./install.sh pour corriger la configuration.")
    except Exception as e:
        print(f"Le bot n'a pas pu demarrer : {e}")
        print("Verifie ta connexion internet, puis relance ./start.sh.")
