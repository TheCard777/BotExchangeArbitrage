from bot.scanner import find_opportunities, net_profit_fraction


def test_net_profit_fraction_positive_spread():
    profit = net_profit_fraction(buy_price=100, sell_price=102, buy_fee=0.001, sell_fee=0.001)
    assert profit > 0
    assert round(profit, 4) == round((102 * 0.999 - 100 * 1.001) / (100 * 1.001), 4)


def test_net_profit_fraction_fees_can_erase_spread():
    profit = net_profit_fraction(buy_price=100, sell_price=100.05, buy_fee=0.001, sell_fee=0.001)
    assert profit < 0


def test_net_profit_fraction_zero_buy_price():
    assert net_profit_fraction(buy_price=0, sell_price=100, buy_fee=0.001, sell_fee=0.001) == 0.0


def test_find_opportunities_filters_by_threshold():
    tickers = {
        "binance": {"BTC/USDT": 100.0},
        "kraken": {"BTC/USDT": 102.0},
    }
    fees = {
        "binance": {"BTC/USDT": 0.001},
        "kraken": {"BTC/USDT": 0.001},
    }

    opportunities = find_opportunities(tickers, fees, ["BTC/USDT"], min_profit_threshold=0.005)
    assert len(opportunities) == 1
    opp = opportunities[0]
    assert opp.buy_exchange == "binance"
    assert opp.sell_exchange == "kraken"
    assert opp.net_profit_fraction >= 0.005


def test_find_opportunities_respects_threshold_when_spread_too_small():
    tickers = {
        "binance": {"BTC/USDT": 100.0},
        "kraken": {"BTC/USDT": 100.05},
    }
    fees = {
        "binance": {"BTC/USDT": 0.001},
        "kraken": {"BTC/USDT": 0.001},
    }

    opportunities = find_opportunities(tickers, fees, ["BTC/USDT"], min_profit_threshold=0.005)
    assert opportunities == []


def test_find_opportunities_sorted_best_first():
    tickers = {
        "a": {"BTC/USDT": 100.0},
        "b": {"BTC/USDT": 110.0},
        "c": {"BTC/USDT": 105.0},
    }
    fees = {eid: {"BTC/USDT": 0.0} for eid in tickers}

    opportunities = find_opportunities(tickers, fees, ["BTC/USDT"], min_profit_threshold=0.0)
    assert opportunities[0].buy_exchange == "a"
    assert opportunities[0].sell_exchange == "b"
    assert opportunities[0].net_profit_fraction >= opportunities[1].net_profit_fraction
