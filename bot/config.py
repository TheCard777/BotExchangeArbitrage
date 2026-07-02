"""Loads config.yaml and .env into a single Config object."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

# Exchanges that require a third credential (an API passphrase) on top of the
# key and secret. Without it, real-mode auth on these exchanges fails.
PASSPHRASE_EXCHANGES = {"kucoin", "okx"}


@dataclass
class LoggingConfig:
    level: str = "INFO"
    file: str = "logs/arbitrage.log"


@dataclass
class Config:
    dry_run: bool
    scan_interval_seconds: float
    exchanges: list[str]
    pairs: list[str]
    min_profit_threshold: float
    max_trade_size_quote: float
    max_balance_fraction_per_trade: float
    max_slippage: float
    logging: LoggingConfig
    request_timeout_seconds: float = 60.0
    api_keys: dict[str, dict[str, str]] = field(default_factory=dict)

    def credentials_for(self, exchange_id: str) -> dict[str, str]:
        creds = self.api_keys.get(exchange_id)
        if not creds or not creds.get("apiKey") or not creds.get("secret"):
            raise ValueError(
                f"Missing API credentials for '{exchange_id}'. "
                f"Set {exchange_id.upper()}_API_KEY / {exchange_id.upper()}_API_SECRET in .env"
            )
        if exchange_id in PASSPHRASE_EXCHANGES and not creds.get("password"):
            raise ValueError(
                f"'{exchange_id}' requiert aussi une passphrase API. "
                f"Definis {exchange_id.upper()}_API_PASSPHRASE dans .env "
                f"(relance ./install.sh pour la saisir)."
            )
        return creds


def _positive(raw: dict, key: str, default: float) -> float:
    """Read a number that must be > 0, falling back to a sane default and
    rejecting garbage with a clear message instead of a cryptic crash later."""
    value = raw.get(key, default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{key}' doit etre un nombre (valeur lue : {value!r}).")
    if value <= 0:
        raise ValueError(f"'{key}' doit etre superieur a 0 (valeur lue : {value}).")
    return value


def load_config(config_path: str | Path = ROOT_DIR / "config.yaml") -> Config:
    load_dotenv(ROOT_DIR / ".env")

    try:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"config.yaml est mal forme et ne peut pas etre lu : {e}") from None

    if not isinstance(raw, dict):
        raise ValueError("config.yaml est vide ou invalide. Relance ./install.sh pour le regenerer.")

    exchanges = raw.get("exchanges")
    if not isinstance(exchanges, list) or len(exchanges) < 2:
        raise ValueError(
            "config.yaml doit lister au moins 2 exchanges sous 'exchanges:'. "
            "Relance ./install.sh pour corriger."
        )
    exchanges = [str(e).strip().lower() for e in exchanges if str(e).strip()]
    if len(set(exchanges)) < 2:
        raise ValueError("config.yaml doit lister au moins 2 exchanges differents.")

    pairs = raw.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise ValueError(
            "config.yaml doit lister au moins une paire sous 'pairs:' (ex: BTC/USDT). "
            "Relance ./install.sh pour corriger."
        )
    pairs = [str(p).strip().upper() for p in pairs if str(p).strip()]
    invalid_pairs = [p for p in pairs if len(p.split("/")) != 2 or not all(p.split("/"))]
    if invalid_pairs:
        raise ValueError(
            f"Paires mal formees dans config.yaml : {', '.join(invalid_pairs)}. "
            "Utilise le format BASE/COTATION, ex: BTC/USDT."
        )

    api_keys = {}
    for exchange_id in exchanges:
        prefix = exchange_id.upper()
        api_keys[exchange_id] = {
            "apiKey": os.getenv(f"{prefix}_API_KEY", ""),
            "secret": os.getenv(f"{prefix}_API_SECRET", ""),
            # Only some exchanges (KuCoin, OKX) use a passphrase; empty for the rest.
            "password": os.getenv(f"{prefix}_API_PASSPHRASE", ""),
        }

    return Config(
        dry_run=bool(raw.get("dry_run", True)),
        scan_interval_seconds=_positive(raw, "scan_interval_seconds", 10),
        exchanges=exchanges,
        pairs=pairs,
        min_profit_threshold=raw.get("min_profit_threshold", 0.005),
        max_trade_size_quote=_positive(raw, "max_trade_size_quote", 100),
        max_balance_fraction_per_trade=raw.get("max_balance_fraction_per_trade", 1.0),
        max_slippage=raw.get("max_slippage", 0.002),
        logging=LoggingConfig(**(raw.get("logging") or {})),
        request_timeout_seconds=_positive(raw, "request_timeout_seconds", 60.0),
        api_keys=api_keys,
    )
