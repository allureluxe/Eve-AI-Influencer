"""Un signal journalier ne se prend qu'une fois par jour.

LE DEFAUT, trouve le 12 septembre 2026 en regardant MTL. La strategie est
journaliere : elle a UN signal par jour et par crypto, la cassure du
plus-haut de 20 jours. Mais le robot reevalue la bougie du jour toutes
les 10 secondes — et tant qu'elle n'est pas close, le prix repasse
au-dessus du canal plusieurs fois. Il prend donc trois fois le meme
signal, et paie trois allers-retours pour un.

    MTL    01h30 · 05h26 · 14h49 · 15h56   le meme jour, +0,01 EUR au total
    BLUR   15h06 · 15h16 · 16h12           -0,87 EUR
    SAGA   20h26 · 21h10 · 21h38           -1,41 EUR

Sur les 51 trades de l'ere D1 : 14 entrees en trop, soit 27 % des trades,
pour +1,51 EUR de gain brut et 1,54 EUR de frais — exactement rien.

POURQUOI AUCUNE MESURE NE L'AVAIT VU. Le banc d'essai avance en bougies
journalieres : une bougie, une decision. Il ne PEUT pas reproduire ce
defaut. Les delais de carence mesures dessus refusaient donc de vraies
entrees du LENDEMAIN — autre chose, et defavorable a juste titre.

Ce n'est pas un reglage a optimiser : c'est une incoherence a supprimer.
"""
from __future__ import annotations

import datetime as dt

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.risk import RiskConfig, RiskManager

MIDI = dt.datetime(2026, 9, 12, 12, 0, tzinfo=dt.timezone.utc).timestamp()


def _gestionnaire(**kw) -> RiskManager:
    rm = RiskManager(RiskConfig(carence_meme_bougie=True,
                                unite_du_signal="D1", **kw))
    rm._derniere_sortie["BTCUSD"] = MIDI
    return rm


class TestLaRegleEstArmee:

    def test_dans_la_config_en_service(self):
        from gold_bot.settings import BotConfig

        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.risk.carence_meme_bougie is True, (
            "le robot reprendra plusieurs fois le meme signal journalier : "
            "27 % de trades en doublon, payes en frais pour rien")

    def test_l_unite_suit_la_strategie(self):
        """Le delai doit couvrir la bougie du SIGNAL, pas une autre."""
        from gold_bot.settings import BotConfig

        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.risk.unite_du_signal == cfg.strategy.entry_tf, (
            f"la carence couvre du {cfg.risk.unite_du_signal} alors que le "
            f"signal est en {cfg.strategy.entry_tf} : elle protegerait la "
            "mauvaise duree")


class TestLeMemeJourEstRefuse:

    def test_racheter_quatre_heures_apres_attend(self):
        rm = _gestionnaire()
        reste = rm.carence_restante("BTCUSD", MIDI + 4 * 3600)
        assert reste > 0, "le rachat du meme jour passe encore"
        # Il doit attendre jusqu'a la bougie suivante, pas une duree fixe.
        assert abs(reste - 8 * 60) < 1, f"{reste:.0f} min au lieu de 480"

    def test_le_lendemain_est_libre(self):
        """La carence ne doit PAS bloquer une vraie entree du jour suivant.

        C'est la difference avec un delai en heures, et c'est ce que les
        mesures du banc d'essai avaient trouve defavorable a juste titre.
        """
        rm = _gestionnaire()
        assert rm.carence_restante("BTCUSD", MIDI + 20 * 3600) == 0.0

    def test_une_autre_crypto_n_est_pas_concernee(self):
        rm = _gestionnaire()
        assert rm.carence_restante("ETHUSD", MIDI + 60) == 0.0

    def test_desarme_ne_change_rien(self):
        rm = RiskManager(RiskConfig())
        rm._derniere_sortie["BTCUSD"] = MIDI
        assert rm.carence_restante("BTCUSD", MIDI + 60) == 0.0


class TestLePyramidageNEstPasTouche:
    """Renforcer une position ouverte est un autre geste que racheter.

    Les confondre desarmerait le pyramidage, qui fait tout le benefice de
    cette strategie : 17 % des trades rapportent 1 335 EUR quand les 83 %
    restants en perdent 646.
    """

    def test_le_renforcement_ignore_la_carence(self):
        import inspect

        source = inspect.getsource(RiskManager.peut_renforcer)
        assert "carence" not in source.lower() or "ne s'applique pas" in source, (
            "le delai de carence s'applique au renforcement : il tuerait "
            "le pyramidage, d'ou vient tout le benefice")


def _trade(symbol: str, closed_at: float, profit: float):
    from gold_bot.core import ClosedTrade, Side
    return ClosedTrade(position_id=f"{symbol}-{closed_at}", symbol=symbol,
                       side=Side.BUY, volume=1.0, entry_price=1.0,
                       exit_price=1.0, opened_at=closed_at - 3600,
                       closed_at=closed_at, profit=profit, r_multiple=0.0,
                       reason="stop")


class TestLaCarenceSurvitAuRedemarrage:
    """1er oct. 2026 : `_derniere_sortie` ne vivait qu'en memoire. Les demos,
    qui redemarraient jusqu'a 9 fois par jour, ont rachete 10 fois le
    meme jour alors que la regle etait armee. Le reel avait la meme fuite."""

    def test_un_robot_neuf_relit_la_sortie_dans_le_journal(self):
        rm = RiskManager(RiskConfig(carence_meme_bougie=True, unite_du_signal="D1"))
        rm.memoriser_sorties([_trade("BTCUSD", MIDI, -5.0)])
        assert rm.carence_restante("BTCUSD", MIDI + 3600) > 0, (
            "apres un redemarrage, le rachat du meme jour repasse")

    def test_la_sortie_la_plus_recente_l_emporte(self):
        rm = RiskManager(RiskConfig(carence_meme_bougie=True, unite_du_signal="D1"))
        hier = MIDI - 86400
        rm.memoriser_sorties([_trade("BTCUSD", MIDI, 1.0), _trade("BTCUSD", hier, 1.0)])
        assert rm._derniere_sortie["BTCUSD"] == MIDI

    def test_aucun_compteur_n_est_touche(self):
        rm = RiskManager(RiskConfig())
        rm.memoriser_sorties([_trade("BTCUSD", MIDI, -5.0)] * 5)
        assert rm.account.consecutive_losses == 0
        assert rm.account.realized_today == 0.0

    def test_le_moteur_relit_le_journal_au_demarrage(self):
        import inspect
        from gold_bot.engine import TradingEngine
        assert "memoriser_sorties" in inspect.getsource(TradingEngine.start)


class TestRachatApresGainExperience:
    """Desarmee par defaut ; a mesurer sur une demo avant tout armement."""

    def test_desarmee_par_defaut_et_dans_le_reel(self):
        from gold_bot.settings import BotConfig
        assert RiskConfig().rachat_meme_bougie_apres_gain is False
        assert BotConfig.load("robot.bitvavo.json").risk.rachat_meme_bougie_apres_gain is False

    def test_armee_elle_laisse_racheter_apres_un_gain(self):
        rm = RiskManager(RiskConfig(carence_meme_bougie=True, unite_du_signal="D1",
                                    rachat_meme_bougie_apres_gain=True))
        rm.record_close(_trade("BTCUSD", MIDI, 3.0))
        assert rm.carence_restante("BTCUSD", MIDI + 3600) == 0.0

    def test_armee_elle_bloque_toujours_apres_une_perte(self):
        rm = RiskManager(RiskConfig(carence_meme_bougie=True, unite_du_signal="D1",
                                    rachat_meme_bougie_apres_gain=True))
        rm.record_close(_trade("BTCUSD", MIDI, -3.0))
        assert rm.carence_restante("BTCUSD", MIDI + 3600) > 0, (
            "un stop perdant (le cas PROMPT) doit attendre la bougie suivante")
