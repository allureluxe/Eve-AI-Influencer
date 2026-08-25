"""Microstructure et ponderation adaptative.

Ces deux modules viennent d'un robot tiers dont le code d'execution etait
inutilisable. Les tests portent d'abord sur les defauts qui rendaient ce
code inoperant chez lui — ils ne doivent pas revenir chez nous.
"""
from __future__ import annotations

import json
from collections import deque

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.apprentissage import (MINIMUM_OBSERVATIONS, PoidsAdaptatifs,
                                    alimenter_depuis_journal, famille_du_trade)
from gold_bot.core import Candle, Tick
from gold_bot.microstructure import (balayage_de_liquidite, desequilibre_carnet,
                                     desequilibre_flux)


def bougie(o, h, l, c, ts=0):
    return Candle(ts, o, h, l, c, 10.0)


# ==========================================================================
class TestDesequilibreCarnet:
    def test_pression_acheteuse(self):
        assert desequilibre_carnet(9.0, 1.0) == pytest.approx(0.8)

    def test_pression_vendeuse(self):
        assert desequilibre_carnet(1.0, 9.0) == pytest.approx(-0.8)

    def test_equilibre(self):
        assert desequilibre_carnet(5.0, 5.0) == 0.0

    def test_carnet_vide_ne_divise_pas_par_zero(self):
        assert desequilibre_carnet(0.0, 0.0) == 0.0

    def test_valeurs_negatives_ignorees(self):
        assert desequilibre_carnet(-3.0, 5.0) == pytest.approx(-1.0)


# ==========================================================================
class TestDesequilibreFlux:
    def test_un_deque_ne_fait_pas_planter(self):
        """Regression : le robot d'origine plantait des le premier trade.

        Il decoupait directement la sequence — `trades[-100:]` — alors que
        `recent_trades` etait un deque, qui ne supporte pas le decoupage.
        TypeError a chaque evaluation, donc aucune decision possible.
        """
        flux = deque([(100.0, 2.0, "buy"), (100.0, 1.0, "sell")], maxlen=10)
        assert desequilibre_flux(flux) == pytest.approx(1.0 / 3.0)

    def test_flux_acheteur(self):
        assert desequilibre_flux([(1, 8.0, "buy"), (1, 2.0, "sell")]) == pytest.approx(0.6)

    def test_lignes_malformees_ignorees(self):
        """Une ligne cassee ne doit pas faire tomber tout le calcul."""
        flux = [(1, 5.0, "buy"), ("incomplet",), (1, "abc", "sell"), (1, 5.0, "sell")]
        assert desequilibre_flux(flux) == 0.0

    def test_vide(self):
        assert desequilibre_flux([]) == 0.0

    def test_fenetre_respectee(self):
        flux = [(1, 1.0, "sell")] * 50 + [(1, 1.0, "buy")] * 10
        assert desequilibre_flux(flux, fenetre=10) == pytest.approx(1.0)


# ==========================================================================
class TestBalayageDeLiquidite:
    def test_balayage_du_creux_donne_un_signal_haussier(self):
        base = [bougie(100, 101, 99, 100, i) for i in range(12)]
        # La meche passe sous le creux puis la cloture revient au-dessus.
        base.append(bougie(100, 100.5, 96, 99.6, 12))
        base.append(bougie(99.6, 101, 99.5, 100.8, 13))
        sens, force, detail = balayage_de_liquidite(base, atr=1.0)
        assert sens == 1
        assert force > 0
        assert "creux" in detail

    def test_balayage_du_sommet_donne_un_signal_baissier(self):
        base = [bougie(100, 101, 99, 100, i) for i in range(12)]
        base.append(bougie(100, 104, 99.5, 100.4, 12))
        base.append(bougie(100.4, 100.6, 99, 99.2, 13))
        sens, force, _ = balayage_de_liquidite(base, atr=1.0)
        assert sens == -1
        assert force > 0

    def test_rejet_trop_faible_refuse(self):
        """Un retour minuscule est du bruit, pas un rejet."""
        base = [bougie(100, 101, 99, 100, i) for i in range(12)]
        base.append(bougie(100, 100.5, 98.9, 98.95, 12))
        base.append(bougie(98.95, 99.2, 98.9, 99.0, 13))
        sens, _, _ = balayage_de_liquidite(base, atr=1.0, rejet_minimum=0.35)
        assert sens == 0

    def test_marche_calme_ne_declenche_rien(self):
        base = [bougie(100, 101, 99, 100, i) for i in range(14)]
        assert balayage_de_liquidite(base, atr=1.0)[0] == 0

    def test_historique_court(self):
        assert balayage_de_liquidite([bougie(1, 1, 1, 1)], atr=1.0)[0] == 0

    def test_atr_nul(self):
        base = [bougie(100, 101, 99, 100, i) for i in range(14)]
        assert balayage_de_liquidite(base, atr=0.0)[0] == 0


# ==========================================================================
class TestTickTailles:
    def test_tailles_facultatives(self):
        """Une taille absente vaut None, jamais zero.

        Zero dirait « plus personne a l'achat » — une information forte et
        fausse. None dit « la source ne le precise pas ».
        """
        t = Tick(0.0, 100.0, 101.0)
        assert t.bid_size is None and t.ask_size is None

    def test_tailles_renseignees(self):
        t = Tick(0.0, 100.0, 101.0, 8.0, 2.0)
        assert desequilibre_carnet(t.bid_size, t.ask_size) == pytest.approx(0.6)


# ==========================================================================
class TestPoidsAdaptatifs:
    def test_poids_neutre_sous_le_seuil(self):
        """Sous vingt trades, on apprendrait le bruit."""
        p = PoidsAdaptatifs()
        for _ in range(MINIMUM_OBSERVATIONS - 1):
            p.observer("tendance_repli", 2.0)
        assert p.poids("tendance_repli") == 1.0
        assert not p.connue("tendance_repli")

    def test_famille_reguliere_gagnante_est_favorisee(self):
        p = PoidsAdaptatifs()
        for _ in range(40):
            p.observer("tendance_repli", 0.5)
        assert p.poids("tendance_repli") > 1.0
        assert p.connue("tendance_repli")

    def test_famille_perdante_est_penalisee(self):
        p = PoidsAdaptatifs()
        for _ in range(40):
            p.observer("retournement", -0.5)
        assert p.poids("retournement") < 1.0

    def test_poids_bornes(self):
        """Meme convaincu, le robot ne peut pas doubler la mise."""
        p = PoidsAdaptatifs()
        for _ in range(200):
            p.observer("parfait", 10.0)
        for _ in range(200):
            p.observer("catastrophe", -10.0)
        assert p.poids("parfait") <= p.plafond
        assert p.poids("catastrophe") >= p.plancher

    def test_regularite_privilegiee_sur_le_coup_de_chance(self):
        """Deux moyennes egales, mais l'une est un coup de chance."""
        regulier = PoidsAdaptatifs()
        chanceux = PoidsAdaptatifs()
        for _ in range(30):
            regulier.observer("regulier", 0.4)
        for i in range(30):
            chanceux.observer("chanceux", 12.4 if i == 0 else -0.0)
        assert regulier.poids("regulier") > chanceux.poids("chanceux")

    def test_famille_inconnue(self):
        assert PoidsAdaptatifs().poids("jamais_vue") == 1.0

    def test_rapport_trie(self):
        p = PoidsAdaptatifs()
        for _ in range(25):
            p.observer("bonne", 0.6)
            p.observer("mauvaise", -0.6)
        rapport = p.rapport()
        assert rapport[0]["famille"] == "bonne"
        assert rapport[0]["actif"] is True


# ==========================================================================
class TestAlimentationDepuisJournal:
    """Le chainon qui manquait au robot d'origine.

    Son `observe()` n'etait appele nulle part : le cerveau existait, rien
    ne le nourrissait, il ne pouvait donc rien apprendre.
    """

    def test_journal_lu_et_ponderation_alimentee(self, tmp_path):
        chemin = tmp_path / "trades.jsonl"
        with open(chemin, "w", encoding="utf-8") as fh:
            for _ in range(30):
                fh.write(json.dumps({"setup": "tendance_repli", "r_multiple": 0.8}) + "\n")
        p = PoidsAdaptatifs()
        assert alimenter_depuis_journal(p, str(chemin)) == 30
        assert p.poids("tendance_repli") > 1.0

    def test_fermetures_partielles_ignorees(self, tmp_path):
        """Un trade sorti en deux fois ne compte pas pour deux."""
        chemin = tmp_path / "trades.jsonl"
        with open(chemin, "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"setup": "a", "r_multiple": 1.0, "partial": True}) + "\n")
            fh.write(json.dumps({"setup": "a", "r_multiple": 1.0}) + "\n")
        p = PoidsAdaptatifs()
        assert alimenter_depuis_journal(p, str(chemin)) == 1

    def test_journal_absent(self, tmp_path):
        p = PoidsAdaptatifs()
        assert alimenter_depuis_journal(p, str(tmp_path / "rien.jsonl")) == 0
        assert p.poids("quoi") == 1.0

    def test_lignes_illisibles_ignorees(self, tmp_path):
        chemin = tmp_path / "trades.jsonl"
        chemin.write_text('{"setup":"a","r_multiple":1.0}\nPAS DU JSON\n\n')
        assert alimenter_depuis_journal(PoidsAdaptatifs(), str(chemin)) == 1

    def test_trade_sans_r_multiple_ignore(self, tmp_path):
        chemin = tmp_path / "trades.jsonl"
        chemin.write_text('{"setup":"a"}\n{"setup":"a","r_multiple":0.5}\n')
        assert alimenter_depuis_journal(PoidsAdaptatifs(), str(chemin)) == 1

    def test_famille_par_defaut(self):
        assert famille_du_trade({}) == "inconnu"
        assert famille_du_trade({"setup": "tendance_repli"}) == "tendance_repli"
        assert famille_du_trade({"comment": "quorum | 5 confirmations"}) == "quorum"


# ==========================================================================
class TestPonderationBranchee:
    """La difference avec le robot d'origine : elle influence les decisions.

    Chez eux, `observe()` n'etait appele nulle part — le cerveau existait
    mais ne recevait jamais rien. Ici on verifie la chaine entiere :
    journal -> ponderation -> classement des candidats.
    """

    def test_la_strategie_recoit_une_ponderation(self):
        from gold_bot.strategy import Strategy
        assert Strategy().poids.poids("crypto_major") == 1.0, \
            "sans historique, la ponderation doit etre neutre"

    def test_le_poids_modifie_la_priorite_pas_la_validite(self):
        """Garde-fou : la ponderation ne peut jamais valider un trade refuse.

        Elle departage des candidats deja valides quand les places sont
        limitees. Un robot qui ajuste seul son risque a partir de ses bons
        resultats augmente la mise juste avant de rendre les gains.
        """
        import inspect
        from gold_bot.strategy import Strategy
        source = inspect.getsource(Strategy)
        # Le seul usage de self.poids doit etre dans le calcul de priorite.
        usages = [l.strip() for l in source.splitlines()
                  if "self.poids.poids(" in l]
        assert len(usages) == 1, f"la ponderation ne doit agir qu'a un endroit : {usages}"
        contexte = source[:source.index("self.poids.poids(")]
        assert contexte.rstrip().endswith("*"), \
            "la ponderation doit multiplier le score de priorite"

    def test_chaine_complete_journal_vers_classement(self, tmp_path, monkeypatch):
        from gold_bot.apprentissage import PoidsAdaptatifs, alimenter_depuis_journal
        chemin = tmp_path / "trades.jsonl"
        with open(chemin, "w", encoding="utf-8") as fh:
            for _ in range(30):
                fh.write(json.dumps({"setup": "crypto_meme", "r_multiple": -0.7}) + "\n")
                fh.write(json.dumps({"setup": "crypto_major", "r_multiple": 0.6}) + "\n")
        p = PoidsAdaptatifs()
        alimenter_depuis_journal(p, str(chemin))
        assert p.poids("crypto_major") > p.poids("crypto_meme"), \
            "un secteur perdant doit passer derriere un secteur gagnant"
        assert p.poids("crypto_meme") < 1.0
