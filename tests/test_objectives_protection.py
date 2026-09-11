"""On ne protege que ce qu'on a ENCORE.

Defaut mesure le 11 septembre 2026. `achieved_this_week` est un cliquet :
une fois l'objectif de la semaine touche, il ne redescend jamais. C'est
juste pour la PROMOTION de palier — la semaine a bel et bien atteint sa
cible, et rendre ensuite ne l'efface pas.

Pour le RISQUE, le cliquet produisait une absurdite. Objectif touche en
debut de semaine (KAVA +5,56 EUR puis LSK +4,48), puis trois stops :
resultat de la semaine -0,37 EUR. Le robot etait toujours en « mode
preservation » et divisait son risque par DEUX — 0,26 % au lieu de
0,60 %, positions de 5 EUR refusees par le plancher — pour proteger un
gain qu'il n'avait plus.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.objectives import ObjectiveTracker


def _suivi(tmp_path, realise: float, atteint: bool) -> ObjectiveTracker:
    t = ObjectiveTracker(state_file=str(tmp_path / "obj.json"))
    t.state.week_start_equity = 300.0
    t.state.realized_this_week = realise
    t.state.achieved_this_week = atteint
    t.state.trades_this_week = 4
    return t


class TestLaPreservationSuitLeGainReel:

    def test_gain_encore_la_on_preserve(self, tmp_path):
        t = _suivi(tmp_path, realise=999.0, atteint=True)
        mult, why = t.risk_multiplier()
        assert mult == t.config.protect_multiplier, why
        assert "preservation" in why

    def test_gain_rendu_on_ne_preserve_plus(self, tmp_path):
        """Le cas du 11 septembre : objectif touche, puis tout rendu."""
        t = _suivi(tmp_path, realise=-0.37, atteint=True)
        mult, why = t.risk_multiplier()
        assert "preservation" not in why, (
            f"le robot protege encore ({why}) alors que la semaine vaut "
            f"{t.state.realized_this_week:+.2f} : il n'y a plus rien a garder")

    def test_le_cliquet_reste_pour_la_promotion(self, tmp_path):
        """Le drapeau lui-meme ne doit PAS etre efface.

        La semaine a atteint sa cible : c'est un fait, et la promotion de
        palier s'en sert. Seul le calcul du RISQUE cesse d'y obeir.
        """
        t = _suivi(tmp_path, realise=-0.37, atteint=True)
        t.risk_multiplier()
        assert t.state.achieved_this_week is True, (
            "le drapeau a ete efface : la semaine perdrait sa promotion")

    def test_une_semaine_negative_reduit_quand_meme(self, tmp_path):
        """Sans preservation, la branche « semaine negative » prend le relais."""
        t = _suivi(tmp_path, realise=-0.37, atteint=True)
        mult, _ = t.risk_multiplier()
        assert 0 < mult <= 1.0, f"multiplicateur aberrant : {mult}"
        assert mult >= t.config.min_multiplier
