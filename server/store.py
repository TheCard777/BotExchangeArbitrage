"""SQLite persistence: users, sessions, encrypted exchange keys, bot config.

API keys/secrets/passphrases are encrypted (see crypto_box) before they ever
touch the database. The plain values only exist in memory when building a
Config to run the bot.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time

from server import crypto_box, security

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS exchange_keys (
    user_id INTEGER NOT NULL,
    exchange TEXT NOT NULL,
    api_key_enc TEXT NOT NULL,
    secret_enc TEXT NOT NULL,
    passphrase_enc TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, exchange)
);
CREATE TABLE IF NOT EXISTS bot_config (
    user_id INTEGER PRIMARY KEY,
    config_json TEXT NOT NULL
);
"""

DEFAULT_CONFIG = {
    "dry_run": True,
    "pairs": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "DOGE/USDT"],
    "min_profit_threshold": 0.005,
    "max_trade_size_quote": 100.0,
    "top_movers": 0,
}


class Store:
    def __init__(self, path: str = "platform.db"):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # --- users & sessions ---------------------------------------------------
    def create_user(self, email: str, password: str) -> int:
        email = email.strip().lower()
        if not email or "@" not in email:
            raise ValueError("Adresse email invalide.")
        with self._lock:
            existing = self._conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if existing:
                raise ValueError("Un compte existe deja avec cet email.")
            cur = self._conn.execute(
                "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
                (email, security.hash_password(password), time.time()),
            )
            self._conn.commit()
            return cur.lastrowid

    def login(self, email: str, password: str) -> str | None:
        """Return a new session token on success, else None."""
        email = email.strip().lower()
        with self._lock:
            row = self._conn.execute(
                "SELECT id, password_hash FROM users WHERE email=?", (email,)
            ).fetchone()
        if not row or not security.verify_password(password, row["password_hash"]):
            return None
        token = security.new_token()
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
                (token, row["id"], time.time()),
            )
            self._conn.commit()
        return token

    def user_for_token(self, token: str) -> int | None:
        if not token:
            return None
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id FROM sessions WHERE token=?", (token,)
            ).fetchone()
        return row["user_id"] if row else None

    def logout(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE token=?", (token,))
            self._conn.commit()

    # --- exchange keys (encrypted) -----------------------------------------
    def set_exchange_key(
        self, user_id: int, exchange: str, api_key: str, secret: str, passphrase: str = ""
    ) -> None:
        exchange = exchange.strip().lower()
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO exchange_keys "
                "(user_id, exchange, api_key_enc, secret_enc, passphrase_enc) VALUES (?, ?, ?, ?, ?)",
                (
                    user_id,
                    exchange,
                    crypto_box.encrypt(api_key),
                    crypto_box.encrypt(secret),
                    crypto_box.encrypt(passphrase),
                ),
            )
            self._conn.commit()

    def delete_exchange_key(self, user_id: int, exchange: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM exchange_keys WHERE user_id=? AND exchange=?",
                (user_id, exchange.strip().lower()),
            )
            self._conn.commit()

    def list_exchanges(self, user_id: int) -> list[str]:
        """Exchange ids the user has keys for — never returns the secrets."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT exchange FROM exchange_keys WHERE user_id=? ORDER BY exchange", (user_id,)
            ).fetchall()
        return [r["exchange"] for r in rows]

    def decrypted_keys(self, user_id: int) -> dict[str, dict[str, str]]:
        """Decrypt the user's keys to build a bot Config. Kept in memory only."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT exchange, api_key_enc, secret_enc, passphrase_enc "
                "FROM exchange_keys WHERE user_id=?",
                (user_id,),
            ).fetchall()
        return {
            r["exchange"]: {
                "apiKey": crypto_box.decrypt(r["api_key_enc"]),
                "secret": crypto_box.decrypt(r["secret_enc"]),
                "password": crypto_box.decrypt(r["passphrase_enc"]),
            }
            for r in rows
        }

    # --- per-user bot config ------------------------------------------------
    def get_config(self, user_id: int) -> dict:
        with self._lock:
            row = self._conn.execute(
                "SELECT config_json FROM bot_config WHERE user_id=?", (user_id,)
            ).fetchone()
        if not row:
            return dict(DEFAULT_CONFIG)
        merged = dict(DEFAULT_CONFIG)
        merged.update(json.loads(row["config_json"]))
        return merged

    def set_config(self, user_id: int, config: dict) -> dict:
        merged = dict(DEFAULT_CONFIG)
        merged.update({k: v for k, v in config.items() if k in DEFAULT_CONFIG})
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO bot_config (user_id, config_json) VALUES (?, ?)",
                (user_id, json.dumps(merged)),
            )
            self._conn.commit()
        return merged

    def close(self) -> None:
        with self._lock:
            self._conn.close()
