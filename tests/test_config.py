"""Tests for config loading and validation (bot/config.py)."""
import textwrap

import pytest

from bot.config import Config, LoggingConfig, load_config


def write_config(tmp_path, body: str):
    path = tmp_path / "config.yaml"
    path.write_text(textwrap.dedent(body))
    return path


def test_loads_valid_config(tmp_path, monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "k1")
    monkeypatch.setenv("BINANCE_API_SECRET", "s1")
    path = write_config(
        tmp_path,
        """
        dry_run: true
        scan_interval_seconds: 5
        exchanges:
          - binance
          - kraken
        pairs:
          - BTC/USDT
        min_profit_threshold: 0.01
        max_trade_size_quote: 200
        request_timeout_seconds: 25
        """,
    )
    config = load_config(path)
    assert isinstance(config, Config)
    assert config.dry_run is True
    assert config.scan_interval_seconds == 5
    assert config.exchanges == ["binance", "kraken"]
    assert config.pairs == ["BTC/USDT"]
    assert config.min_profit_threshold == 0.01
    assert config.max_trade_size_quote == 200
    assert config.request_timeout_seconds == 25
    # API keys are pulled from the environment by exchange prefix.
    assert config.api_keys["binance"] == {"apiKey": "k1", "secret": "s1", "password": ""}
    # Unset exchange still gets a (blank) entry rather than missing.
    assert config.api_keys["kraken"] == {"apiKey": "", "secret": "", "password": ""}


def test_applies_sane_defaults_when_optional_fields_missing(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - binance
          - kraken
        pairs:
          - BTC/USDT
        """,
    )
    config = load_config(path)
    assert config.dry_run is True  # safe default: never trade unless told to
    assert config.scan_interval_seconds == 10
    assert config.min_profit_threshold == 0.005
    assert config.max_trade_size_quote == 100
    assert config.request_timeout_seconds == 60.0
    assert isinstance(config.logging, LoggingConfig)


def test_empty_file_is_rejected_with_clear_message(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("")
    with pytest.raises(ValueError, match="vide ou invalide"):
        load_config(path)


def test_malformed_yaml_is_rejected(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("exchanges: [binance, kraken\npairs: oops")
    with pytest.raises(ValueError, match="mal forme"):
        load_config(path)


def test_requires_at_least_two_exchanges(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - binance
        pairs:
          - BTC/USDT
        """,
    )
    with pytest.raises(ValueError, match="au moins 2 exchanges"):
        load_config(path)


def test_rejects_duplicate_exchanges(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - binance
          - binance
        pairs:
          - BTC/USDT
        """,
    )
    with pytest.raises(ValueError, match="2 exchanges differents"):
        load_config(path)


def test_normalizes_exchange_case_and_whitespace(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - " Binance "
          - KRAKEN
        pairs:
          - btc/usdt
        """,
    )
    config = load_config(path)
    assert config.exchanges == ["binance", "kraken"]
    assert config.pairs == ["BTC/USDT"]


def test_requires_at_least_one_pair(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - binance
          - kraken
        pairs: []
        """,
    )
    with pytest.raises(ValueError, match="au moins une paire"):
        load_config(path)


def test_rejects_malformed_pairs(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - binance
          - kraken
        pairs:
          - BTCUSDT
        """,
    )
    with pytest.raises(ValueError, match="mal formees"):
        load_config(path)


def test_rejects_non_numeric_timeout(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - binance
          - kraken
        pairs:
          - BTC/USDT
        request_timeout_seconds: abc
        """,
    )
    with pytest.raises(ValueError, match="doit etre un nombre"):
        load_config(path)


def test_rejects_non_positive_timeout(tmp_path):
    path = write_config(
        tmp_path,
        """
        exchanges:
          - binance
          - kraken
        pairs:
          - BTC/USDT
        request_timeout_seconds: 0
        """,
    )
    with pytest.raises(ValueError, match="superieur a 0"):
        load_config(path)


def test_credentials_for_raises_when_missing():
    config = Config(
        dry_run=False,
        scan_interval_seconds=10,
        exchanges=["binance"],
        pairs=["BTC/USDT"],
        min_profit_threshold=0.005,
        max_trade_size_quote=100,
        max_balance_fraction_per_trade=1.0,
        max_slippage=0.002,
        logging=LoggingConfig(),
        api_keys={"binance": {"apiKey": "", "secret": ""}},
    )
    with pytest.raises(ValueError, match="Missing API credentials"):
        config.credentials_for("binance")


def test_credentials_for_returns_when_present():
    config = Config(
        dry_run=False,
        scan_interval_seconds=10,
        exchanges=["binance"],
        pairs=["BTC/USDT"],
        min_profit_threshold=0.005,
        max_trade_size_quote=100,
        max_balance_fraction_per_trade=1.0,
        max_slippage=0.002,
        logging=LoggingConfig(),
        api_keys={"binance": {"apiKey": "k", "secret": "s"}},
    )
    assert config.credentials_for("binance") == {"apiKey": "k", "secret": "s"}


def _config_with(api_keys):
    return Config(
        dry_run=False,
        scan_interval_seconds=10,
        exchanges=list(api_keys),
        pairs=["BTC/USDT"],
        min_profit_threshold=0.005,
        max_trade_size_quote=100,
        max_balance_fraction_per_trade=1.0,
        max_slippage=0.002,
        logging=LoggingConfig(),
        api_keys=api_keys,
    )


def test_passphrase_read_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("KUCOIN_API_KEY", "k")
    monkeypatch.setenv("KUCOIN_API_SECRET", "s")
    monkeypatch.setenv("KUCOIN_API_PASSPHRASE", "p")
    path = write_config(
        tmp_path,
        """
        exchanges:
          - kucoin
          - binance
        pairs:
          - BTC/USDT
        """,
    )
    config = load_config(path)
    assert config.api_keys["kucoin"] == {"apiKey": "k", "secret": "s", "password": "p"}


def test_kucoin_requires_passphrase():
    config = _config_with({"kucoin": {"apiKey": "k", "secret": "s", "password": ""}})
    with pytest.raises(ValueError, match="passphrase"):
        config.credentials_for("kucoin")


def test_kucoin_ok_with_passphrase():
    config = _config_with({"kucoin": {"apiKey": "k", "secret": "s", "password": "p"}})
    assert config.credentials_for("kucoin")["password"] == "p"


def test_binance_does_not_require_passphrase():
    config = _config_with({"binance": {"apiKey": "k", "secret": "s", "password": ""}})
    # No passphrase needed for Binance — must not raise.
    assert config.credentials_for("binance")["apiKey"] == "k"
