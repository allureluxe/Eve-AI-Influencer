"""Le rejeu de portefeuille dit-il la verite ?

Un second moteur de rejeu est dangereux : s'il diverge du premier, on
compare deux mesures qui ne parlent pas de la meme strategie, et rien
ne devient rouge. Ce depot l'a deja paye plusieurs fois (« deux endroits
decidaient du meme reglage », « le rejeu mesurait une regle que le robot
n'appliquait pas »).

D'ou le verrou central ici : sur UN SEUL instrument, le portefeuille
doit rendre EXACTEMENT ce que rend le rejeu par instrument. S'il en
differe d'un centime, c'est qu'un des deux pilotes fait autre chose.
"""
import math

import pytest

from gold_bot.backtest import Backtester
from gold_bot.backtest_portefeuille import BacktestPortefeuille
from gold_bot.core import Candle, ClosedTrade, Side
from gold_bot.settings import BotConfig


def _serie(n=520, depart=100.0, pente=0.35, amplitude=3.0):
    """Une tendance haussiere bruitee : de quoi declencher des cassures."""
    bougies = []
    prix = depart
    for i in range(n):
        prix += pente + amplitude * math.sin(i / 7.0)
        haut = prix + amplitude
        bas = prix - amplitude
        bougies.append(Candle(ts=1_600_000_000 + i * 86400,
                              open=prix - pente, high=haut, low=bas,
                              close=prix, volume=1000.0))
    return bougies


class _RegistreFixe:
    """Rend toujours la meme serie, quel que soit le symbole demande."""

    def __init__(self, series):
        self._series = series

    def candles(self, symbol, asset_class, tf, n):
        return list(self._series.get(symbol, [])[-n:])


@pytest.fixture
def config():
    cfg = BotConfig.load("robot.demo.json")
    return cfg


class TestUnSeulInstrumentDonneLeMemeResultat:
    """Le verrou : meme corps de bougie, donc memes chiffres."""

    def test_le_portefeuille_a_un_instrument_egale_le_rejeu_simple(self, config):
        serie = _serie()
        registre = _RegistreFixe({"BTCUSD": serie})

        seul = Backtester(config, registry=registre).run(
            "BTCUSD", bars=len(serie), start_balance=3300.0)
        porte = BacktestPortefeuille(config, registry=registre).run(
            ["BTCUSD"], bars=len(serie), start_balance=3300.0)

        assert porte.par_instrument, "aucun instrument n'a defile"
        assert porte.end_balance == pytest.approx(seul.end_balance, abs=1e-9), (
            "le rejeu de portefeuille ne reproduit pas le rejeu par instrument")
        reels_seul = [t for t in seul.trades if not t.partial]
        reels_porte = [t for t in porte.trades if not t.partial]
        assert len(reels_porte) == len(reels_seul)
        for a, b in zip(reels_seul, reels_porte):
            assert a.symbol == b.symbol
            assert a.profit == pytest.approx(b.profit, abs=1e-9)
            assert a.entry_price == pytest.approx(b.entry_price, abs=1e-12)


class TestLeBudgetDeRisqueEstVraimentPartage:
    """Ce pour quoi ce module existe."""

    def test_un_budget_saturé_empeche_le_second_instrument(self, config):
        """A budget serre, deux cryptos se disputent la meme place.

        Le budget est ramene a un peu plus d'UNE position : la seconde
        crypto ne doit alors presque rien pouvoir prendre. Sans cette
        reduction il reste de la place pour huit lignes, aucune
        concurrence n'a lieu, et le test ne mesurerait rien — la faute
        classique de ce depot : verifier une regle dans un cas ou elle
        ne se declenche pas.
        """
        serie = _serie()
        registre = _RegistreFixe({"BTCUSD": serie, "ADAUSD": serie})
        config.risk.max_total_risk_pct = config.risk.base_risk_pct * 1.2

        seul = BacktestPortefeuille(config, registry=registre).run(
            ["BTCUSD"], bars=len(serie), start_balance=3300.0)
        deux = BacktestPortefeuille(config, registry=registre).run(
            ["BTCUSD", "ADAUSD"], bars=len(serie), start_balance=3300.0)

        def engage(resultat, symbole):
            return sum(t.entry_price * t.volume
                       for t in resultat.par_instrument[symbole].trades
                       if not t.partial)

        assert engage(seul, "BTCUSD") > 0, "le scenario ne produit aucun trade"
        # LE BUDGET NE REFUSE PAS, IL RETRECIT.
        #
        # Tant qu'il reste plus de 0,05 % de marge, `size_position`
        # accepte le trade en rabotant sa taille. Le second instrument
        # obtient donc autant de TRADES que le premier, mais bien plus
        # petits — compter les trades ne verrait rien.
        assert engage(deux, "ADAUSD") < engage(deux, "BTCUSD") * 0.5, (
            "le second instrument n'a subi aucune concurrence : "
            "le budget de risque n'est pas partage")

    def test_le_capital_de_depart_n_est_compte_qu_une_fois(self, config):
        serie = _serie()
        registre = _RegistreFixe({"BTCUSD": serie, "ADAUSD": serie})
        r = BacktestPortefeuille(config, registry=registre).run(
            ["BTCUSD", "ADAUSD"], bars=len(serie), start_balance=3300.0)
        assert r.start_balance == 3300.0, (
            "un rejeu de portefeuille qui additionne les capitaux mesure "
            "plusieurs comptes, pas un robot")


class TestLeNombreDEtagesEstEnregistre:
    """Sans lui, la mesure qui a justifie le pyramidage est irreproductible."""

    def test_closed_trade_porte_les_etages(self):
        t = ClosedTrade(position_id="x", symbol="BTCUSD", side=Side.BUY,
                        volume=1.0, entry_price=1.0, exit_price=2.0,
                        opened_at=0.0, closed_at=1.0, profit=1.0,
                        r_multiple=1.0, reason="test", etages=4)
        assert t.etages == 4

    def test_le_simulateur_reporte_les_etages_de_la_position(self, config):
        serie = _serie()
        registre = _RegistreFixe({"BTCUSD": serie})
        r = BacktestPortefeuille(config, registry=registre).run(
            ["BTCUSD"], bars=len(serie), start_balance=3300.0)
        for t in r.trades:
            assert t.etages >= 1
        par_etage = r.resultat_par_etage()
        assert all(e >= 1 for e in par_etage), par_etage


class TestLeDefilementEstChronologique:
    def test_les_instruments_avancent_dans_l_ordre_du_temps(self, config):
        """Sinon BTC vivrait tout son historique avant qu'ADA ne commence."""
        serie = _serie()
        registre = _RegistreFixe({"BTCUSD": serie, "ADAUSD": serie})
        r = BacktestPortefeuille(config, registry=registre).run(
            ["BTCUSD", "ADAUSD"], bars=len(serie), start_balance=3300.0)
        horodatages = [ts for ts, _ in r.courbe]
        assert horodatages == sorted(horodatages), (
            "la courbe de capital n'est pas chronologique")
