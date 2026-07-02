"""Guard that the wizard's generated config.yaml is always loadable.

This is the seam most likely to break silently: if someone changes the
config template or the loader's required fields, this test fails instead of
the user discovering it when the bot won't start.
"""
import setup_wizard
from bot.config import load_config


def test_generated_config_loads_back(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "ROOT_DIR", tmp_path)
    setup_wizard.write_config(
        dry_run=True,
        exchanges=["binance", "kraken"],
        pairs=["BTC/USDT", "ETH/USDT"],
        max_trade_size_quote=250.0,
    )
    config = load_config(tmp_path / "config.yaml")
    assert config.dry_run is True
    assert config.exchanges == ["binance", "kraken"]
    assert config.pairs == ["BTC/USDT", "ETH/USDT"]
    assert config.max_trade_size_quote == 250.0
    # The timeout field added for slow connections must survive the round-trip.
    assert config.request_timeout_seconds == 60


def test_generated_config_live_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "ROOT_DIR", tmp_path)
    setup_wizard.write_config(
        dry_run=False,
        exchanges=["binance", "coinbase"],
        pairs=["BTC/USDT"],
        max_trade_size_quote=50.0,
    )
    config = load_config(tmp_path / "config.yaml")
    assert config.dry_run is False


def test_write_env_round_trips_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "ROOT_DIR", tmp_path)
    setup_wizard.write_env({"binance": ("mykey", "mysecret", "")})
    content = (tmp_path / ".env").read_text()
    assert "BINANCE_API_KEY=mykey" in content
    assert "BINANCE_API_SECRET=mysecret" in content
    # Binance has no passphrase line.
    assert "PASSPHRASE" not in content


def test_write_env_writes_passphrase_for_kucoin(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "ROOT_DIR", tmp_path)
    setup_wizard.write_env({"kucoin": ("k", "s", "myphrase")})
    content = (tmp_path / ".env").read_text()
    assert "KUCOIN_API_KEY=k" in content
    assert "KUCOIN_API_SECRET=s" in content
    assert "KUCOIN_API_PASSPHRASE=myphrase" in content


def test_write_env_accepts_legacy_two_tuple(tmp_path, monkeypatch):
    monkeypatch.setattr(setup_wizard, "ROOT_DIR", tmp_path)
    setup_wizard.write_env({"binance": ("k", "s")})  # old 2-tuple still works
    content = (tmp_path / ".env").read_text()
    assert "BINANCE_API_KEY=k" in content
