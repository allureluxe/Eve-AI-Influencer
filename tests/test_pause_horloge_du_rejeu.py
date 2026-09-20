"""La pause apres pertes doit vivre dans le temps DU REJEU.

CE QUE CE TEST AURAIT EVITE. `record_close` posait
`paused_until = time.time() + 45 min` -- l'horloge du serveur. Le rejeu,
lui, demande `can_trade(ts=candle.ts)` avec une date de 2024. A la 4e
perte, `now < paused_until` devenait vrai pour TOUTES les bougies
suivantes, et le rejeu cessait d'ouvrir quoi que ce soit jusqu'a la fin
de la periode.

Mesure du 20 septembre, 40 paires, 900 bougies : 21 720 refus « pause
apres pertes » contre 150 refus de strategie. Le rejeu de portefeuille
etait bloque 99,2 % du temps. Tous les chiffres qu'il a rendus mesuraient
un robot a l'arret.

Aucun test ne pouvait le voir, parce que tous les tests existants
appellent `can_trade()` sans `ts` -- donc avec la meme horloge des deux
cotes, ou le defaut est invisible. C'est la variante « deux horloges »
du piege recense quatre fois dans le CLAUDE.md : un garde-fou qui
s'execute, mais pas dans le monde qu'on croit.
"""
from __future__ import annotations

import time

from gold_bot.core import ClosedTrade, Side
from gold_bot.risk import RiskConfig, RiskManager


ANCIEN = 1_700_000_000.0        # novembre 2023
MINUTE = 60.0


def _perte(ts: float, n: int) -> ClosedTrade:
    return ClosedTrade(
        position_id=f"t{n}", symbol="BTCEUR", side=Side.BUY, volume=1.0,
        entry_price=100.0, exit_price=99.0, profit=-1.0, r_multiple=-1.0,
        opened_at=ts - 3600.0, closed_at=ts, reason="stop")


def _gestionnaire() -> RiskManager:
    r = RiskManager(RiskConfig(max_consecutive_losses=4,
                               pause_after_losses_minutes=45.0))
    r.account.equity = 3300.0
    r.account.balance = 3300.0
    r.account.peak_equity = 3300.0
    return r


class TestLaPauseSuitLHorlogeDuRejeu:

    def test_quatre_pertes_historiques_ne_bloquent_pas_tout_l_avenir(self):
        r = _gestionnaire()
        for n in range(4):
            r.record_close(_perte(ANCIEN + n * 86400.0, n))

        # Une heure APRES la derniere perte, dans le temps du rejeu :
        # la pause de 45 minutes est passee, on doit pouvoir trader.
        ok, pourquoi = r.can_trade([], ts=ANCIEN + 3 * 86400.0 + 60 * MINUTE)
        assert ok, (
            f"refus « {pourquoi} » une heure apres la derniere perte : la "
            "pause a ete posee sur l'horloge du serveur, pas sur celle du "
            "rejeu -- toute la periode restante est bloquee")

    def test_la_pause_mord_quand_meme_pendant_ses_45_minutes(self):
        # Le garde-fou doit rester un garde-fou : la corriger ne doit pas
        # revenir a la desarmer.
        r = _gestionnaire()
        for n in range(4):
            r.record_close(_perte(ANCIEN + n * 60.0, n))
        ok, pourquoi = r.can_trade([], ts=ANCIEN + 3 * 60.0 + 10 * MINUTE)
        assert not ok
        assert "pause apres pertes" in pourquoi

    def test_le_compteur_est_purge_une_fois_la_pause_payee(self):
        r = _gestionnaire()
        for n in range(4):
            r.record_close(_perte(ANCIEN + n * 60.0, n))
        r.can_trade([], ts=ANCIEN + 60 * MINUTE)
        assert r.account.consecutive_losses == 0, (
            "sans la purge, chaque perte suivante redeclenche la pause et "
            "le robot ne sort plus jamais du regime punitif")
        assert r.account.paused_until == 0.0

    def test_en_reel_le_comportement_est_inchange(self):
        # Les appelants du robot reel ne passent pas de `ts`. La pause
        # doit continuer de mordre exactement comme avant.
        r = _gestionnaire()
        maintenant = time.time()
        for n in range(4):
            r.record_close(_perte(maintenant - 10.0 + n, n))
        ok, pourquoi = r.can_trade([])
        assert not ok
        assert "pause apres pertes" in pourquoi
