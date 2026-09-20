"""Le resume affiche sur chaque onglet doit DISTINGUER les comptes.

Demande de l'operateur le 20 septembre : « 3 onglets dans le mode demo
[...] et le nom de la methode utilisee ». Trois onglets qui affichent la
meme phrase ne selectionnent rien.

C'est arrive le jour meme : les comptes 1 et 3 ne different que par le
point mort, et ce reglage ne figurait pas dans le resume. Deux onglets
strictement identiques, pour deux robots qui font autre chose.
"""
import os

import pytest

from gold_bot.methode import phrase_methode, resume_methode
from gold_bot.settings import BotConfig

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPTES = ["robot.demo.json", "robot.demo2.json", "robot.demo3.json"]


def _cfg(nom):
    return BotConfig.load(os.path.join(RACINE, nom))


class TestChaqueCompteALeSienEtIlEstDIFFERENT:
    def test_les_trois_resumes_sont_distincts(self):
        resumes = {nom: resume_methode(_cfg(nom)) for nom in COMPTES}
        assert len(set(resumes.values())) == 3, (
            "deux comptes affichent la meme phrase :\n  "
            + "\n  ".join(f"{n} : {r}" for n, r in resumes.items()))

    @pytest.mark.parametrize("nom", COMPTES)
    def test_les_trois_partent_du_meme_capital(self, nom):
        """Decision de l'operateur : « les 3 comptes doivent avoir une
        mise de depart de 3300 € ». Des capitaux differents rendraient
        les resultats incomparables."""
        assert _cfg(nom).engine.start_balance == 3300.0


class TestLeResumeSuitLesREGLAGES:
    """Il est DEDUIT, jamais ecrit a la main -- c'est ce qui avait fait
    afficher « canal 20 jours » pendant une semaine."""

    def test_le_canal_arme_apparait(self):
        cfg = _cfg("robot.demo.json")
        assert f"Canal {min(cfg.strategy.donchian_entrees)} j" in resume_methode(cfg)

    def test_la_reserve_apparait_et_se_lit_en_francais(self):
        assert "⅓" in resume_methode(_cfg("robot.demo.json"))
        assert "rien de réservé" in resume_methode(_cfg("robot.demo2.json"))

    def test_le_point_mort_apparait(self):
        assert "0,5" in resume_methode(_cfg("robot.demo3.json"))
        assert "0,7" in resume_methode(_cfg("robot.demo.json"))

    def test_un_reglage_modifie_change_le_resume(self):
        cfg = _cfg("robot.demo.json")
        avant = resume_methode(cfg)
        cfg.risk.pyramide_max = 3
        assert resume_methode(cfg) != avant


class TestAucunJargonDansCeQueLOperateurLIT:
    """Regle permanente du depot : parler en euros et en francais
    courant. Un mot qu'il ne comprend pas le fait douter du reste."""

    @pytest.mark.parametrize("nom", COMPTES)
    def test_ni_R_ni_ATR_ni_breakeven_dans_le_resume(self, nom):
        r = resume_methode(_cfg(nom))
        for jargon in ("breakeven", "ATR", " R ", "R-multiple", "drawdown"):
            assert jargon.lower() not in r.lower(), (
                f"« {jargon} » apparait dans « {r} »")
