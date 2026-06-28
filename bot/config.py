"""Loads config.yaml and .env into a single Config object."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent


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
    request_timeout_seconds: float = 30.0
    api_keys: dict[str, dict[str, str]] = field(default_factory=dict)

    def credentials_for(self, exchange_id: str) -> dict[str, str]:
        creds = self.api_keys.get(exchange_id)
        if not creds or not creds.get("apiKey") or not creds.get("secret"):
            raise ValueError(
                f"Missing API credentials for '{exchange_id}'. "
                f"Set {exchange_id.upper()}_API_KEY / {exchange_id.upper()}_API_SECRET in .env"
            )
        return creds


def load_config(config_path: str | Path = ROOT_DIR / "config.yaml") -> Config:
    load_dotenv(ROOT_DIR / ".env")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    api_keys = {}
    for exchange_id in raw["exchanges"]:
        prefix = exchange_id.upper()
        api_keys[exchange_id] = {
            "apiKey": os.getenv(f"{prefix}_API_KEY", ""),
            "secret": os.getenv(f"{prefix}_API_SECRET", ""),
        }

    return Config(
        dry_run=raw.get("dry_run", True),
        scan_interval_seconds=raw.get("scan_interval_seconds", 10),
        exchanges=raw["exchanges"],
        pairs=raw["pairs"],
        min_profit_threshold=raw["min_profit_threshold"],
        max_trade_size_quote=raw["max_trade_size_quote"],
        max_balance_fraction_per_trade=raw.get("max_balance_fraction_per_trade", 1.0),
        max_slippage=raw.get("max_slippage", 0.002),
        logging=LoggingConfig(**raw.get("logging", {})),
        request_timeout_seconds=raw.get("request_timeout_seconds", 30.0),
        api_keys=api_keys,
    )
