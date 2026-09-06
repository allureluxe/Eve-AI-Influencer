"""Le capital reserve pour des places qui ne s'ouvrent jamais ne rapporte rien.

Mesure du 30 aout, en argent reel : 97,37 EUR de capital, 70,82 EUR
disponibles toute la journee. Le partage du cash divise par TOUTES les
places libres — six — en pariant que six occasions se presenteront. Il y
en a eu DEUX. Quatre sixiemes du compte ont dormi jusqu'au soir, et les
deux positions prises ont porte 0,25 % de risque au lieu des 0,60 %
configures.

Ce n'est pas le partage qui est faux : quand six occasions existent, six
positions de 14,40 EUR risquent exactement autant que deux de 43 EUR.
C'est de reserver pour des occasions qui n'existent pas.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.core import Side
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe, spread_estime


def _dimensionner(places_visees=None, capital=97.0, positions=None):
    from gold_bot.risk import RiskManager

    cfg = BotConfig.load("robot.bitvavo.json")
    u = Universe()
    inst = u.get("BTCUSD")
    prix = 68_000.0
    stop = prix * 0.0128            # ~1,6 ATR au M30
    rm = RiskManager(cfg.risk)
    rm.sync_account(equity=capital, balance=capital)
    return cfg, rm.size_position(
        inst, Side.BUY, prix, prix - stop, prix + stop * cfg.trade.tp_r_multiple,
        open_positions=positions or [], universe_lookup=u.get,
        spread=spread_estime(inst, prix), available_cash=capital,
        places_visees=places_visees)


class TestLePartageSAccordeAuxOccasionsREELLES:

    def test_deux_occasions_ne_reservent_pas_pour_six(self):
        """La journee du 30 aout, verrouillee."""
        _, six = _dimensionner(places_visees=None)     # ancien comportement
        _, deux = _dimensionner(places_visees=2)
        assert six.allowed and deux.allowed, (six.reason, deux.reason)
        assert deux.risk_pct > six.risk_pct, (
            f"avec 2 occasions le robot risque {deux.risk_pct:.3f} % contre "
            f"{six.risk_pct:.3f} % en reservant pour 6 : le capital dort "
            "toujours pour des places qui ne s'ouvriront pas")

    def test_huit_occasions_partagent_comme_avant(self):
        """Le partage reste juste quand les occasions existent vraiment."""
        _, defaut = _dimensionner(places_visees=None)
        _, huit = _dimensionner(places_visees=8)
        assert abs(huit.risk_pct - defaut.risk_pct) < 1e-9

    def test_une_seule_occasion_ne_depasse_pas_le_risque_configure(self):
        """La borne dure : partager moins ne doit pas risquer plus.

        C'est la seule chose qui pourrait rendre ce changement dangereux —
        et c'est `base_risk_pct` puis `max_total_risk_pct` qui l'empechent,
        pas le partage.
        """
        cfg, une = _dimensionner(places_visees=1)
        assert une.allowed
        assert une.risk_pct <= cfg.risk.base_risk_pct + 1e-9, (
            f"{une.risk_pct:.3f} % de risque pour {cfg.risk.base_risk_pct:.2f} % "
            "configures : le partage ne doit jamais AUGMENTER le risque")

    def test_la_valeur_absente_garde_l_ancien_comportement(self):
        """Une couche qui ne sait pas compter ses occasions ne doit pas
        concentrer par accident."""
        _, sans = _dimensionner(places_visees=None)
        _, trop = _dimensionner(places_visees=99)
        assert abs(sans.risk_pct - trop.risk_pct) < 1e-9, (
            "places_visees ne doit jamais depasser les places reellement libres")


class TestLeQuatriemeVerrouDuRenforcement:
    """Trois verrous leves, un quatrieme encore ferme : la pyramide inerte."""

    def test_la_boucle_multi_entrees_laisse_passer_un_renfort(self):
        import inspect
        from gold_bot.dual_scalping_engine import MultiEntryScalpingMixin
        src = inspect.getsource(MultiEntryScalpingMixin._look_for_entry)
        assert "if ev.symbol not in renforcables:" in src, (
            "la boucle refuse encore toute occasion sur un symbole detenu : "
            "armer pyramide_max ne changerait rien")

    def test_le_dimensionnement_recoit_les_places_visees(self):
        import inspect
        from gold_bot.dual_scalping_engine import MultiEntryScalpingMixin
        src = inspect.getsource(MultiEntryScalpingMixin._look_for_entry)
        assert "places_visees=" in src, (
            "le moteur connait le nombre d'occasions mais ne le transmet pas : "
            "le cash continue d'etre reserve pour six places")
