"""Guard that the wizard's generated config.yaml is always loadable.

This is the seam most likely to break silently: if someone changes the
config template or the loader's required fields, this test fails instead of
the user discovering it when the bot won't start.
"""
import setup_wizard
from bot.config import load_config
from setup_wizard import parse_exchange_selection, parse_pair_selection


def test_pairs_select_by_numbers():
    assert parse_pair_selection("1,2") == ["BTC/USDT", "ETH/USDT"]


def test_pairs_select_by_range():
    assert parse_pair_selection("1-3") == ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


def test_pairs_select_all():
    assert parse_pair_selection("tous") == setup_wizard.POPULAR_PAIRS


def test_pairs_custom_typed():
    assert parse_pair_selection("btc/usdt, sol/usdt") == ["BTC/USDT", "SOL/USDT"]


def test_pairs_custom_invalid_format():
    assert parse_pair_selection("BTCUSDT") is None


def test_pairs_number_out_of_range():
    assert parse_pair_selection("999") is None


def test_pairs_empty_is_none():
    assert parse_pair_selection("") is None


def test_automatic_mode_watches_all_popular_and_auto_focuses(monkeypatch):
    # User picks option "1" (Automatic): universe = all popular pairs, and
    # top_movers is enabled without them having to type "tous" or a number.
    monkeypatch.setattr(setup_wizard, "ask_choice", lambda *a, **k: "1")
    pairs, top_movers = setup_wizard.choose_pairs_and_focus()
    assert pairs == setup_wizard.POPULAR_PAIRS
    assert top_movers == setup_wizard.AUTO_TOP_MOVERS


def test_manual_mode_uses_chosen_pairs(monkeypatch):
    monkeypatch.setattr(setup_wizard, "ask_choice", lambda *a, **k: "2")
    monkeypatch.setattr(setup_wizard, "choose_pairs", lambda: ["BTC/USDT", "ETH/USDT"])
    monkeypatch.setattr(setup_wizard, "choose_top_movers", lambda n: 0)
    pairs, top_movers = setup_wizard.choose_pairs_and_focus()
    assert pairs == ["BTC/USDT", "ETH/USDT"]
    assert top_movers == 0


def test_choose_top_movers_yes_enables_automatic(monkeypatch):
    monkeypatch.setattr(setup_wizard, "ask", lambda *a, **k: "o")
    assert setup_wizard.choose_top_movers(19) == 8  # follows the 8 most volatile


def test_choose_top_movers_no_keeps_all(monkeypatch):
    monkeypatch.setattr(setup_wizard, "ask", lambda *a, **k: "n")
    assert setup_wizard.choose_top_movers(19) == 0


def test_choose_top_movers_skips_when_few_pairs():
    # 3 or fewer pairs: nothing to narrow, no question asked.
    assert setup_wizard.choose_top_movers(3) == 0


def test_read_secret_uses_visible_input_in_git_bash(monkeypatch):
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    monkeypatch.setattr("builtins.input", lambda prompt="": "  mykey  ")
    # Must NOT call getpass (broken in Git Bash) — use input and strip.
    monkeypatch.setattr(
        setup_wizard.getpass, "getpass", lambda *a, **k: (_ for _ in ()).throw(AssertionError("getpass used"))
    )
    assert setup_wizard.read_secret("Cle : ") == "mykey"


def test_read_secret_uses_getpass_outside_git_bash(monkeypatch):
    monkeypatch.delenv("MSYSTEM", raising=False)
    monkeypatch.setattr(setup_wizard.getpass, "getpass", lambda *a, **k: "  secret  ")
    assert setup_wizard.read_secret("Cle : ") == "secret"


def test_read_secret_falls_back_to_input_if_getpass_fails(monkeypatch):
    monkeypatch.delenv("MSYSTEM", raising=False)
    monkeypatch.setattr(
        setup_wizard.getpass, "getpass", lambda *a, **k: (_ for _ in ()).throw(OSError("no tty"))
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "typed")
    assert setup_wizard.read_secret("Cle : ") == "typed"


def test_default_pairs_are_valid_and_broad():
    # More than just BTC/ETH, and all well-formed.
    assert len(setup_wizard.DEFAULT_PAIRS) >= 3
    for pair in setup_wizard.DEFAULT_PAIRS:
        assert len(pair.split("/")) == 2


def test_select_multiple_by_comma():
    assert parse_exchange_selection("1,2") == ["binance", "kraken"]


def test_select_by_range():
    assert parse_exchange_selection("1-3") == ["binance", "kraken", "coinbase"]


def test_select_all_keyword():
    all_ids = [eid for eid, _ in setup_wizard.SUPPORTED_EXCHANGES]
    result = parse_exchange_selection("tous")
    assert result == all_ids
    assert parse_exchange_selection("all") == result


def test_all_supported_exchanges_are_valid_ccxt_ids():
    import ccxt.pro as ccxtpro

    available = set(ccxtpro.exchanges)
    for eid, _ in setup_wizard.SUPPORTED_EXCHANGES:
        assert eid in available, f"{eid} is not a valid ccxt.pro exchange id"
        assert getattr(ccxtpro, eid)().has.get("watchTicker"), f"{eid} lacks watchTicker"


def test_select_dedupes_and_keeps_order():
    assert parse_exchange_selection("2,1,2") == ["kraken", "binance"]


def test_select_rejects_fewer_than_two():
    assert parse_exchange_selection("1") is None


def test_select_rejects_out_of_range():
    assert parse_exchange_selection("1,99") is None


def test_select_rejects_garbage():
    assert parse_exchange_selection("abc") is None


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
