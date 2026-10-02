"""Le Lab ne doit plus mourir de faim, la recherche ne doit plus couper.

2 oct. 2026 : un candidat M5 chargeait 180 jours de M5 pour ~245 cryptos
(tue par le plafond memoire, 16 h sans resultat) ; ChatGPT coupait a 90 s
une reponse de 12 000 jetons, facturee quand meme.
"""
from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot import lab
from gold_bot.datasources.base import tf_seconds
from luna import cerveaux


def test_les_series_rapides_sont_bornees_en_bougies():
    for tf in ("M5", "M15", "H1", "H4", "D1"):
        bougies = lab._lab_jours(tf) * 86400 / tf_seconds(tf)
        assert bougies <= lab.LAB_MAX_BARS + 288, f"{tf} : {bougies:.0f} bougies"


def test_les_unites_lentes_gardent_toute_la_periode():
    assert lab._lab_jours("D1") == lab.LAB_HISTORY_DAYS


def test_le_delai_suit_la_longueur_demandee():
    assert cerveaux._delai_pour(1200) == cerveaux.DELAI
    assert cerveaux._delai_pour(12000) >= 300
    assert cerveaux._delai_pour(10**6) <= 600
