"""Entrypoint: scan configured exchanges/pairs for arbitrage and act on them."""
from __future__ import annotations

import asyncio
import logging
import signal

import aiohttp

from bot.config import load_config
from bot.exchange_client import ExchangeClient
from bot.executor import TradeAborted, TradeExecutor
from bot.logger import setup_logging
from bot.scanner import ArbitrageScanner

logger = logging.getLogger("arbitrage.main")


async def check_internet_connectivity(timeout_seconds: float = 8) -> bool:
    """Quick, exchange-independent reachability check used to tell apart
    'no internet at all' from 'internet works but exchanges don't' when
    every configured exchange fails to connect.
    """
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout_seconds)) as session:
            # Receiving any HTTP response at all (even an error status like
            # 403) proves the network path to the internet works — only an
            # exception (timeout, DNS failure, connection refused) means
            # there's really no connectivity.
            async with session.get("https://www.cloudflare.com/cdn-cgi/trace"):
                return True
    except Exception:
        return False


async def connect_with_retries(scanner: ArbitrageScanner, attempts: int = 5, delay_seconds: float = 5) -> None:
    """Connect to every configured exchange, retrying only the ones still
    failing on each attempt. An exchange that never connects is dropped
    instead of blocking the others — one flaky/unreachable exchange
    shouldn't stop the bot from running on the rest.
    """
    remaining = dict(scanner.clients)
    for attempt in range(1, attempts + 1):
        results = await asyncio.gather(
            *(client.load_markets() for client in remaining.values()),
            return_exceptions=True,
        )
        failures = {
            exchange_id: result
            for exchange_id, result in zip(remaining.keys(), results)
            if isinstance(result, Exception)
        }
        if not failures:
            return

        if attempt == attempts:
            for exchange_id, error in failures.items():
                logger.warning(
                    "%s reste inaccessible apres %d tentatives (%s: %s) — exchange ignore pour cette session",
                    exchange_id,
                    attempts,
                    type(error).__name__,
                    error,
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


async def run() -> None:
    config = load_config()
    setup_logging(config.logging)

    if config.dry_run:
        logger.info("Demarrage en mode DEMONSTRATION — aucun ordre reel ne sera passe.")
    else:
        logger.warning("Demarrage en mode REEL — des ordres reels seront passes avec de l'argent reel.")

    clients = {eid: ExchangeClient(eid, config) for eid in config.exchanges}
    scanner = ArbitrageScanner(clients, config.pairs, config.min_profit_threshold)
    executor = TradeExecutor(clients, config)

    try:
        await connect_with_retries(scanner)
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
