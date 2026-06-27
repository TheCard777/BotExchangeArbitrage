"""Interactive setup wizard for beginners.

Asks a handful of plain-language questions and writes .env and config.yaml
for you — no manual file editing required. Safe to re-run at any time.
"""
from __future__ import annotations

import getpass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

SUPPORTED_EXCHANGES = [
    ("binance", "Binance"),
    ("kraken", "Kraken"),
    ("coinbase", "Coinbase"),
    ("bybit", "Bybit"),
    ("kucoin", "KuCoin"),
    ("okx", "OKX"),
]

DEFAULT_PAIRS = ["BTC/USDT", "ETH/USDT"]
LIVE_CONFIRM_PHRASE = "ACTIVER"

CONFIG_TEMPLATE = """\
# Configuration generee par setup_wizard.py.
# Tu peux la modifier a la main, ou relancer setup_wizard.py pour repartir de zero.
#
# dry_run: true  -> le bot observe et affiche les opportunites, sans jamais trader.
# dry_run: false -> le bot passe de vrais ordres avec l'argent de tes comptes.
dry_run: {dry_run}

scan_interval_seconds: 10

exchanges:
{exchanges_yaml}

pairs:
{pairs_yaml}

# Profit minimum (apres frais) pour agir sur une opportunite. 0.005 = 0.5%.
min_profit_threshold: 0.005

# Montant maximum (en monnaie de cotation, ex: USDT) engage par trade.
max_trade_size_quote: {max_trade_size_quote}

# Fraction maximum du solde disponible utilisee par trade, en plus du plafond ci-dessus.
max_balance_fraction_per_trade: 0.5

# Ecart de prix tolere entre le scan et l'execution avant d'annuler un trade.
max_slippage: 0.002

logging:
  level: INFO
  file: logs/arbitrage.log
"""


def ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix} ").strip()
    return answer if answer else (default or "")


def ask_choice(prompt: str, choices: list[str], default_index: int = 0) -> str:
    while True:
        answer = ask(prompt, choices[default_index])
        if answer in choices:
            return answer
        print(f"  -> reponds avec une de ces valeurs : {', '.join(choices)}")


def print_header() -> None:
    print("=" * 64)
    print("  Assistant de configuration - Bot d'arbitrage crypto")
    print("=" * 64)
    print()
    print("Ce bot compare les prix entre plusieurs exchanges crypto et")
    print("peut trader automatiquement les ecarts de prix rentables.")
    print()
    print("ATTENTION : si tu actives le mode reel, le bot utilise de")
    print("l'argent reel sur tes comptes. Commence toujours par le mode")
    print("demonstration pour voir comment il se comporte.")
    print()


def choose_exchanges() -> list[str]:
    print("Exchanges disponibles :")
    for i, (_, label) in enumerate(SUPPORTED_EXCHANGES, start=1):
        print(f"  {i}. {label}")
    print()
    print("Choisis-en au moins 2 (le bot compare leurs prix entre eux).")

    while True:
        raw = ask("Tes choix, separes par des virgules (ex: 1,2)", "1,2")
        try:
            indices = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except ValueError:
            print("  -> entre des numeros separes par des virgules, ex: 1,2")
            continue

        if len(set(indices)) < 2 or any(i < 1 or i > len(SUPPORTED_EXCHANGES) for i in indices):
            print(f"  -> choisis au moins 2 numeros valides entre 1 et {len(SUPPORTED_EXCHANGES)}")
            continue

        return [SUPPORTED_EXCHANGES[i - 1][0] for i in dict.fromkeys(indices)]


def choose_pairs() -> list[str]:
    print()
    print(f"Paires a surveiller par defaut : {', '.join(DEFAULT_PAIRS)}")
    while True:
        raw = ask(
            "Appuie sur Entree pour garder ce choix, ou tape tes paires separees par des virgules"
            " (ex: BTC/USDT,SOL/USDT)",
            ",".join(DEFAULT_PAIRS),
        )
        pairs = [p.strip().upper() for p in raw.split(",") if p.strip()]
        invalid = [p for p in pairs if len(p.split("/")) != 2 or not all(p.split("/"))]
        if invalid:
            print(f"  -> format invalide : {', '.join(invalid)}. Utilise BASE/COTATION, ex: BTC/USDT")
            continue
        return pairs


def collect_api_keys(exchanges: list[str]) -> dict[str, tuple[str, str]]:
    print()
    print("Pour chaque exchange, entre une cle API avec les droits de")
    print("TRADING uniquement (jamais de droit de retrait). La saisie est masquee.")
    print()
    keys = {}
    for exchange_id in exchanges:
        label = dict((eid, name) for eid, name in SUPPORTED_EXCHANGES)[exchange_id]
        print(f"-- {label} --")
        api_key = getpass.getpass(f"  Cle API {label} (laisser vide pour passer) : ").strip()
        api_secret = ""
        if api_key:
            api_secret = getpass.getpass(f"  Secret API {label} : ").strip()
        keys[exchange_id] = (api_key, api_secret)
    return keys


def write_env(keys: dict[str, tuple[str, str]]) -> None:
    lines = ["# Genere par setup_wizard.py. Ne partage jamais ce fichier.", ""]
    for exchange_id, (api_key, api_secret) in keys.items():
        prefix = exchange_id.upper()
        lines.append(f"{prefix}_API_KEY={api_key}")
        lines.append(f"{prefix}_API_SECRET={api_secret}")
        lines.append("")
    (ROOT_DIR / ".env").write_text("\n".join(lines))


def write_config(dry_run: bool, exchanges: list[str], pairs: list[str], max_trade_size_quote: float) -> None:
    exchanges_yaml = "\n".join(f"  - {e}" for e in exchanges)
    pairs_yaml = "\n".join(f"  - {p}" for p in pairs)
    content = CONFIG_TEMPLATE.format(
        dry_run="true" if dry_run else "false",
        exchanges_yaml=exchanges_yaml,
        pairs_yaml=pairs_yaml,
        max_trade_size_quote=max_trade_size_quote,
    )
    (ROOT_DIR / "config.yaml").write_text(content)


def main() -> None:
    print_header()

    existing_env = ROOT_DIR / ".env"
    if existing_env.exists():
        keep = ask("Une configuration existe deja. La remplacer ? (o/n)", "n")
        if keep.lower() not in ("o", "oui", "y", "yes"):
            print("Configuration existante conservee. Aucun changement effectue.")
            return

    print("As-tu deja des cles API pour trader avec de l'argent reel ?")
    print("  1. Non, je veux juste voir comment le bot fonctionne (mode demonstration, sans risque)")
    print("  2. Oui, je veux configurer mes cles pour trader")
    mode = ask_choice("Ton choix", ["1", "2"], default_index=0)

    exchanges = choose_exchanges()
    pairs = choose_pairs()

    if mode == "1":
        keys = {eid: ("", "") for eid in exchanges}
        dry_run = True
        max_trade_size_quote = 100
        print()
        print("Mode demonstration choisi : aucune cle API necessaire, le bot")
        print("affichera les opportunites detectees sans jamais trader.")
    else:
        keys = collect_api_keys(exchanges)
        print()
        budget = ask("Montant maximum a risquer par trade, en USDT", "50")
        try:
            max_trade_size_quote = float(budget.replace(",", "."))
        except ValueError:
            max_trade_size_quote = 50.0

        print()
        print("Veux-tu activer le trading reel des maintenant, ou commencer")
        print("en mode demonstration pour observer le bot avant de risquer de l'argent ?")
        print(f"  -> tape '{LIVE_CONFIRM_PHRASE}' pour activer le trading reel tout de suite,")
        print("     ou appuie juste sur Entree pour rester en mode demonstration.")
        confirm = ask("Ta reponse", "")
        dry_run = confirm.strip().upper() != LIVE_CONFIRM_PHRASE

    write_config(dry_run, exchanges, pairs, max_trade_size_quote)
    write_env(keys)

    print()
    print("=" * 64)
    print("Configuration enregistree !")
    print(f"  Mode : {'DEMONSTRATION (aucun trade reel)' if dry_run else 'REEL (argent reel engage)'}")
    print(f"  Exchanges : {', '.join(exchanges)}")
    print(f"  Paires : {', '.join(pairs)}")
    print()
    print("Pour lancer le bot : ./start.sh")
    if dry_run:
        print()
        print("Quand tu seras pret a trader pour de vrai, relance ./install.sh")
        print(f"et tape '{LIVE_CONFIRM_PHRASE}' a la derniere question.")
    print("=" * 64)


if __name__ == "__main__":
    main()
