"""Luna change de tenue d'un Reel à l'autre, jamais au milieu d'un Reel (10 oct.)."""
from __future__ import annotations

from helpers import *  # noqa: F401,F403

import alluxe_ia.luna_tenues as T


def test_une_tenue_par_reel_et_jamais_une_recente(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "REGISTRE", tmp_path / "tenues.json")
    vues = []
    for n in range(T.DERNIERS_A_EVITER + 3):
        cle = T.choisir(f"reel-{n}")
        assert cle not in vues[-T.DERNIERS_A_EVITER:], "tenue remise trop tôt"
        assert T.choisir(f"reel-{n}") == cle, "la tenue change au milieu d'un Reel"
        vues.append(cle)
    assert vues[0] != "sweat_noir", "le sweat noir des deux derniers Reels revient"


def test_le_texte_commun_recoit_la_tenue(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "REGISTRE", tmp_path / "tenues.json")
    from alluxe_ia.reel_luna_ecrans import COMMUN
    texte = T.avec_tenue(COMMUN, "reel-neuf")
    assert T.PAR_DEFAUT not in texte
    assert T.TENUES[T.choisir("reel-neuf")] in texte
