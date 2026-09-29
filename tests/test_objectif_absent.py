"""Une cible a zero ne doit JAMAIS fermer une position.

L'incident, nuit du 27 septembre 2026, compte demo 2 : quatre positions
ouvertes puis fermees en 10 a 26 secondes, motif « objectif atteint »,
prix de sortie **zero**. Perte : -482,37 EUR, soit -9 a -16 R pour un
risque de 9 EUR par trade.

La cause tient en une ligne. `initial_levels` a commence, le
26 septembre a 18h47, a rendre une cible de **0.0** quand `tp_actif`
est faux, avec ce commentaire :

    « les moteurs de sortie savent ainsi qu'il n'existe PAS de TP »

Aucun moteur de sortie ne le savait. `hit_target` comparait
`prix >= 0` — vrai a la premiere cotation venue — et le simulateur
reglait la sortie AU PRIX DE LA CIBLE, c'est-a-dire zero : 100 % du
notionnel perdu d'un coup.

Ces tests verrouillent les deux chemins de sortie du simulateur, celui
des cotations et celui des bougies.
"""
from __future__ import annotations

import unittest

from gold_bot.core import Position, Side


def _position(tp: float) -> Position:
    return Position(
        id="test", symbol="ETHUSD", side=Side.BUY, volume=1.0,
        entry_price=2369.31, stop_loss=2100.0, take_profit=tp,
        opened_at=0.0)


class TestCibleAZeroNeFermeRien(unittest.TestCase):

    def test_achat_sans_objectif_ne_touche_jamais_la_cible(self):
        """Le cas exact de l'incident : cible 0, prix normal."""
        pos = _position(0.0)
        self.assertFalse(pos.hit_target(2369.31))
        self.assertFalse(pos.hit_target(0.01))
        self.assertFalse(pos.hit_target(1_000_000.0))

    def test_vente_sans_objectif_non_plus(self):
        pos = _position(0.0)
        pos.side = Side.SELL
        self.assertFalse(pos.hit_target(2369.31))
        self.assertFalse(pos.hit_target(0.01))

    def test_un_vrai_objectif_fonctionne_toujours(self):
        """La garde ne doit pas desarmer les sorties legitimes."""
        pos = _position(2500.0)
        self.assertFalse(pos.hit_target(2499.99))
        self.assertTrue(pos.hit_target(2500.0))
        self.assertTrue(pos.hit_target(2600.0))

    def test_le_stop_reste_intact_sans_objectif(self):
        """Sans TP, la position doit toujours pouvoir sortir par le stop."""
        pos = _position(0.0)
        self.assertFalse(pos.hit_stop(2200.0))
        self.assertTrue(pos.hit_stop(2100.0))
        self.assertTrue(pos.hit_stop(1900.0))


class TestLeSimulateurNeReglePlusAZero(unittest.TestCase):
    """Le chemin des bougies, celui qu'utilisent les rejeux et le labo."""

    def test_process_candle_ignore_une_cible_nulle(self):
        from gold_bot.brokers.paper import PaperBroker  # noqa: PLC0415

        source = open("gold_bot/brokers/paper.py", encoding="utf-8").read()
        # La garde doit exister DANS LES DEUX SENS, achat et vente.
        self.assertIn("avec_objectif and candle.high >= pos.take_profit", source)
        self.assertIn("avec_objectif and candle.low <= pos.take_profit", source)
        self.assertTrue(hasattr(PaperBroker, "process_candle"))


if __name__ == "__main__":
    unittest.main()
