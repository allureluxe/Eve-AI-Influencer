"""Les reglages proposes par les cerveaux sont remis dans l'unite du moteur.

3 oct. 2026 : un tiers des essais rendaient zero trade (percentiles en pour
cent, canal en nombre seul).
"""
from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.lab import normaliser_reglage


def test_percentile_en_pour_cent_devient_fraction():
    assert normaliser_reglage("min_atr_percentile", 60) == 0.60
    assert normaliser_reglage("max_atr_percentile", 35) == 0.35


def test_fraction_deja_juste_inchangee():
    assert normaliser_reglage("min_atr_percentile", 0.2) == 0.2


def test_canal_nombre_seul_devient_liste():
    assert normaliser_reglage("donchian_entrees", 55) == (55,)
    assert normaliser_reglage("donchian_entrees", [10, 20]) == (10, 20)


def test_autres_reglages_inchanges():
    assert normaliser_reglage("trail_atr_mult", 3.5) == 3.5
