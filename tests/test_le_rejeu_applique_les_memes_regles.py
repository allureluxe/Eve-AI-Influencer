"""Le rejeu applique-t-il les MEMES portes que le robot reel ?

TROIS FOIS QUE CE PIEGE SE REFERME DANS CE DEPOT.

  1. L'espacement de pyramide ne s'executait jamais dans le moteur reel
     alors que le rejeu l'appliquait : « le rejeu mesurait une regle que
     le robot n'appliquait pas » (CLAUDE.md, 6 septembre).
  2. Le delai de carence vivait dans `check_exposure`, que le rejeu
     n'appelle pas. Premiere mesure : des chiffres IDENTIQUES au temoin,
     et on a failli conclure que la carence ne servait a rien.
  3. Le 20 septembre, la limite par famille de cryptos : faire varier
     `max_per_correlation_group` de 99 a 1 rendait QUATRE FOIS le meme
     resultat, au centime. Elle ne s'executait pas non plus.

A chaque fois le symptome est le meme -- un reglage qui « ne change
rien » -- et la cause aussi. Ce fichier existe pour qu'il n'y ait pas
de quatrieme fois.
"""
import inspect

import pytest

from gold_bot.backtest import Backtester
from gold_bot.risk import RiskManager


#: Les portes d'entree du gestionnaire de risque. Chacune DOIT etre
#: traversee par le rejeu, sinon il mesure une strategie plus permissive
#: que celle qui tourne.
PORTES_OBLIGATOIRES = (
    ("can_trade", "coupe-circuits, nombre de trades du jour, delai entre trades"),
    ("check_exposure", "limite par famille de cryptos, carence apres sortie"),
    ("size_position", "budget de risque, cout d'execution, cash disponible"),
    ("peut_renforcer", "conditions d'ajout d'un etage de pyramide"),
)


class TestLeRejeuTraverseLesMEMESPortes:
    @pytest.mark.parametrize("porte,role", PORTES_OBLIGATOIRES)
    def test_la_porte_est_appelee_par_le_rejeu(self, porte, role):
        source = inspect.getsource(Backtester.preparer)
        assert f"risk.{porte}(" in source, (
            f"le rejeu n'appelle pas `{porte}` ({role}).\n"
            f"Il mesurera donc une strategie PLUS PERMISSIVE que celle qui "
            f"tourne, et tout reglage porte par cette fonction semblera "
            f"« ne rien changer ».")

    def test_aucune_porte_d_entree_n_a_ete_oubliee(self):
        """Si le gestionnaire de risque gagne une nouvelle porte, ce test
        la signale au lieu de la laisser passer en silence."""
        attendues = {p for p, _ in PORTES_OBLIGATOIRES}
        publiques = {
            nom for nom, _ in inspect.getmembers(RiskManager, inspect.isfunction)
            if not nom.startswith("_")
        }
        # Les fonctions qui ne sont pas des portes d'entree.
        hors_sujet = {
            "sync_account", "record_close", "record_open", "effective_risk_pct",
            "open_risk_pct", "carence_restante", "reset_day", "daily_pnl_pct",
            "note_trade", "halt", "resume", "is_halted", "snapshot",
            "appliquer_retrait", "appliquer_apport", "recaler",
            # Mouvement de tresorerie, appele par le moteur quand la
            # plateforme confirme un retrait -- pas une porte d'entree.
            "absorber_retrait",
            # Calculs de cout, utilises A L'INTERIEUR de `size_position`
            # (verifie : risk.py lignes 1099 et 1168). Les brancher a
            # part les appliquerait deux fois.
            "cost_ratio_for", "execution_cost",
        }
        inconnues = publiques - attendues - hors_sujet
        assert not inconnues, (
            f"nouvelles fonctions publiques du gestionnaire de risque : "
            f"{sorted(inconnues)}.\nSi l'une est une PORTE D'ENTREE, "
            f"ajoutez-la a PORTES_OBLIGATOIRES et branchez-la dans le "
            f"rejeu -- sinon ajoutez-la a `hors_sujet` en disant pourquoi.")


class TestLaLimitePARFAMILLESExecuteVRAIMENT:
    """Le cas precis du 20 septembre."""

    def test_elle_refuse_une_deuxieme_crypto_de_la_meme_famille(self):
        from gold_bot.core import Position, Side
        from gold_bot.universe import Universe

        u = Universe()
        cfg = RiskManager(__import__("gold_bot.risk", fromlist=["RiskConfig"])
                          .RiskConfig(max_per_correlation_group=1))
        cfg.sync_account(3300.0, 3300.0, "EUR")

        # Deux cryptos de la MEME famille.
        familles = {}
        for inst in u:
            g = getattr(inst, "correlation_group", "")
            if g:
                familles.setdefault(g, []).append(inst)
        paire = next(v for v in familles.values() if len(v) >= 2)
        deja, candidate = paire[0], paire[1]

        ouverte = Position(id="1", symbol=deja.symbol, side=Side.BUY,
                           volume=1.0, entry_price=100.0, stop_loss=90.0,
                           take_profit=120.0, opened_at=0.0)
        ok, motif = cfg.check_exposure(candidate, Side.BUY, [ouverte], u.get)
        assert ok is False, (
            f"{candidate.symbol} accepte alors que {deja.symbol} est deja "
            f"ouverte dans la meme famille « {candidate.correlation_group} »")
        assert "correle" in motif
