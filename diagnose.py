"""Outil de diagnostic de connexion.

Teste, un par un, chaque exchange configure et explique en clair pourquoi il
est joignable ou non (blocage geographique, connexion trop lente, pare-feu,
cles API...). A lancer quand le bot n'arrive pas a se connecter :

    ./diagnose.sh           (Windows : via Git Bash)
ou  .venv/bin/python diagnose.py
"""
from __future__ import annotations

import asyncio
import logging
import time

import aiohttp
import ccxt.async_support as ccxt

from bot.diagnostics import GEOBLOCK, classify_error

# Keep ccxt/aiohttp's cosmetic "unclosed session" chatter out of the report —
# it's harmless noise that would only confuse a non-technical user.
logging.getLogger("ccxt.base.exchange").setLevel(logging.CRITICAL)
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

DEFAULT_EXCHANGES = ["binance", "kraken", "coinbase", "bybit", "kucoin", "okx"]
# Exchanges qui marchent souvent la ou Binance est bloque.
GEOBLOCK_ALTERNATIVES = ["kraken", "kucoin", "okx", "bybit"]
PROBE_TIMEOUT = 20


def load_configured_exchanges() -> list[str]:
    """Liste des exchanges du config.yaml, ou liste par defaut si absent."""
    try:
        from bot.config import load_config

        return load_config().exchanges
    except Exception:
        return DEFAULT_EXCHANGES


async def check_internet() -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get("https://www.cloudflare.com/cdn-cgi/trace"):
                return True
    except Exception:
        return False


async def test_exchange(exchange_id: str) -> dict:
    """Tente de charger les marches d'un exchange et classe le resultat."""
    exchange = None
    started = time.monotonic()
    try:
        exchange_class = getattr(ccxt, exchange_id)
        exchange = exchange_class({"enableRateLimit": True, "timeout": PROBE_TIMEOUT * 1000})
        await exchange.load_markets()
        elapsed = time.monotonic() - started
        return {"id": exchange_id, "ok": True, "elapsed": elapsed}
    except Exception as e:  # noqa: BLE001 — on veut classer tout type d'echec
        category, message = classify_error(e)
        return {
            "id": exchange_id,
            "ok": False,
            "elapsed": time.monotonic() - started,
            "category": category,
            "message": message,
        }
    finally:
        if exchange is not None:
            try:
                await exchange.close(clean_instance_data=True)
            except Exception:
                pass


async def run() -> None:
    print("=" * 64)
    print("  Diagnostic de connexion - Bot d'arbitrage crypto")
    print("=" * 64)
    print()

    print("1) Test de la connexion internet de base...")
    if await check_internet():
        print("   OK : cette machine a bien acces a internet.")
    else:
        print("   ECHEC : aucune connexion internet detectee.")
        print("   -> Verifie ton Wi-Fi/4G, coupe un eventuel VPN, puis relance.")
        print()
        print("Inutile de tester les exchanges sans internet. Diagnostic termine.")
        return

    exchanges = load_configured_exchanges()
    print()
    print(f"2) Test de chaque exchange ({', '.join(exchanges)})...")
    print()

    results = await asyncio.gather(*(test_exchange(e) for e in exchanges))

    ok = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    for r in results:
        if r["ok"]:
            print(f"   [OK ] {r['id']:<10} joignable ({r['elapsed']:.1f}s)")
        else:
            print(f"   [KO ] {r['id']:<10} {r['message']}")

    print()
    print("=" * 64)
    print("Resume :")
    print(f"  {len(ok)} exchange(s) joignable(s) : {', '.join(r['id'] for r in ok) or 'aucun'}")
    print(f"  {len(failed)} en echec : {', '.join(r['id'] for r in failed) or 'aucun'}")
    print()

    if len(ok) >= 2:
        print("Tu as au moins 2 exchanges joignables : le bot peut fonctionner.")
        if failed:
            print("Pour eviter les avertissements, tu peux retirer du config.yaml les")
            print(f"exchanges en echec ({', '.join(r['id'] for r in failed)}) et relancer ./install.sh.")
    else:
        print("Moins de 2 exchanges joignables : le bot ne peut pas comparer les prix.")
        geo = [r for r in failed if r.get("category") == GEOBLOCK]
        if geo:
            print()
            print(f"Exchange(s) bloque(s) geographiquement : {', '.join(r['id'] for r in geo)}.")
            print("C'est une restriction de l'exchange, pas un bug du bot.")
            alternatives = [a for a in GEOBLOCK_ALTERNATIVES if a not in [r["id"] for r in failed]]
            suggestion = alternatives or GEOBLOCK_ALTERNATIVES
            print(f"-> Remplace-les par d'autres exchanges (ex: {', '.join(suggestion[:3])})")
            print("   en relancant ./install.sh, ou utilise un VPN vers un pays autorise.")
        else:
            print("-> Essaie un autre reseau (Wi-Fi au lieu de 4G, ou inversement) ou un VPN,")
            print("   puis relance ce diagnostic.")
    print("=" * 64)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
