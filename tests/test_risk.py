"""Tests du money management : dimensionnement, echelle adaptative, coupe-circuits."""
from __future__ import annotations

import time
import unittest

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.core import ClosedTrade, Position, Side
from gold_bot.risk import EquityLadder, LadderStep, RiskConfig, RiskManager
from gold_bot.universe import Universe


class Base(unittest.TestCase):
    def setUp(self):
        self.universe = Universe()
        self.gold = self.universe.get("XAUUSD")
        self.rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_risk_pct=2.0, min_risk_pct=0.2))
        self.rm.sync_account(equity=10000.0, balance=10000.0, currency="EUR")


class TestDimensionnement(Base):
    def test_le_volume_respecte_le_risque_demande(self):
        # 1 % de 10 000 = 100 EUR ; stop a 5 $ ; 1 lot d'or = 100 oz
        # -> 100 / (5 x 100) = 0.20 lot
        d = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2665.0,
                                  universe_lookup=self.universe.get)
        self.assertTrue(d.allowed, d.reason)
        self.assertAlmostEqual(d.lots, 0.20, places=2)
        self.assertAlmostEqual(d.risk_amount, 100.0, delta=1.0)

    def test_un_stop_plus_large_reduit_le_volume(self):
        serre = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2665.0,
                                      universe_lookup=self.universe.get)
        large = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2635.0, 2695.0,
                                      universe_lookup=self.universe.get)
        self.assertLess(large.lots, serre.lots)
        # Le risque vise est le meme (1 % = 100 EUR). Le pas de lot empeche
        # de tomber pile dessus : on exige que le risque reel ne DEPASSE
        # jamais la cible, et reste a moins d'un pas de lot en dessous.
        for d in (serre, large):
            self.assertLessEqual(d.risk_amount, 100.0 + 1e-6, d.factors)
            pas_de_lot = self.gold.lot_step * self.gold.contract_size * d.stop_distance
            self.assertGreater(d.risk_amount, 100.0 - pas_de_lot)

    def test_l_arrondi_du_lot_ne_depasse_jamais_le_risque_vise(self):
        # Regression : un arrondi au plus proche gonflait le risque a chaque
        # trade (0.065 -> 0.07 lot = +8 % de risque, silencieusement).
        for stop in (2645.0, 2643.3, 2641.7, 2638.5):
            d = self.rm.size_position(self.gold, Side.BUY, 2650.0, stop, 2680.0,
                                      universe_lookup=self.universe.get)
            if d.allowed:
                self.assertLessEqual(d.risk_pct, 1.0 + 1e-9,
                                     f"risque depasse avec un stop a {stop}")

    def test_stop_nul_refuse(self):
        d = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2650.0, 2665.0,
                                  universe_lookup=self.universe.get)
        self.assertFalse(d.allowed)
        self.assertIn("stop-loss", d.reason)

    def test_ratio_insuffisant_refuse(self):
        d = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2651.0,
                                  universe_lookup=self.universe.get)
        self.assertFalse(d.allowed)
        self.assertIn("rendement/risque", d.reason)

    def test_petit_capital_refuse_plutot_que_sur_risquer(self):
        # 200 EUR de capital : le lot minimum (0.01) sur un stop de 5 $
        # represente 5 EUR, soit 2.5 % — au-dessus du plafond.
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_risk_pct=1.5))
        rm.sync_account(equity=200.0, balance=200.0)
        d = rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2665.0,
                             universe_lookup=self.universe.get)
        self.assertFalse(d.allowed)
        self.assertIn("plafond", d.reason)

    def test_le_levier_plafonne_le_volume(self):
        rm = RiskManager(RiskConfig(base_risk_pct=2.0, max_risk_pct=2.0, max_leverage=5.0))
        rm.sync_account(equity=10000.0, balance=10000.0)
        # Stop tres serre : sans plafond de levier le volume exploserait.
        d = rm.size_position(self.gold, Side.BUY, 2650.0, 2649.5, 2655.0,
                             universe_lookup=self.universe.get)
        notional = d.lots * 2650.0 * self.gold.contract_size
        self.assertLessEqual(notional, 10000.0 * 5.0 + 1.0)


class TestEchelleAdaptative(unittest.TestCase):
    """La taille monte avec les gains et descend avec les pertes."""

    def setUp(self):
        self.ladder = EquityLadder()

    def test_taille_neutre_a_la_reference(self):
        mult, _ = self.ladder.multiplier(1000.0, 1000.0)
        self.assertAlmostEqual(mult, 1.0)

    def test_la_taille_monte_avec_les_gains(self):
        m10, _ = self.ladder.multiplier(1100.0, 1000.0)
        m25, _ = self.ladder.multiplier(1250.0, 1000.0)
        m50, _ = self.ladder.multiplier(1500.0, 1000.0)
        self.assertGreater(m10, 1.0)
        self.assertGreater(m25, m10)
        self.assertGreater(m50, m25)

    def test_la_taille_descend_avec_les_pertes(self):
        m8, _ = self.ladder.multiplier(920.0, 1000.0)
        m15, _ = self.ladder.multiplier(850.0, 1000.0)
        m25, _ = self.ladder.multiplier(750.0, 1000.0)
        self.assertLess(m8, 1.0)
        self.assertLess(m15, m8)
        self.assertLess(m25, m15)

    def test_les_multiplicateurs_restent_bornes(self):
        haut, _ = self.ladder.multiplier(1_000_000.0, 1000.0)
        bas, _ = self.ladder.multiplier(1.0, 1000.0)
        self.assertLessEqual(haut, self.ladder.ceiling)
        self.assertGreaterEqual(bas, self.ladder.floor)

    def test_effet_sur_le_risque_reel(self):
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_risk_pct=2.0))
        rm.sync_account(equity=12500.0, balance=12500.0)
        rm.account.reference_equity = 10000.0        # +25 %
        risk, factors = rm.effective_risk_pct()
        self.assertGreater(risk, 1.0)
        self.assertTrue(any("x1.45" in f for f in factors), factors)

    def test_le_plafond_dur_n_est_jamais_franchi(self):
        rm = RiskManager(RiskConfig(base_risk_pct=1.5, max_risk_pct=2.0))
        rm.sync_account(equity=100000.0, balance=100000.0)
        rm.account.reference_equity = 10000.0        # +900 %
        risk, _ = rm.effective_risk_pct(extra_multiplier=3.0)
        self.assertLessEqual(risk, 2.0)


class TestCoupeCircuits(Base):
    def test_limite_de_perte_journaliere(self):
        self.rm.account.day_start_equity = 10000.0
        self.rm.sync_account(equity=9500.0, balance=9500.0)   # -5 %
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertIn("journaliere", why)

    def test_arret_sur_drawdown_maximal(self):
        self.rm.account.peak_equity = 10000.0
        self.rm.sync_account(equity=7500.0, balance=7500.0)   # -25 %
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertTrue(self.rm.account.halted)

    def test_pause_apres_pertes_consecutives(self):
        for i in range(4):
            self.rm.record_close(ClosedTrade(
                position_id=str(i), symbol="XAUUSD", side=Side.BUY, volume=0.1,
                entry_price=2650, exit_price=2645, opened_at=0, closed_at=time.time(),
                profit=-50.0, r_multiple=-1.0, reason="stop"))
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertIn("pause", why)

    def test_le_risque_diminue_apres_des_pertes(self):
        normal, _ = self.rm.effective_risk_pct()
        for i in range(3):
            self.rm.record_close(ClosedTrade(
                position_id=str(i), symbol="XAUUSD", side=Side.BUY, volume=0.1,
                entry_price=2650, exit_price=2645, opened_at=0, closed_at=time.time(),
                profit=-50.0, r_multiple=-1.0, reason="stop"))
        apres, factors = self.rm.effective_risk_pct()
        self.assertLess(apres, normal)
        self.assertTrue(any("pertes d'affilee" in f for f in factors))

    def test_gain_journalier_protege_la_journee(self):
        self.rm.account.day_start_equity = 10000.0
        self.rm.sync_account(equity=10700.0, balance=10700.0)   # +7 %
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertIn("journalier", why)


class TestExposition(Base):
    def _pos(self, symbol: str) -> Position:
        return Position(id=symbol, symbol=symbol, side=Side.BUY, volume=0.1,
                        entry_price=100.0, stop_loss=99.0, take_profit=103.0, opened_at=0.0)

    def test_pas_deux_positions_sur_le_meme_instrument(self):
        ok, why = self.rm.check_exposure(self.gold, Side.BUY, [self._pos("XAUUSD")],
                                         self.universe.get)
        self.assertFalse(ok)
        self.assertIn("deja ouverte", why)

    def test_pas_deux_positions_sur_un_groupe_correle(self):
        # XAUUSD et XAGUSD partagent le groupe "metals".
        ok, why = self.rm.check_exposure(self.gold, Side.BUY, [self._pos("XAGUSD")],
                                         self.universe.get)
        self.assertFalse(ok)
        self.assertIn("correle", why)

    def test_groupes_differents_autorises(self):
        ok, _ = self.rm.check_exposure(self.gold, Side.BUY, [self._pos("BTCUSD")],
                                       self.universe.get)
        self.assertTrue(ok)

    def test_le_risque_ouvert_est_compte(self):
        pos = Position(id="1", symbol="XAUUSD", side=Side.BUY, volume=0.20,
                       entry_price=2650.0, stop_loss=2645.0, take_profit=2665.0, opened_at=0.0)
        pct = self.rm.open_risk_pct([pos], self.universe.get)
        self.assertAlmostEqual(pct, 1.0, delta=0.05)     # 100 EUR sur 10 000

    def test_un_stop_en_profit_ne_compte_plus_comme_risque(self):
        pos = Position(id="1", symbol="XAUUSD", side=Side.BUY, volume=0.20,
                       entry_price=2650.0, stop_loss=2655.0, take_profit=2670.0, opened_at=0.0)
        self.assertEqual(self.rm.open_risk_pct([pos], self.universe.get), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


def _pos_carence(symbole="SOLUSD", entree=100.0, stop=98.0, pid="p1") -> Position:
    return Position(id=pid, symbol=symbole, side=Side.BUY, volume=1.0,
                    entry_price=entree, stop_loss=stop, take_profit=104.0,
                    opened_at=time.time(), initial_risk=2.0)


def _rm_carence(**reglages) -> RiskManager:
    rm = RiskManager(RiskConfig(**reglages))
    rm.sync_account(1000.0, 1000.0, "EUR")
    return rm


class TestLeDelaiDeCarenceNeTouchePasAuPyramidage:
    """Le rachat et le renforcement sont deux gestes opposes.

    Mesure des 1er-2 septembre : dix entrees successives sur UNIUSD en
    48 h (4,54 -> 5,49) pour 0,64 EUR de gain, six sur FILUSD dont la plus
    haute a pris -1,06 R. Le robot refermait puis rouvrait la MEME crypto
    plus haut, en repayant l'aller-retour. Esperance BRUTE +0,135 R contre
    NETTE -0,105 R : ce sont les frais de rotation qui retournent le signe,
    pas la qualite des entrees.

    Mais brider le rachat ne doit PAS brider la pyramide, sinon on tue le
    renforcement en croyant tuer la rotation.
    """

    @staticmethod
    def _ferme(symbole="SOLUSD", quand=None):
        from gold_bot.core import ClosedTrade
        return ClosedTrade(
            position_id="x", symbol=symbole, side=Side.BUY, volume=1.0,
            entry_price=100.0, exit_price=99.0,
            opened_at=(quand or time.time()) - 600,
            closed_at=quand or time.time(),
            profit=-1.0, r_multiple=-1.0, reason="stop")

    def test_le_rachat_immediat_est_refuse(self):
        rm = _rm_carence(cooldown_apres_sortie_minutes=120.0)
        rm.record_close(self._ferme())
        ok, why = rm.check_exposure(Universe().get("SOLUSD"), Side.BUY, [],
                                    Universe().get)
        assert not ok, "le rachat immediat passe encore"
        assert "trop tot" in why

    def test_le_rachat_est_permis_une_fois_le_delai_ecoule(self):
        rm = _rm_carence(cooldown_apres_sortie_minutes=30.0)
        rm.record_close(self._ferme(quand=time.time() - 3600))   # il y a 1 h
        ok, why = rm.check_exposure(Universe().get("SOLUSD"), Side.BUY, [],
                                    Universe().get)
        assert ok, why

    def test_un_autre_symbole_n_est_pas_bride(self):
        """La carence est PAR symbole, pas une pause generale."""
        rm = _rm_carence(cooldown_apres_sortie_minutes=120.0)
        rm.record_close(self._ferme(symbole="SOLUSD"))
        ok, why = rm.check_exposure(Universe().get("ETHUSD"), Side.BUY, [],
                                    Universe().get)
        assert ok, why

    def test_LA_PYRAMIDE_PASSE_MALGRE_LA_CARENCE(self):
        """Le test qui protege le chantier pyramidage.

        Symbole en carence ET position ouverte deja verrouillee en profit :
        c'est un renforcement, pas un rachat. Il doit passer.
        """
        rm = _rm_carence(pyramide_max=2, cooldown_apres_sortie_minutes=240.0)
        rm.record_close(self._ferme())                    # sortie a l'instant
        ouverte = _pos_carence(stop=100.5)                   # +0,25R deja verrouille
        ok, why = rm.check_exposure(Universe().get("SOLUSD"), Side.BUY,
                                    [ouverte], Universe().get)
        assert ok, (
            f"la carence bloque un etage de pyramide : {why!r} — "
            "renforcer un gagnant en cours n'est pas racheter ce qu'on "
            "vient de quitter")

    def test_desarme_par_defaut(self):
        assert RiskConfig().cooldown_apres_sortie_minutes == 0.0
        rm = _rm_carence()
        rm.record_close(self._ferme())
        ok, _ = rm.check_exposure(Universe().get("SOLUSD"), Side.BUY, [],
                                  Universe().get)
        assert ok, "le comportement par defaut a change"


class TestUnApportNEstPasUnePerformance:
    """L'echelle de capital ne doit pas recompenser un virement.

    Observe le 2 septembre : un depot de ~69 EUR (90 -> 158) a ete lu comme
    +63 % de gain. L'echelle anti-martingale est montee au cran x1,80 et le
    risque par trade est passe de 0,41 % a 1,08 %, au-dessus du palier
    « preuve » (0,6 %). La perte suivante a coute 2,28 EUR contre 0,30 a
    0,71 EUR les jours precedents : meme strategie, position 3x plus grosse.
    """

    def test_un_depot_ne_gonfle_pas_l_echelle(self):
        rm = RiskManager()
        rm.sync_account(90.0, 90.0, "EUR")
        avant = rm.account.reference_equity
        rm.sync_account(159.0, 159.0, "EUR")          # depot de 69 EUR
        assert rm.account.reference_equity > avant + 60, (
            f"reference restee a {rm.account.reference_equity:.2f} apres un "
            "depot de 69 EUR : l'echelle va lire un gain de +63 %")
        gain = rm.account.equity / rm.account.reference_equity - 1
        assert abs(gain) < 0.02, (
            f"l'echelle voit encore {gain * 100:+.1f} % de gain apres un depot")

    def test_une_chute_reste_traitee_comme_une_perte(self):
        """L'asymetrie est voulue, et c'est la moitie qui protege.

        Une chute inexpliquee peut etre un retrait ou une grosse perte. La
        prendre pour un retrait recalerait la reference vers le bas et
        desarmerait le coupe-circuit de drawdown au pire moment. On accepte
        donc de brimer la taille apres un vrai retrait : c'est l'erreur qui
        ne coute rien.
        """
        rm = RiskManager()
        rm.sync_account(160.0, 160.0, "EUR")
        ref = rm.account.reference_equity
        rm.sync_account(90.0, 90.0, "EUR")
        assert rm.account.reference_equity == ref, (
            "la reference a suivi une chute : le drawdown ne se verra plus")
        assert rm.account.peak_equity >= 160.0, (
            "le sommet a ete abaisse : le coupe-circuit de drawdown est mort")

    def test_un_vrai_gain_de_trading_est_bien_compte(self):
        """Le garde-fou ne doit pas avaler les vraies performances."""
        rm = RiskManager()
        rm.sync_account(100.0, 100.0, "EUR")
        ref = rm.account.reference_equity
        rm.account.realized_today = 3.0                # gagne en tradant
        rm.sync_account(103.0, 103.0, "EUR")
        assert rm.account.reference_equity == ref, (
            "un gain de trading a ete pris pour un apport : l'echelle ne "
            "montera jamais")


class TestLeRejeuAppliqueVraimentLaCarence:
    """Le piege qui a deja menti une fois.

    La carence vit dans `check_exposure`, que le rejeu n'appelle pas : il a
    sa propre porte d'entree. La premiere mesure a rendu des chiffres
    IDENTIQUES au temoin — au centieme et par paire — et on aurait conclu
    que la carence ne sert a rien alors qu'elle ne s'etait jamais
    declenchee. C'est exactement ce qui etait arrive au pyramidage.
    """

    def test_le_rejeu_refuse_bien_un_rachat_trop_tot(self):
        import inspect
        from gold_bot.backtest import Backtester
        src = inspect.getsource(Backtester.run)
        assert "carence_restante" in src, (
            "le rejeu n'applique pas le delai de carence : toute mesure "
            "rendra un resultat identique au temoin, sans rien casser")

    def test_la_carence_suit_l_horloge_qu_on_lui_donne(self):
        """En rejeu l'horloge est celle des bougies, pas celle du systeme."""
        rm = RiskManager(RiskConfig(cooldown_apres_sortie_minutes=60.0))
        rm.sync_account(1000.0, 1000.0, "EUR")
        from gold_bot.core import ClosedTrade
        t0 = 1_700_000_000.0
        rm.record_close(ClosedTrade(
            position_id="x", symbol="SOLUSD", side=Side.BUY, volume=1.0,
            entry_price=100.0, exit_price=99.0, opened_at=t0 - 600,
            closed_at=t0, profit=-1.0, r_multiple=-1.0, reason="stop"))
        assert rm.carence_restante("SOLUSD", now=t0 + 600) > 0, (
            "10 min apres la sortie, la carence de 60 min devrait tenir")
        assert rm.carence_restante("SOLUSD", now=t0 + 4000) == 0.0, (
            "66 min apres la sortie, la carence devrait etre levee")
