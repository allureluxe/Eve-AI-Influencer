"""Le rapport ALLURE envoye par Telegram s'ouvre dans une visionneuse de
documents qui n'execute PAS le JavaScript (14 sept. 2026).

L'operateur a recu une page complete -- « Jour par jour » s'affichait -- mais
sans graphique ET sans tableau des trades, les deux fabriques par un unique
bloc `<script>`. Deux defauts empiles :

  1. Ce bloc n'etait jamais execute par la visionneuse : tout ce qui en
     dependait restait vide, quel que soit son contenu.
  2. Quand `POINTS` etait vide, `POINTS[0][1]` levait une exception qui
     arretait le script ENTIER -- le graphique ET le tableau des trades
     disparaissaient ensemble, pour une seule cause.

Le graphique et le tableau sont maintenant rendus cote serveur, comme
« Jour par jour » l'a toujours ete. Ces tests verrouillent : qu'aucune page
ne depend plus de JavaScript, et qu'un nombre de points insuffisant ne fait
plus disparaitre tout le reste.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from rapports import _graphique_svg, _lignes_trades


class TestLeGraphiqueNeDependPlusDuJavaScript:

    def test_aucune_page_ne_porte_plus_de_script(self):
        svg = _graphique_svg([[0, 1.0], [3600, 2.0]], [])
        assert "<script" not in svg

    def test_zero_point_ne_leve_aucune_exception(self):
        """Avant le correctif, POINTS[0][1] sur un tableau vide arretait
        TOUT le script -- graphique ET tableau des trades disparaissaient."""
        rendu = _graphique_svg([], [])
        assert "<svg" not in rendu
        assert rendu  # un message, pas une page vide

    def test_un_seul_point_ne_leve_aucune_exception(self):
        rendu = _graphique_svg([[1000, 227.5]], [])
        assert rendu

    def test_deux_points_ou_plus_produisent_un_vrai_graphique(self):
        points = [[0, 100.0], [3600, 101.5], [7200, 99.0]]
        svg = _graphique_svg(points, [])
        assert svg.startswith('<svg')
        assert "</svg>" in svg

    def test_les_trades_fermes_apparaissent_comme_des_points_sur_la_courbe(self):
        points = [[0, 100.0], [7200, 105.0]]
        trades = [{"closed_at": 3600, "profit": 5.0},
                  {"closed_at": 5000, "profit": -2.0}]
        svg = _graphique_svg(points, trades)
        assert svg.count("<circle") >= len(trades)


class TestLeTableauDesTradesEstDuHtmlStatique:

    def test_aucun_trade_donne_une_ligne_explicite_pas_un_vide(self):
        rendu = _lignes_trades([])
        assert "aucun trade" in rendu

    def test_chaque_trade_produit_une_ligne(self):
        trades = [
            {"symbol": "BTCUSD", "closed_at": 1_800_000_000, "profit": 1.23,
             "r_multiple": 0.8},
            {"symbol": "ETHUSD", "closed_at": 1_800_003_600, "profit": -0.45,
             "r_multiple": -0.3},
        ]
        rendu = _lignes_trades(trades)
        assert rendu.count("<tr>") == 2
        assert "BTC" in rendu and "ETH" in rendu
        assert "<script" not in rendu

    def test_un_r_multiple_absent_ne_leve_aucune_exception(self):
        """`r_multiple` peut manquer sur un vieux trade du journal --
        `_lignes_trades` ne doit pas presumer sa presence."""
        trades = [{"symbol": "SOLUSD", "closed_at": 1_800_000_000, "profit": 0.5}]
        rendu = _lignes_trades(trades)
        assert rendu.count("<tr>") == 1
