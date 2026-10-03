from gold_bot.lab import MIN_FORWARD_TRADES, MIN_PAYOFF, MIN_PF, MIN_TRADES, MIN_WIN


def test_forward_window_has_un_seuil_distinct_du_backtest():
    # 100 -> 50 le 3 oct. 2026 (voir gold_bot/lab.py) ; jamais sous la
    # regle des 40 trades de CLAUDE.md.
    assert MIN_TRADES >= 40
    assert 10 <= MIN_FORWARD_TRADES < MIN_TRADES


def test_une_methode_de_tendance_n_est_pas_rejetee_d_office():
    """35 % de reussite, gain moyen 2,6x : PF 1,4 -- le profil du reel."""
    reussite, payoff = 35.0, 2.6
    pf = (reussite / 100 * payoff) / (1 - reussite / 100)
    assert pf >= MIN_PF
    assert reussite >= MIN_WIN and payoff > MIN_PAYOFF, (
        "un seuil de reussite rejetterait la famille qui tourne en reel")
