"""Tests de la gestion dynamique : break-even, trailing, extension du TP.

C'est le comportement le plus important du robot : on verifie qu'a
l'approche de l'objectif il repousse le TP ET remonte le stop, dans les
deux sens, et qu'il ne desserre jamais un stop deja place.
"""
from __future__ import annotations

import unittest

from helpers import flat_indicators, trending_indicators

from gold_bot.core import Position, Side, Tick
from gold_bot.trade_manager import ActionType, TradeManager, TradeManagerConfig, compute_momentum


def make_position(side: Side, entry: float, risk: float, tp_r: float = 2.0) -> Position:
    sign = side.sign
    return Position(
        id="T1", symbol="XAUUSD", side=side, volume=0.10,
        entry_price=entry,
        stop_loss=entry - sign * risk,
        take_profit=entry + sign * risk * tp_r,
        opened_at=0.0,
    )


def tick_at(price: float, spread: float = 0.30) -> Tick:
    return Tick(ts=1000.0, bid=price - spread / 2, ask=price + spread / 2)


class TestInitialLevels(unittest.TestCase):
    def test_stop_et_objectif_coherents_a_l_achat(self):
        tm = TradeManager(TradeManagerConfig(atr_stop_mult=1.6, tp_r_multiple=2.0, spread_buffer_mult=0.0))
        sl, tp = tm.initial_levels(Side.BUY, 2600.0, atr=2.0)
        self.assertLess(sl, 2600.0)
        self.assertGreater(tp, 2600.0)
        self.assertAlmostEqual(2600.0 - sl, 3.2, places=2)
        self.assertAlmostEqual(tp - 2600.0, 6.4, places=2)

    def test_stop_et_objectif_coherents_a_la_vente(self):
        tm = TradeManager(TradeManagerConfig(atr_stop_mult=1.6, tp_r_multiple=2.0, spread_buffer_mult=0.0))
        sl, tp = tm.initial_levels(Side.SELL, 2600.0, atr=2.0)
        self.assertGreater(sl, 2600.0)
        self.assertLess(tp, 2600.0)

    def test_le_spread_elargit_le_stop(self):
        tm = TradeManager(TradeManagerConfig(spread_buffer_mult=2.0))
        sl_sans, _ = tm.initial_levels(Side.BUY, 2600.0, atr=2.0, spread=0.0)
        sl_avec, _ = tm.initial_levels(Side.BUY, 2600.0, atr=2.0, spread=0.5)
        self.assertLess(sl_avec, sl_sans)

    def test_le_stop_reste_dans_les_bornes_atr(self):
        tm = TradeManager(TradeManagerConfig(min_stop_atr=0.8, max_stop_atr=3.0, spread_buffer_mult=0.0))
        # Une structure absurdement lointaine doit etre ramenee au plafond.
        sl, _ = tm.initial_levels(Side.BUY, 2600.0, atr=2.0, structure_stop=2500.0)
        self.assertAlmostEqual(2600.0 - sl, 3.2, places=2)
        # Une structure trop proche est ramenee au plancher.
        sl, _ = tm.initial_levels(Side.BUY, 2600.0, atr=2.0, structure_stop=2599.9)
        self.assertGreaterEqual(2600.0 - sl, 1.6 - 1e-9)


class TestBreakEven(unittest.TestCase):
    def test_le_stop_passe_a_l_entree_au_seuil(self):
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(breakeven_at_r=0.8, partial_enabled=False))
        pos = make_position(Side.BUY, 2600.0, risk=4.0)
        actions = tm.manage(pos, tick_at(2603.4), ind)   # 0.85R
        self.assertTrue(pos.breakeven_done)
        self.assertGreaterEqual(pos.stop_loss, pos.entry_price)
        self.assertTrue(any(a.type is ActionType.MODIFY_STOP for a in actions))

    def test_pas_de_break_even_avant_le_seuil(self):
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(breakeven_at_r=0.8, partial_enabled=False))
        pos = make_position(Side.BUY, 2600.0, risk=4.0)
        tm.manage(pos, tick_at(2601.0), ind)             # 0.25R
        self.assertFalse(pos.breakeven_done)
        self.assertLess(pos.stop_loss, pos.entry_price)

    def test_le_break_even_reste_sain_sur_un_gros_volume(self):
        """Trouve le 18 sept. en demo : `initial_risk` est deja la distance
        prix (1R), diviser par le volume l'ecrasait sur les altcoins a gros
        volume/prix unitaire bas (des milliers d'unites, ex. STRK, ROSE) --
        `cout_r` explosait, le stop de break-even partait a des annees-
        lumiere du prix reel, et la position se cloturait aussitot sur un
        "profit" fictif de plusieurs dizaines de R. Les positions a volume
        < 1 (BTC, ETH) masquaient le bug par coincidence (diviser AUGMENTE
        la distance dans ce sens, ce qui fait retomber sous le plancher)."""
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(breakeven_at_r=0.8, partial_enabled=False,
                                             breakeven_offset_r=0.08))
        entry, risk = 0.0388, 0.003   # ordre de grandeur STRKUSD reel
        pos = Position(id="T1", symbol="STRKUSD", side=Side.BUY, volume=900.0,
                       entry_price=entry, stop_loss=entry - risk,
                       take_profit=entry + risk * 2.0, opened_at=0.0)
        # spread par defaut de tick_at() (0,30) est pense pour l'or a 2600 --
        # sur un prix a 0,04 ca ecraserait tout, d'ou un spread realiste ici.
        tm.manage(pos, tick_at(entry + risk * 0.85, spread=0.0001), ind)   # 0.85R
        self.assertTrue(pos.breakeven_done)
        # Le stop de break-even doit rester tout pres de l'entree (quelques
        # % au plus) -- jamais a des multiples du prix lui-meme.
        self.assertLess(pos.stop_loss, entry * 1.05)
        self.assertGreaterEqual(pos.stop_loss, entry)


class TestExtensionObjectif(unittest.TestCase):
    """Le comportement demande : TP repousse + stop remonte, automatiquement."""

    def test_achat_le_tp_est_repousse_a_l_approche(self):
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(partial_enabled=False))
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=2.0)   # TP = 2608
        tp_initial = pos.take_profit

        # 90 % du chemin vers le TP, tendance haussiere franche
        actions = tm.manage(pos, tick_at(2607.2), ind)

        self.assertGreater(pos.take_profit, tp_initial, "le TP doit etre repousse plus haut")
        self.assertEqual(pos.tp_extensions, 1)
        self.assertTrue(any(a.type is ActionType.MODIFY_TARGET for a in actions))

    def test_achat_le_stop_monte_en_meme_temps_que_le_tp(self):
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(partial_enabled=False))
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=2.0)
        stop_initial = pos.stop_loss

        tm.manage(pos, tick_at(2607.2), ind)

        self.assertGreater(pos.stop_loss, stop_initial, "le stop doit remonter")
        self.assertGreater(pos.stop_loss, pos.entry_price, "le gain doit etre verrouille")
        self.assertGreaterEqual(pos.locked_r(), 0.3)

    def test_vente_le_tp_descend_et_le_stop_descend(self):
        ind = trending_indicators(-1)
        tm = TradeManager(TradeManagerConfig(partial_enabled=False))
        pos = make_position(Side.SELL, 2600.0, risk=4.0, tp_r=2.0)  # TP = 2592
        tp_initial, stop_initial = pos.take_profit, pos.stop_loss

        tm.manage(pos, tick_at(2592.8), ind)

        self.assertLess(pos.take_profit, tp_initial, "sur une vente le TP doit descendre")
        self.assertLess(pos.stop_loss, stop_initial, "sur une vente le stop doit descendre")
        self.assertLess(pos.stop_loss, pos.entry_price, "le gain doit etre verrouille")
        self.assertGreaterEqual(pos.locked_r(), 0.3)

    def test_extensions_successives_plafonnees(self):
        ind = trending_indicators(1)
        cfg = TradeManagerConfig(partial_enabled=False, max_extensions=3)
        tm = TradeManager(cfg)
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=2.0)

        price = 2607.2
        for _ in range(12):
            tm.manage(pos, tick_at(price), ind)
            # on avance toujours jusqu'a 92 % du nouvel objectif
            price = pos.entry_price + 0.92 * (pos.take_profit - pos.entry_price)

        self.assertEqual(pos.tp_extensions, 3, "le nombre d'extensions doit etre plafonne")

    def test_pas_d_extension_si_la_dynamique_faiblit(self):
        ind = flat_indicators()
        tm = TradeManager(TradeManagerConfig(partial_enabled=False))
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=2.0)
        tp_initial = pos.take_profit

        actions = tm.manage(pos, tick_at(2607.2), ind)

        self.assertEqual(pos.take_profit, tp_initial, "objectif inchange si la dynamique ne suit pas")
        self.assertEqual(pos.tp_extensions, 0)
        self.assertTrue(any(a.type is ActionType.MODIFY_STOP for a in actions),
                        "le stop doit au contraire etre resserre")

    def test_le_gain_verrouille_ne_recule_jamais(self):
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(partial_enabled=False))
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=2.0)

        locked = -1e9
        price = 2603.0
        for _ in range(20):
            tm.manage(pos, tick_at(price), ind)
            self.assertGreaterEqual(pos.locked_r() + 1e-9, locked,
                                    "le stop ne doit jamais etre desserre")
            locked = pos.locked_r()
            price += 1.5


class TestTrailing(unittest.TestCase):
    def test_le_stop_suit_le_prix_au_dela_de_1r(self):
        ind = trending_indicators(1)
        # breakeven_at_r desarme (hors de portee des prix testes) : ce test
        # verifie le SUIVEUR seul. Sans ca, le premier tick (1.5R, au-dessus
        # du seuil de break-even par defaut) declenche AUSSI le break-even --
        # et sur ce risque de 4,0 (0,15 % de 2600), les frais (0,7 % en
        # aller-retour) dominent largement la distance de stop, ce qui est
        # un cas reel et desormais correctement gere (voir
        # TestBreakEven::test_le_break_even_reste_sain_sur_un_gros_volume)
        # mais qui n'a rien a voir avec ce que ce test-ci verifie.
        tm = TradeManager(TradeManagerConfig(partial_enabled=False, extend_enabled=False,
                                             breakeven_at_r=99.0))
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=6.0)

        tm.manage(pos, tick_at(2606.0), ind)
        stop1 = pos.stop_loss
        tm.manage(pos, tick_at(2612.0), ind)
        self.assertGreater(pos.stop_loss, stop1, "le stop suiveur doit progresser avec le prix")

    def test_le_stop_ne_recule_pas_si_le_prix_recule(self):
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(partial_enabled=False, extend_enabled=False))
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=6.0)

        tm.manage(pos, tick_at(2612.0), ind)
        stop_haut = pos.stop_loss
        tm.manage(pos, tick_at(2607.0), ind)
        self.assertEqual(pos.stop_loss, stop_haut)


class TestPrisePartielle(unittest.TestCase):
    def test_prise_partielle_a_1r_une_seule_fois(self):
        ind = trending_indicators(1)
        tm = TradeManager(TradeManagerConfig(partial_at_r=1.0, partial_fraction=0.4))
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=4.0)

        a1 = tm.manage(pos, tick_at(2604.5), ind)
        partials = [a for a in a1 if a.type is ActionType.PARTIAL_CLOSE]
        self.assertEqual(len(partials), 1)
        self.assertAlmostEqual(partials[0].volume, 0.04, places=6)

        a2 = tm.manage(pos, tick_at(2605.5), ind)
        self.assertFalse([a for a in a2 if a.type is ActionType.PARTIAL_CLOSE])


class TestSortiesSecurite(unittest.TestCase):
    def test_sortie_sur_retournement_avec_gain_acquis(self):
        ind = trending_indicators(-1)          # dynamique franchement baissiere
        tm = TradeManager(TradeManagerConfig())
        pos = make_position(Side.BUY, 2600.0, risk=4.0, tp_r=3.0)
        actions = tm.manage(pos, tick_at(2603.0), ind)   # +0.75R
        self.assertTrue(any(a.type is ActionType.CLOSE for a in actions))

    def test_stop_temporel_sur_position_qui_stagne(self):
        ind = flat_indicators()
        tm = TradeManager(TradeManagerConfig(time_stop_minutes=60.0, time_stop_min_r=0.25))
        pos = make_position(Side.BUY, 2600.0, risk=4.0)
        actions = tm.manage(pos, tick_at(2600.2), ind, now=pos.opened_at + 3600 * 2)
        self.assertTrue(any(a.type is ActionType.CLOSE for a in actions))


class TestMomentum(unittest.TestCase):
    def test_dynamique_positive_en_tendance_haussiere(self):
        m = compute_momentum(make_position(Side.BUY, 2600.0, 4.0), trending_indicators(1))
        self.assertGreater(m.score, 0.35)

    def test_dynamique_negative_a_contre_sens(self):
        m = compute_momentum(make_position(Side.BUY, 2600.0, 4.0), trending_indicators(-1))
        self.assertLess(m.score, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
