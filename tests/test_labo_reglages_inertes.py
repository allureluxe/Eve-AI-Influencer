"""Le labo doit refuser une hypothese qu'il ne peut pas mesurer.

L'INCIDENT, mesure le 27 septembre 2026.

Le carnet du labo portait **354 essais pour 57 resultats distincts**, et
**166 essais rendaient exactement -291,04 EUR** — celui du temoin. Un
essai sur deux ne mesurait rien.

La cause : `Strategy._finish` aiguille vers une branche par famille, et
chaque branche ne lit QUE ses propres reglages. Le labo tourne sur
`robot.demo2.json`, famille **momentum**, dont la branche ne lit que
`momentum_formation`, `momentum_seuil_pct` et `momentum_detention`. Les
agents lui proposaient du canal Donchian, de l'ADX et du ratio
rendement/risque : poses sur la configuration, jamais lus.

Rien ne le signalait. Le backtest tournait, rendait un resultat
plausible, et le candidat etait archive « barre backtest non franchie » —
un verdict sur une idee qui n'avait jamais ete mesuree.

Mesure de controle, 4 symboles, 1 200 barres :

    min_adx 5 | min_adx 40 | donchian 5 | donchian 60 | min_score 0.0
    -> 218 trades, -427,26 EUR, 34,4 % — IDENTIQUE pour les cinq.
    atr_stop_mult 0.8 -> 235 trades, -527,70 EUR   (celui-la mord :
    il est dans `trade`, que toutes les familles lisent.)
"""
from __future__ import annotations

import unittest

from gold_bot.lab import AGENTS, REGLAGES_PAR_FAMILLE, reglages_sans_effet


class TestReglagesSansEffet(unittest.TestCase):

    def test_le_canal_donchian_est_inerte_en_momentum(self):
        """Le cas exact de l'incident."""
        inertes = reglages_sans_effet(
            {"name": "x", "famille": "momentum", "donchian_entrees": [10]},
            "momentum")
        self.assertEqual(inertes, ["donchian_entrees"])

    def test_le_canal_donchian_mord_en_donchian(self):
        inertes = reglages_sans_effet(
            {"name": "x", "famille": "donchian", "donchian_entrees": [10]},
            "donchian")
        self.assertEqual(inertes, [])

    def test_ladx_est_inerte_dans_une_branche_specialisee(self):
        """min_adx n'est lu que par le chemin generique."""
        self.assertEqual(
            reglages_sans_effet({"name": "x", "min_adx": 20.0}, "momentum"),
            ["min_adx"])
        self.assertEqual(
            reglages_sans_effet({"name": "x", "min_adx": 20.0}, "donchian"),
            ["min_adx"])
        self.assertEqual(
            reglages_sans_effet({"name": "x", "min_adx": 20.0}, "tendance"),
            [])

    def test_les_reglages_de_trade_mordent_dans_toutes_les_familles(self):
        """atr_stop_mult est dans `trade` : jamais inerte."""
        for famille in ("momentum", "donchian", "tendance", "reversion"):
            self.assertEqual(
                reglages_sans_effet({"name": "x", "atr_stop_mult": 1.8}, famille),
                [], f"atr_stop_mult declare inerte en {famille}")

    def test_la_famille_elle_meme_ne_compte_pas_comme_un_reglage(self):
        self.assertEqual(
            reglages_sans_effet({"name": "x", "famille": "donchian"}, "donchian"),
            [])


class TestLesAgentsProposentDesReglagesLUS(unittest.TestCase):
    """Le verrou qui empeche l'incident de revenir par la porte d'entree."""

    def test_chaque_variante_a_au_moins_un_reglage_qui_mord(self):
        for agent, variantes in AGENTS.items():
            for params in variantes:
                famille = str(params.get("famille") or "tendance")
                proposes = [k for k in params if k not in ("name", "famille")]
                if not proposes:
                    continue
                inertes = reglages_sans_effet(params, famille)
                self.assertNotEqual(
                    len(inertes), len(proposes),
                    f"{agent} / {params.get('name')} : AUCUN reglage lu par "
                    f"la famille « {famille} » (inertes : {inertes}). "
                    f"Cette variante remesurerait le temoin.")

    def test_les_familles_declarees_sont_connues(self):
        connues = set(REGLAGES_PAR_FAMILLE) | {"tendance"}
        for agent, variantes in AGENTS.items():
            for params in variantes:
                f = params.get("famille")
                if f is not None:
                    self.assertIn(f, connues, f"{agent} : famille inconnue {f!r}")


if __name__ == "__main__":
    unittest.main()
