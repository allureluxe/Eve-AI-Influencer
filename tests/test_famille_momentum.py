"""La famille « momentum » : entree sur tendance, sortie a DATE FIXE.

Ces tests verrouillent ce qui distingue cette methode de la notre. Le
piege documente dans le CLAUDE.md -- « verifier qu'un reglage est LU ne
prouve rien, il faut verifier qu'il S'EXECUTE » -- s'applique ici deux
fois : a l'entree (le rendement se mesure-t-il sur la bonne fenetre ?) et
a la sortie (la date fixe l'emporte-t-elle vraiment sur les deux autres
regles de sortie ?).
"""
from __future__ import annotations

import time

import pytest

from gold_bot.core import Position, Side
from gold_bot.trade_manager import ActionType
from gold_bot.settings import BotConfig
from gold_bot.strategy import Strategy, StrategyConfig
from gold_bot.trade_manager import TradeManager, TradeManagerConfig


JOUR = 86400.0


def _position(ouverte_il_y_a_jours: float) -> Position:
    return Position(
        id="p1", symbol="BTCEUR", side=Side.BUY, volume=1.0,
        entry_price=100.0, stop_loss=90.0, take_profit=None,
        opened_at=time.time() - ouverte_il_y_a_jours * JOUR)


class TestLaSortieADateFixeSExecute:
    """Elle doit fermer SANS CONDITION, et exclure les deux autres."""

    def test_ferme_au_terme_meme_en_pleine_progression(self):
        # Le cas qui distingue cette regle du stop temporel : la position
        # gagne, elle progresse, rien ne cloche -- et elle sort quand meme.
        tm = TradeManager(TradeManagerConfig(detention_max_jours=5.0))
        pos = _position(5.1)
        action = tm._safety_exits(pos, price=130.0, r_now=3.0,
                                  momentum=_momentum_neutre(), now=time.time())
        assert action is not None
        assert action.type is ActionType.CLOSE
        assert "duree de detention" in action.reason

    def test_ne_ferme_pas_avant_le_terme(self):
        tm = TradeManager(TradeManagerConfig(detention_max_jours=5.0))
        pos = _position(4.9)
        assert tm._safety_exits(pos, price=95.0, r_now=-0.5,
                                momentum=_momentum_neutre(),
                                now=time.time()) is None

    def test_elle_exclut_la_stagnation_ET_le_stop_temporel(self):
        # TROIS regles qui decident de la meme sortie, c'est le piege du
        # CLAUDE.md. Armees ensemble, seule la date fixe doit parler.
        tm = TradeManager(TradeManagerConfig(
            detention_max_jours=5.0,
            stagnation_jours=1.0, stagnation_max_r=0.5,
            time_stop_minutes=60.0, time_stop_min_r=0.25))
        pos = _position(3.0)   # au-dela de la stagnation ET du stop temporel
        action = tm._safety_exits(pos, price=100.0, r_now=0.0,
                                  momentum=_momentum_neutre(), now=time.time())
        # Ni l'une ni l'autre ne doit avoir ferme : le terme n'est pas la.
        assert action is None

    def test_desarmee_a_zero_rien_ne_change(self):
        tm = TradeManager(TradeManagerConfig(
            detention_max_jours=0.0,
            stagnation_jours=0.0,
            time_stop_minutes=7200.0, time_stop_min_r=0.25))
        pos = _position(10.0)
        action = tm._safety_exits(pos, price=100.0, r_now=0.0,
                                  momentum=_momentum_neutre(), now=time.time())
        assert action is not None
        assert "stop temporel" in action.reason


class TestLEntreeSurTendance:
    """Elle doit acheter ce qui monte, refuser ce qui baisse.

    Ces tests appellent la VRAIE methode. Verifier a la main que
    `bougies[-(n+1)]` vaut 100 ne prouverait rien sur le code qui tourne
    -- c'est exactement le defaut releve trois fois dans le CLAUDE.md.
    """

    def test_achete_une_hausse(self):
        ev = _evaluer([100.0] * 10 + [110.0, 120.0, 130.0, 140.0], prix=140.0,
                      formation=4)
        porte = _porte(ev, "momentum")
        assert porte.passed, porte.detail
        assert ev.side is Side.BUY
        assert ev.setup == "momentum_tendance"
        assert ev.stop_loss and ev.stop_loss < 140.0

    def test_refuse_une_baisse(self):
        ev = _evaluer([100.0] * 10 + [95.0, 90.0, 85.0, 80.0], prix=80.0,
                      formation=4)
        porte = _porte(ev, "momentum")
        assert not porte.passed
        assert ev.side is None

    def test_la_fenetre_de_formation_est_bien_celle_configuree(self):
        # Meme serie, deux fenetres. Sur 4 bougies la crypto MONTE
        # (100 -> 140) ; sur 12 elle BAISSE (200 -> 140). Si le code
        # lisait la mauvaise fenetre, les deux rendraient la meme reponse.
        serie = [200.0] * 8 + [100.0, 110.0, 120.0, 130.0, 140.0]
        courte = _evaluer(serie, prix=140.0, formation=4)
        longue = _evaluer(serie, prix=140.0, formation=12)
        assert _porte(courte, "momentum").passed, "4 bougies : +40 %"
        assert not _porte(longue, "momentum").passed, "12 bougies : -30 %"

    def test_le_seuil_minimal_s_execute(self):
        serie = [100.0] * 10 + [101.0, 102.0, 103.0, 104.0]   # +4 %
        assert _porte(_evaluer(serie, 104.0, 4, seuil=2.0), "momentum").passed
        assert not _porte(_evaluer(serie, 104.0, 4, seuil=10.0),
                          "momentum").passed

    def test_historique_insuffisant_refuse_au_lieu_de_deviner(self):
        ev = _evaluer([100.0, 110.0], prix=110.0, formation=28)
        porte = _porte(ev, "momentum")
        assert not porte.passed
        assert "insuffisant" in porte.detail


class TestLaConfigurationRefuseLIncoherent:
    def test_momentum_sans_sortie_a_date_fixe_est_refuse(self):
        cfg = BotConfig.load("robot.demo2.json")
        cfg.strategy.famille = "momentum"
        cfg.trade.detention_max_jours = 0.0
        soucis = cfg.validate()
        assert any("detention_max_jours" in s for s in soucis), (
            "armer la famille sans sa regle de sortie donnerait un achat "
            "de tendance sans sortie -- ce n'est plus la methode mesuree")

    def test_momentum_avec_sortie_est_accepte(self):
        cfg = BotConfig.load("robot.demo2.json")
        cfg.strategy.famille = "momentum"
        cfg.trade.detention_max_jours = 5.0
        cfg.trade.time_stop_minutes = 0.0
        assert not [s for s in cfg.validate() if "momentum" in s
                    or "detention" in s]


# ----------------------------------------------------------------------
def _momentum_neutre():
    from gold_bot.trade_manager import Momentum
    return Momentum(score=0.0, reasons=[])


def _indicateurs(closes: list[float]):
    from gold_bot.core import Candle
    from gold_bot.indicators import IndicatorSet
    ind = IndicatorSet()
    for i, c in enumerate(closes):
        ind.update(Candle(ts=float(i) * JOUR, open=c, high=c * 1.001,
                          low=c * 0.999, close=c, volume=1000.0))
    return ind


def _evaluer(closes: list[float], prix: float, formation: int,
             seuil: float = 0.0):
    """Appelle la VRAIE branche momentum de la strategie."""
    from gold_bot.core import Tick
    from gold_bot.strategy import Evaluation
    from gold_bot.universe import instrument_crypto

    strat = Strategy(StrategyConfig(
        famille="momentum", momentum_formation=formation,
        momentum_seuil_pct=seuil))
    instrument = instrument_crypto("BTC", "majeures")
    ev = Evaluation(symbol="BTCEUR", asset_class="crypto")
    ind = _indicateurs(closes)
    atr = max(prix * 0.02, 1e-6)
    tick = Tick(ts=0.0, bid=prix * 0.999, ask=prix * 1.001)
    return strat._finish_momentum(ev, instrument, ind, prix, atr, tick)


def _porte(ev, nom: str):
    porte = next((g for g in ev.gates if g.name == nom), None)
    assert porte is not None, f"la porte « {nom} » n'a pas ete evaluee"
    return porte


class TestLeCroisementDesDeuxFamilles:
    """Exiger la cassure ET la tendance longue.

    Demande de l'operateur le 21 septembre : « fais un test en melangeant
    nos 2 methodes ». La cassure est un EVENEMENT, le momentum un ETAT ;
    rien n'oblige a choisir.
    """

    def _cfg(self, plancher: float, fenetre: int = 4):
        return StrategyConfig(
            famille="donchian", donchian_entrees=(3,),
            donchian_tendance_longue=True,
            donchian_momentum_min_pct=plancher,
            donchian_momentum_fenetre=fenetre)

    def test_une_cassure_dans_une_baisse_de_fond_est_refusee(self):
        # Le prix casse son plus-haut de 3 bougies, mais il est TRES bas
        # par rapport a il y a 4 bougies : c'est un rebond, pas une
        # tendance. C'est exactement le cas que le croisement doit fermer.
        ev = _casser([200.0, 100.0, 100.0, 100.0, 101.0, 102.0], prix=103.0,
                     cfg=self._cfg(plancher=0.0, fenetre=5))
        porte = _porte(ev, "tendance_longue")
        assert not porte.passed, porte.detail
        assert ev.side is None

    def test_une_cassure_en_tendance_haussiere_passe(self):
        ev = _casser([100.0, 105.0, 110.0, 115.0, 118.0], prix=125.0,
                     cfg=self._cfg(plancher=0.0))
        assert _porte(ev, "tendance_longue").passed
        assert ev.side is Side.BUY

    def test_le_plancher_s_execute_vraiment(self):
        serie = [100.0, 101.0, 102.0, 103.0, 104.0]
        assert _porte(_casser(serie, 105.0, self._cfg(2.0)),
                      "tendance_longue").passed
        assert not _porte(_casser(serie, 105.0, self._cfg(20.0)),
                          "tendance_longue").passed

    def test_a_zero_le_croisement_est_desarme(self):
        # Desarme, la porte ne doit meme pas etre evaluee : la
        # configuration en service ne change pas d'un iota.
        serie = [200.0, 100.0, 100.0, 100.0, 101.0, 102.0]
        ev = _casser(serie, prix=103.0, cfg=self._cfg(plancher=0.0, fenetre=5))
        ev2 = _casser(serie, prix=103.0,
                      cfg=StrategyConfig(famille="donchian",
                                         donchian_entrees=(3,)))
        assert any(g.name == "tendance_longue" for g in ev.gates)
        assert not any(g.name == "tendance_longue" for g in ev2.gates)
        assert ev2.side is Side.BUY

    def test_la_fenetre_par_defaut_suit_momentum_formation(self):
        cfg = StrategyConfig(famille="donchian", donchian_entrees=(3,),
                             donchian_tendance_longue=True,
                             donchian_momentum_min_pct=1.0,
                             donchian_momentum_fenetre=0,
                             momentum_formation=4)
        ev = _casser([100.0, 101.0, 102.0, 103.0, 104.0], 105.0, cfg)
        assert "sur 4 bougies" in _porte(ev, "tendance_longue").detail


def _casser(closes, prix, cfg):
    """Fait passer une cassure de canal dans `_finish_donchian`."""
    from gold_bot.core import Tick
    from gold_bot.strategy import Evaluation
    from gold_bot.universe import instrument_crypto
    strat = Strategy(cfg)
    ev = Evaluation(symbol="BTCEUR", asset_class="crypto")
    ind = _indicateurs(closes)
    atr = max(prix * 0.02, 1e-6)
    tick = Tick(ts=0.0, bid=prix * 0.999, ask=prix * 1.001)
    return strat._finish_donchian(ev, instrument_crypto("BTC", "majeures"),
                                  ind, prix, atr, tick)


class TestLaSortieSurRetournementEnPerte:
    """Couper un perdant dont la tendance s'est retournee.

    L'angle mort : `r_now >= reversal_exit_r` reservait la regle aux
    positions DEJA EN BENEFICE. Une position en perte dont la tendance se
    retourne descendait jusqu'au stop complet, alors que l'indicateur
    avait vu le retournement.
    """

    def _tm(self, **kw):
        # Le stop temporel est repousse tres loin : sinon c'est LUI qui
        # ferme la position d'un jour, et le test ne dirait rien de la
        # regle qu'il pretend verifier. (Pas 0 : a zero, `age >= 0` est
        # toujours vrai et il se declencherait en permanence.)
        base = dict(reversal_exit_en_perte=True, reversal_exit_perte_r=-0.30,
                    reversal_exit_perte_score=-0.60, reversal_exit_r=0.25,
                    time_stop_minutes=9_999_999.0)
        base.update(kw)
        return TradeManager(TradeManagerConfig(**base))

    def _momentum(self, score):
        from gold_bot.trade_manager import Momentum
        return Momentum(score=score, reasons=["supertrend retourne"])

    def test_coupe_un_perdant_dont_la_tendance_se_retourne(self):
        a = self._tm()._safety_exits(
            _position(1.0), price=97.0, r_now=-0.50,
            momentum=self._momentum(-0.75), now=time.time())
        assert a is not None and a.type is ActionType.CLOSE
        assert "retournement en perte" in a.reason

    def test_ne_coupe_pas_sur_un_retournement_tiede(self):
        # -0,50 passe le seuil du BENEFICE (-0,45) mais pas celui de la
        # PERTE (-0,60) : en perte on exige plus de certitude.
        assert self._tm()._safety_exits(
            _position(1.0), price=97.0, r_now=-0.50,
            momentum=self._momentum(-0.50), now=time.time()) is None

    def test_ne_coupe_pas_sur_le_bruit_des_premieres_heures(self):
        # A peine sous l'eau : on laisse respirer, meme si le score est mauvais.
        assert self._tm()._safety_exits(
            _position(0.1), price=99.5, r_now=-0.05,
            momentum=self._momentum(-0.90), now=time.time()) is None

    def test_desarmee_rien_ne_change(self):
        assert self._tm(reversal_exit_en_perte=False)._safety_exits(
            _position(1.0), price=97.0, r_now=-0.50,
            momentum=self._momentum(-0.90), now=time.time()) is None

    def test_le_benefice_garde_son_seuil_a_lui(self):
        # La regle historique ne doit pas etre durcie par la nouvelle.
        a = self._tm()._safety_exits(
            _position(1.0), price=103.0, r_now=0.40,
            momentum=self._momentum(-0.46), now=time.time())
        assert a is not None
        assert "retournement confirme" in a.reason
