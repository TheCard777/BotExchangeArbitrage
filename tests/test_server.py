"""Tests for the SaaS platform layer (server/).

Covers: crypto_box (Fernet round-trip), security (password hashing/tokens),
store (users/sessions/encrypted keys/config on a temp SQLite db), engine
(UserBotEngine + BotManager with a fake scanner so no network), and the API
(FastAPI TestClient with a fake engine factory so no real exchange calls).
"""
from __future__ import annotations

import asyncio

import pytest
from cryptography.fernet import Fernet

from server import crypto_box, security
from server.engine import BotManager, UserBotEngine, build_config
from server.store import DEFAULT_CONFIG, Store


@pytest.fixture(autouse=True)
def _platform_secret(monkeypatch):
    """Every test runs with a valid master encryption key set."""
    monkeypatch.setenv("BOT_PLATFORM_SECRET", Fernet.generate_key().decode())


@pytest.fixture
def store(tmp_path):
    s = Store(str(tmp_path / "test.db"))
    yield s
    s.close()


# --- crypto_box -------------------------------------------------------------
def test_crypto_box_round_trip():
    token = crypto_box.encrypt("my-secret-api-key")
    assert token != "my-secret-api-key"  # actually encrypted
    assert crypto_box.decrypt(token) == "my-secret-api-key"


def test_crypto_box_empty_passthrough():
    assert crypto_box.encrypt("") == ""
    assert crypto_box.decrypt("") == ""


def test_crypto_box_missing_secret(monkeypatch):
    monkeypatch.delenv("BOT_PLATFORM_SECRET", raising=False)
    with pytest.raises(crypto_box.SecretConfigError):
        crypto_box.encrypt("x")


def test_crypto_box_wrong_secret_fails(monkeypatch):
    token = crypto_box.encrypt("secret")
    monkeypatch.setenv("BOT_PLATFORM_SECRET", Fernet.generate_key().decode())
    with pytest.raises(crypto_box.SecretConfigError):
        crypto_box.decrypt(token)


# --- security ---------------------------------------------------------------
def test_password_hash_and_verify():
    stored = security.hash_password("hunter2!!")
    assert "$" in stored
    assert security.verify_password("hunter2!!", stored)
    assert not security.verify_password("wrong", stored)


def test_password_hash_is_salted():
    assert security.hash_password("same") != security.hash_password("same")


def test_verify_rejects_garbage():
    assert not security.verify_password("x", "not-a-valid-stored-hash")


def test_empty_password_rejected():
    with pytest.raises(ValueError):
        security.hash_password("")


def test_tokens_are_unique():
    assert security.new_token() != security.new_token()


# --- store: users & sessions ------------------------------------------------
def test_create_login_logout(store):
    uid = store.create_user("User@Example.com", "password123")
    assert isinstance(uid, int)
    token = store.login("user@example.com", "password123")  # case-insensitive email
    assert token
    assert store.user_for_token(token) == uid
    store.logout(token)
    assert store.user_for_token(token) is None


def test_duplicate_email_rejected(store):
    store.create_user("a@b.com", "password123")
    with pytest.raises(ValueError):
        store.create_user("a@b.com", "password123")


def test_bad_email_rejected(store):
    with pytest.raises(ValueError):
        store.create_user("not-an-email", "password123")


def test_login_wrong_password(store):
    store.create_user("a@b.com", "password123")
    assert store.login("a@b.com", "nope") is None


def test_unknown_token(store):
    assert store.user_for_token("garbage") is None
    assert store.user_for_token("") is None


# --- store: exchange keys ---------------------------------------------------
def test_exchange_keys_encrypted_and_recoverable(store):
    uid = store.create_user("a@b.com", "password123")
    store.set_exchange_key(uid, "Binance", "KEY123", "SECRET456")
    store.set_exchange_key(uid, "kucoin", "K2", "S2", "passphrase!")

    assert store.list_exchanges(uid) == ["binance", "kucoin"]

    keys = store.decrypted_keys(uid)
    assert keys["binance"] == {"apiKey": "KEY123", "secret": "SECRET456", "password": ""}
    assert keys["kucoin"]["password"] == "passphrase!"


def test_exchange_keys_stored_ciphertext_not_plaintext(store):
    uid = store.create_user("a@b.com", "password123")
    store.set_exchange_key(uid, "binance", "PLAINKEY", "PLAINSECRET")
    row = store._conn.execute(
        "SELECT api_key_enc, secret_enc FROM exchange_keys WHERE user_id=?", (uid,)
    ).fetchone()
    assert "PLAINKEY" not in row["api_key_enc"]
    assert "PLAINSECRET" not in row["secret_enc"]


def test_delete_exchange_key(store):
    uid = store.create_user("a@b.com", "password123")
    store.set_exchange_key(uid, "binance", "k", "s")
    store.delete_exchange_key(uid, "binance")
    assert store.list_exchanges(uid) == []


def test_keys_isolated_per_user(store):
    u1 = store.create_user("a@b.com", "password123")
    u2 = store.create_user("c@d.com", "password123")
    store.set_exchange_key(u1, "binance", "k1", "s1")
    assert store.list_exchanges(u2) == []


# --- store: config ----------------------------------------------------------
def test_config_defaults(store):
    uid = store.create_user("a@b.com", "password123")
    assert store.get_config(uid) == DEFAULT_CONFIG


def test_config_set_merges_and_ignores_unknown(store):
    uid = store.create_user("a@b.com", "password123")
    saved = store.set_config(uid, {"dry_run": False, "top_movers": 5, "evil_field": 1})
    assert saved["dry_run"] is False
    assert saved["top_movers"] == 5
    assert "evil_field" not in saved
    # persisted
    assert store.get_config(uid)["dry_run"] is False


# --- engine -----------------------------------------------------------------
def _make_config(store, uid):
    store.set_exchange_key(uid, "binance", "k", "s")
    store.set_exchange_key(uid, "kraken", "k", "s")
    return build_config(store, uid)


def test_build_config_uses_user_keys(store):
    uid = store.create_user("a@b.com", "password123")
    store.set_config(uid, {"dry_run": False, "max_trade_size_quote": 42.0})
    config = _make_config(store, uid)
    assert set(config.exchanges) == {"binance", "kraken"}
    assert config.dry_run is False
    assert config.max_trade_size_quote == 42.0
    assert config.realtime is False
    assert "binance" in config.api_keys


class FakeScanner:
    """Stands in for ArbitrageScanner: no network, deterministic results."""

    def __init__(self):
        from bot.scanner import Opportunity

        self.clients = {"binance": _FakeClient(), "kraken": _FakeClient()}
        self._opp = Opportunity("BTC/USDT", "binance", "kraken", 100.0, 101.0, 0.008)
        self.last_scan_summary = {}

    async def scan(self):
        self.last_scan_summary = {"exchanges": 2, "best": self._opp}
        return [self._opp]


class _FakeClient:
    async def close(self):
        pass


@pytest.mark.asyncio
async def test_user_bot_engine_runs_and_reports(store):
    uid = store.create_user("a@b.com", "password123")
    config = _make_config(store, uid)

    async def build_scanner(_config):
        return FakeScanner()

    engine = UserBotEngine(config, build_scanner=build_scanner, scan_interval=0.01)
    await engine.start()
    # wait for at least one scan
    for _ in range(100):
        if engine.opportunities:
            break
        await asyncio.sleep(0.01)
    await engine.stop()

    assert engine.status == "stopped"
    snap = engine.snapshot()
    assert snap["opportunities"], "engine should have reported an opportunity"
    assert snap["summary"]["exchanges"] == 2
    assert snap["error"] is None


@pytest.mark.asyncio
async def test_user_bot_engine_surfaces_connect_failure(store):
    uid = store.create_user("a@b.com", "password123")
    config = _make_config(store, uid)

    async def failing_build(_config):
        raise RuntimeError("cle API invalide")

    engine = UserBotEngine(config, build_scanner=failing_build)
    await engine.start()
    await engine.stop()
    assert engine.status == "error"
    assert "cle API invalide" in engine.error


@pytest.mark.asyncio
async def test_bot_manager_lifecycle(store):
    uid = store.create_user("a@b.com", "password123")
    _make_config(store, uid)

    class FakeEngine:
        def __init__(self, config):
            self.config = config
            self.status = "stopped"
            self.started = False

        async def start(self):
            self.started = True
            self.status = "running"

        async def stop(self):
            self.status = "stopped"

        def snapshot(self):
            return {"status": self.status}

    manager = BotManager(store, engine_factory=FakeEngine)
    engine = await manager.start(uid)
    assert engine.started
    assert manager.snapshot(uid)["status"] == "running"
    # starting again returns the same running engine
    assert await manager.start(uid) is engine
    await manager.shutdown()
    assert engine.status == "stopped"


# --- API --------------------------------------------------------------------
@pytest.fixture
def client(store):
    from fastapi.testclient import TestClient

    from server.app import create_app

    class FakeEngine:
        def __init__(self, config):
            self.config = config

        async def start(self):
            pass

        def snapshot(self):
            return {
                "status": "running",
                "error": None,
                "dry_run": self.config.dry_run,
                "exchanges": list(self.config.exchanges),
                "opportunities": [],
                "summary": {},
            }

        async def stop(self):
            pass

    manager = BotManager(store, engine_factory=FakeEngine)
    app = create_app(store=store, manager=manager)
    with TestClient(app) as c:
        yield c


def _auth(client, email="a@b.com", password="password123"):
    client.post("/api/register", json={"email": email, "password": password})
    token = client.post("/api/login", json={"email": email, "password": password}).json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_register_and_login(client):
    r = client.post("/api/register", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 200
    r = client.post("/api/login", json={"email": "a@b.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["token"]


def test_register_short_password_rejected(client):
    r = client.post("/api/register", json={"email": "a@b.com", "password": "short"})
    assert r.status_code == 422


def test_login_bad_credentials(client):
    client.post("/api/register", json={"email": "a@b.com", "password": "password123"})
    r = client.post("/api/login", json={"email": "a@b.com", "password": "nope"})
    assert r.status_code == 401


def test_endpoints_require_auth(client):
    assert client.get("/api/exchanges").status_code == 401
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/bot/status").status_code == 401


def test_exchange_key_flow(client):
    headers = _auth(client)
    r = client.put(
        "/api/exchanges/binance",
        json={"api_key": "KEY", "secret": "SECRET"},
        headers=headers,
    )
    assert r.status_code == 200
    assert "binance" in r.json()["exchanges"]

    assert client.get("/api/exchanges", headers=headers).json()["exchanges"] == ["binance"]

    r = client.request("DELETE", "/api/exchanges/binance", headers=headers)
    assert r.json()["exchanges"] == []


def test_config_flow(client):
    headers = _auth(client)
    assert client.get("/api/config", headers=headers).json()["dry_run"] is True
    r = client.put("/api/config", json={"dry_run": False, "top_movers": 3}, headers=headers)
    assert r.json()["dry_run"] is False
    assert r.json()["top_movers"] == 3


def test_bot_start_requires_two_exchanges(client):
    headers = _auth(client)
    r = client.post("/api/bot/start", headers=headers)
    assert r.status_code == 400  # no exchanges yet


def test_bot_start_stop_status(client):
    headers = _auth(client)
    client.put("/api/exchanges/binance", json={"api_key": "k", "secret": "s"}, headers=headers)
    client.put("/api/exchanges/kraken", json={"api_key": "k", "secret": "s"}, headers=headers)
    r = client.post("/api/bot/start", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "running"
    assert client.post("/api/bot/stop", headers=headers).json()["ok"] is True


def test_users_cannot_see_each_others_exchanges(client):
    h1 = _auth(client, "a@b.com")
    h2 = _auth(client, "c@d.com")
    client.put("/api/exchanges/binance", json={"api_key": "k", "secret": "s"}, headers=h1)
    assert client.get("/api/exchanges", headers=h2).json()["exchanges"] == []


def test_frontend_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Plateforme Arbitrage" in r.text
