from gold_bot.lab import famille_execution, reglages_sans_effet

def test_categorie_risque_est_traduite_en_famille_strategy_valide():
    p={"famille":"risque","strategie_famille":"tendance","min_rr":2.1}
    assert famille_execution(p)=="tendance"
    assert reglages_sans_effet(p, famille_execution(p)) == []

def test_categorie_volatilite_est_traduite_en_tendance():
    p={"famille":"volatilite","min_atr_percentile":0.2,"max_atr_percentile":0.9}
    assert famille_execution(p)=="tendance"
