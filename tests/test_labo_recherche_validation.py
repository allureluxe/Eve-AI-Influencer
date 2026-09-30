from ops.labo_recherche import FAMILLES_EXECUTABLES, _empreinte_idee, valider


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
    assert FAMILLES_EXECUTABLES == {"tendance", "momentum", "donchian", "reversion", "volatilite", "risque", "filtre", "sortie"}


def test_empreinte_identifie_une_meme_experience_independamment_de_l_ordre():
    a = {"famille": "momentum", "params": {"min_adx": 20, "donchian_entrees": [20]}}
    b = {"famille": "momentum", "params": {"donchian_entrees": [20], "min_adx": 20}}
    assert _empreinte_idee(a) == _empreinte_idee(b)


def test_empreinte_change_quand_un_reglage_change():
    a = {"famille": "momentum", "params": {"min_adx": 20}}
    b = {"famille": "momentum", "params": {"min_adx": 25}}
    assert _empreinte_idee(a) != _empreinte_idee(b)
