from gold_bot.lab import MIN_TRADES, MIN_FORWARD_TRADES

def test_forward_window_has_un_seuil_distinct_du_backtest():
    assert MIN_TRADES >= 100
    assert 10 <= MIN_FORWARD_TRADES < MIN_TRADES
