"""Entrypoint: scan configured exchanges/pairs for arbitrage and act on them."""
from __future__ import annotations

import asyncio
import logging
import signal
import socket

import aiohttp

from bot import __version__
from bot.config import load_config
from bot.diagnostics import classify_error
from bot.dns_fallback import install as install_dns_fallback
from bot.exchange_client import ExchangeClient
from bot.executor import TradeAborted, TradeExecutor
from bot.logger import setup_logging
from bot.scanner import ArbitrageScanner

logger = logging.getLogger("arbitrage.main")


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

        if attempt == attempts:
            for exchange_id, error in failures.items():
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
            ", ".join(failures),
            delay_seconds,
        )
        remaining = {exchange_id: remaining[exchange_id] for exchange_id in failures}
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
                logger.exception("Echec du scan, nouvelle tentative au prochain cycle")
                opportunities = []

            for opportunity in opportunities:
                try:
                    await executor.execute(opportunity)
                except TradeAborted as e:
                    logger.warning("Trade annule : %s", e)
                except Exception:
                    logger.exception("Erreur inattendue lors de l'execution d'une opportunite")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=config.scan_interval_seconds)
            except asyncio.TimeoutError:
                pass
    finally:
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
