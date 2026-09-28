from ops.labo_recherche import FAMILLES_EXECUTABLES, valider


def test_famille_macro_nest_pas_executée_implicitement():
    idee, raison = valider({
        "titre": "macro test",
        "famille": "macro",
        "params": {"min_adx": 20},
    }, {"min_adx"})
    assert idee is not None
    assert raison == "FEATURE_REQUIRED"
    assert idee["famille"] == "macro"


def test_famille_vide_nest_pas_convertie_en_tendance():
    idee, raison = valider({
        "titre": "hypothese sans famille",
        "params": {"min_adx": 20},
    }, {"min_adx"})
    assert idee is not None
    assert raison == "FEATURE_REQUIRED"
    assert idee["famille"] == "inconnu"


def test_famille_executable_conserve_les_reglages_connus():
    idee, raison = valider({
        "titre": "momentum test",
        "famille": "momentum",
        "params": {"momentum_formation": 14, "param_inconnu": 123},
    }, {"momentum_formation"})
    assert raison == ""
    assert idee["params"] == {"momentum_formation": 14}


def test_liste_des_familles_est_explicitement_bornee():
    assert FAMILLES_EXECUTABLES == {"tendance", "momentum", "donchian", "reversion"}
