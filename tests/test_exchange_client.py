"""Tests for ExchangeClient's automatic alternate-domain fallback."""
import types

import pytest

from bot import exchange_client
from bot.config import Config, LoggingConfig


def make_config():
    return Config(
        dry_run=True,
        scan_interval_seconds=10,
        exchanges=["bybit"],
        pairs=["BTC/USDT"],
        min_profit_threshold=0.005,
        max_trade_size_quote=100,
        max_balance_fraction_per_trade=1.0,
        max_slippage=0.002,
        logging=LoggingConfig(),
        api_keys={"bybit": {"apiKey": "", "secret": "", "password": ""}},
    )


def make_fake_exchange(fail_main, error_message):
    """Build a fake ccxt exchange class whose main host fails and whose
    alternate host (bytick) succeeds, tracking every instance created."""
    instances = []

    class _Fake:
        def __init__(self, params):
            self.params = params
            self.hostname = params.get("hostname", "bybit.com")
            self.has = {"watchTicker": True}
            self.markets = {}
            self.closed = False
            instances.append(self)

        async def load_markets(self):
            if "bytick" in self.hostname:
                self.markets = {"BTC/USDT": {}}
                return self.markets
            if fail_main:
                raise Exception(error_message)
            self.markets = {"BTC/USDT": {}}
            return self.markets

        async def close(self, clean_instance_data=False):
            self.closed = True

    return _Fake, instances


async def test_falls_back_to_bytick_on_network_error(monkeypatch):
    fake_cls, instances = make_fake_exchange(
        fail_main=True, error_message="bybit Cannot connect to host api.bybit.com"
    )
    monkeypatch.setattr(exchange_client, "ccxt", types.SimpleNamespace(bybit=fake_cls))
    client = exchange_client.ExchangeClient("bybit", make_config())

    markets = await client.load_markets()

    assert markets == {"BTC/USDT": {}}
    assert client._tried_alt is True
    assert client.exchange.hostname == "bytick.com"  # switched
    assert instances[0].closed is True  # old (main-domain) instance was closed


async def test_no_fallback_when_main_host_works(monkeypatch):
    fake_cls, instances = make_fake_exchange(fail_main=False, error_message="")
    monkeypatch.setattr(exchange_client, "ccxt", types.SimpleNamespace(bybit=fake_cls))
    client = exchange_client.ExchangeClient("bybit", make_config())

    await client.load_markets()

    assert client._tried_alt is False
    assert client.exchange.hostname == "bybit.com"
    assert len(instances) == 1  # never rebuilt


async def test_auth_error_does_not_trigger_fallback(monkeypatch):
    # An auth problem isn't a reachability problem — don't switch domains.
    fake_cls, _ = make_fake_exchange(
        fail_main=True, error_message="bybit Invalid api-key or signature"
    )
    monkeypatch.setattr(exchange_client, "ccxt", types.SimpleNamespace(bybit=fake_cls))
    client = exchange_client.ExchangeClient("bybit", make_config())

    with pytest.raises(Exception, match="Invalid api-key"):
        await client.load_markets()
    assert client._tried_alt is False


async def test_exchange_without_alternate_reraises(monkeypatch):
    fake_cls, _ = make_fake_exchange(
        fail_main=True, error_message="Cannot connect to host api.kraken.com"
    )
    monkeypatch.setattr(exchange_client, "ccxt", types.SimpleNamespace(kraken=fake_cls))
    cfg = make_config()
    cfg.exchanges = ["kraken"]
    cfg.api_keys = {"kraken": {"apiKey": "", "secret": "", "password": ""}}
    client = exchange_client.ExchangeClient("kraken", cfg)

    with pytest.raises(Exception, match="Cannot connect"):
        await client.load_markets()
    assert client._alt_hostname is None
