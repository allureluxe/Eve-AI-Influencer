"""Le suiveur se resserre UNE FOIS le benefice garanti, pas avant.

IDEE DE L'OPERATEUR, 12 septembre 2026, en regardant MTL monter a
+2,76 EUR puis retomber a +1,08 : « on reste a 2 ATR, mais des que le
stop passe en benef il se resserre jusqu'a etre proche ».

DEUX VERSIONS AVAIENT ETE MESUREES ET ECARTEES avant celle-ci, toutes
deux resserrant selon le GAIN — donc des les premiers pas. Elles
etranglaient la position et divisaient le resultat par deux. Toute la
difference tient a un mot : APRES l'abri.

MESURE, six periodes de ~15 mois, 70 paires, frais doubles, chacune
repartant de 263 EUR :

    263 EUR deviennent   696 E sans  /  702 E avec
    recul moyen         25,5 %      /  21,5 %
    pire recul            38 %      /    29 %

    rendement meilleur : 3 periodes sur 6  -> pile ou face
    recul PLUS PETIT   : 5 periodes sur 6, JAMAIS pire

On n'arme donc pas pour gagner plus — les deux se valent — mais pour
encaisser moins de casse. A 38 % de recul le coupe-circuit interne
(45 %) est frole ; a 29 % il reste de la marge.
"""
from __future__ import annotations

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.trade_manager import TradeManagerConfig


def _largeur(cfg: TradeManagerConfig, abri_r: float) -> float:
    """Largeur du suiveur, en ATR, pour un benefice verrouille de `abri_r`."""
    mult = cfg.trail_atr_mult
    if cfg.trail_serrage_apres_abri > 0 and abri_r > 0:
        mult = mult / (1.0 + cfg.trail_serrage_apres_abri * abri_r)
        mult = max(cfg.trail_min_atr_mult, mult)
    return mult


class TestLaRegleEstArmee:

    def test_les_deux_reglages_sont_dans_la_config(self):
        from gold_bot.settings import BotConfig

        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.trade.trail_serrage_apres_abri > 0, (
            "le resserrage apres abri est desarme : le robot rendra de "
            "nouveau tout l'ecart entre le plus-haut et le stop")
        assert cfg.trade.trail_min_atr_mult >= 1.0, (
            f"plancher a {cfg.trade.trail_min_atr_mult} ATR : trop serre, "
            "un soubresaut ordinaire sortirait la position")


class TestOnNeSerreQuAPRESLAbri:
    """Le mot qui change tout."""

    def test_avant_l_abri_la_largeur_est_pleine(self):
        cfg = TradeManagerConfig(trail_atr_mult=2.0,
                                 trail_serrage_apres_abri=0.15,
                                 trail_min_atr_mult=1.2)
        assert _largeur(cfg, abri_r=0.0) == pytest.approx(2.0), (
            "la position est resserree avant d'etre a l'abri : c'est la "
            "version qui divisait le resultat par deux")

    def test_apres_l_abri_elle_se_reduit(self):
        cfg = TradeManagerConfig(trail_atr_mult=2.0,
                                 trail_serrage_apres_abri=0.15,
                                 trail_min_atr_mult=1.2)
        assert _largeur(cfg, abri_r=1.0) < 2.0
        assert _largeur(cfg, abri_r=3.0) < _largeur(cfg, abri_r=1.0)

    def test_le_plancher_empeche_l_etranglement(self):
        """« Calcule bien pour pas que 10 pips me sorte. »"""
        cfg = TradeManagerConfig(trail_atr_mult=2.0,
                                 trail_serrage_apres_abri=0.15,
                                 trail_min_atr_mult=1.2)
        for abri in (5.0, 20.0, 100.0):
            assert _largeur(cfg, abri) == pytest.approx(1.2), (
                f"a +{abri} R d'abri la largeur tombe sous le plancher : "
                "le moindre soubresaut sortirait la position")

    def test_a_zero_rien_ne_change(self):
        """Le defaut du code doit laisser le comportement d'avant."""
        cfg = TradeManagerConfig(trail_atr_mult=2.0)
        assert cfg.trail_serrage_apres_abri == 0.0
        for abri in (0.0, 1.0, 10.0):
            assert _largeur(cfg, abri) == pytest.approx(2.0)


class TestCeQueLaMesureAEcarte:
    """Les deux versions precedentes ne doivent pas revenir par la fenetre.

    Elles resserraient selon le GAIN COURANT, pas selon le benefice
    VERROUILLE. Sur les memes donnees elles divisaient le resultat par
    deux : 1 232 EUR hors echantillon contre 474 a 615.
    """

    def test_le_declencheur_est_le_stop_pas_le_gain(self):
        import inspect

        from gold_bot.trade_manager import TradeManager
        source = inspect.getsource(TradeManager.manage)
        i = source.find("cfg.trail_serrage_apres_abri > 0")
        assert i > 0, "le resserrage a disparu du moteur"
        condition = source[i:i + 260]
        assert "position.stop_loss - position.entry_price" in condition, (
            "le resserrage se declenche sur autre chose que le passage du "
            "stop au-dessus de l'entree : c'est la version mesuree perdante")


class TestLePointMortCouvreLesFrais:
    """« Le trade ne peut plus perdre » doit etre vrai, pas presque.

    Le 12 septembre 2026, MTL sort a -0,24 EUR avec un stop pose AU-DESSUS
    du prix d'entree. Sur 44 trades de l'ere D1, SIX sont gagnants sur les
    prix et perdants une fois les frais payes.

    L'ecart etait un chiffre ecrit a la main (0,05 R) pendant que le retour
    a l'equilibre en demande 0,092 :

        aller-retour de frais    0,069 R
        limite du stop a -0,2 %  0,023 R

    Il se CALCULE desormais, comme le plafond de cout et la borne de
    spread ailleurs dans ce depot.
    """

    @staticmethod
    def _marge(entree: float, distance: float, commission: float,
               plancher: float) -> float:
        cout = entree * (2 * commission + 0.002)
        return max(plancher, cout / distance)

    def test_la_marge_couvre_le_cout_reel(self):
        # MTL : entree 0,23177, stop a 1,6 ATR soit ~8,7 % du prix.
        entree, distance = 0.23177, 0.23177 * 0.087
        marge = self._marge(entree, distance, 0.0025, 0.08)
        cout_reel = (2 * 0.0025 + 0.002) / 0.087
        assert marge >= cout_reel - 1e-9, (
            f"marge {marge:.3f} R pour un cout de {cout_reel:.3f} R : le "
            "stop de break-even sortirait encore a perte")

    def test_le_reglage_reste_un_plancher(self):
        """Qui veut plus de marge doit pouvoir en demander plus."""
        entree, distance = 100.0, 50.0        # cout negligeable
        assert self._marge(entree, distance, 0.0025, 0.30) == pytest.approx(0.30)

    def test_le_moteur_calcule_au_lieu_de_choisir(self):
        import inspect

        from gold_bot.trade_manager import TradeManager
        source = inspect.getsource(TradeManager.manage)
        i = source.find("breakeven_at_r")
        bloc = source[i:i + 2200]
        assert "cfg.commission_pct" in bloc, (
            "le point mort ignore la commission : il annoncera de nouveau "
            "« le trade ne peut plus perdre » sur des trades qui perdent")
        assert "max(cfg.breakeven_offset_r" in bloc, (
            "le reglage n'est plus un plancher")

    def test_la_commission_suit_le_tarif_reel(self):
        import inspect

        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine._calibrer_sur_le_capital)
        assert "self.config.trade.commission_pct = frais" in source, (
            "le gestionnaire de trade garde un tarif devine : deux endroits "
            "decideraient du meme reglage, et le moins informe gagnerait")
