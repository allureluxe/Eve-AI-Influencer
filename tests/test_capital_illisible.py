"""Une lecture ratee n'est pas un capital nul.

LE 12 SEPTEMBRE 2026 A 01H49, l'operateur a recu sur son telephone :

    « Capital insuffisant pour cette plateforme
      capital 0.00 | ticket minimum 5.00
      AUCUNE unite praticable — capital nul »

    « Le capital (0.00 EUR) ne porte plus des positions de 15 EUR.
      Le robot descend a 5.00 EUR pour continuer a travailler. »

Son compte valait 263 EUR. L'API Bitvavo n'avait pas repondu.

DEUX DEGATS. Une alerte alarmante et fausse — et une alerte fausse coute
plus qu'une alerte manquante, car elle apprend a ne plus les lire, et
c'est par ce canal qu'arrive le chien de garde. Et surtout une
RECONFIGURATION du robot sur une donnee inexistante : le plancher etait
reellement descendu a 5 EUR, c'est-a-dire aux miettes que l'operateur
venait de faire retirer.

Le chien de garde applique cette regle depuis le premier jour :
« Lecture d'equite impossible => AUCUNE ACTION. On ne coupe jamais sur
une donnee manquante. » Elle vaut partout.
"""
from __future__ import annotations

import inspect

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path


class TestOnNeSeReconfigurePasSurDuVide:

    def test_le_plancher_ne_bouge_pas_sans_capital(self):
        from gold_bot.engine import TradingEngine

        source = inspect.getsource(TradingEngine._ajuster_le_plancher)
        assert "if equity <= 0" in source, (
            "le plancher se recalcule sur un capital illisible : une panne "
            "d'API suffirait a ramener les positions a 5 EUR")
        # Le garde-fou doit sortir AVANT toute ecriture.
        avant = source.split("if equity <= 0")[0]
        assert "cfg.risk.ticket_min_eur =" not in avant, (
            "le plancher est modifie avant le controle du capital")

    def test_pas_d_alerte_capital_insuffisant_sur_un_capital_illisible(self):
        from gold_bot.engine import TradingEngine

        source = inspect.getsource(TradingEngine._calibrer_sur_le_capital)
        # L'APPEL, pas le commentaire qui le decrit : la meme phrase
        # apparait dans l'explication juste au-dessus.
        i = source.find('self.notifier.warning(\n                    "Capital insuffisant')
        assert i > 0, "l'alerte a change de forme, ce test ne la trouve plus"
        avant = source[:i]
        assert "cal.equity <= 0" in avant, (
            "le robot annonce « capital insuffisant » sans verifier que le "
            "capital a pu etre LU : le message serait faux")


class TestLaRegleEstLaMemePartout:
    """Le chien de garde la respecte deja : on verifie qu'elle n'a pas bouge."""

    def test_le_chien_de_garde_ne_coupe_pas_sur_une_lecture_ratee(self):
        import pathlib
        racine = pathlib.Path(__file__).resolve().parent.parent
        texte = (racine / "ops" / "chien_de_garde.py").read_text(encoding="utf-8")
        assert "AUCUNE ACTION" in texte
        assert "if equite is None:" in texte, (
            "le chien de garde agirait sur une equite absente : il "
            "couperait le robot sur une panne d'API")
