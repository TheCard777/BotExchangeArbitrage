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


async def connect_with_retries(scanner: ArbitrageScanner, attempts: int = 5, delay_seconds: float = 5) -> None:
    for attempt in range(1, attempts + 1):
        try:
            await scanner.load_markets()
            return
        except Exception as e:
            if attempt == attempts:
                raise
            logger.warning(
                "Connexion aux exchanges impossible (essai %d/%d) : %s — nouvelle tentative dans %ds",
                attempt,
                attempts,
                e,
                delay_seconds,
            )
            await asyncio.sleep(delay_seconds)


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

    await connect_with_retries(scanner)

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
        await asyncio.gather(*(client.close() for client in clients.values()))


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
