"""Money management : la demande du tout premier message.

« un bon money management [...] une mise de lot progressif ou regressif en
fonction du capital »

Ces tests verifient que c'est reellement le cas, et surtout que le robot
reduit sa taille quand il perd — le sens qui compte. Un systeme qui
augmente la mise apres une perte pour « se refaire » est la facon la plus
rapide de detruire un compte, et elle a un nom : la martingale.
"""
from __future__ import annotations

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.core import Side
from gold_bot.risk import EquityLadder, RiskConfig, RiskManager
from gold_bot.universe import Universe


class TestEchelleDeCapital:
    """Mise progressive a la hausse, regressive a la baisse."""

    def setup_method(self):
        self.echelle = EquityLadder()

    def test_le_gain_augmente_la_taille(self):
        assert self.echelle.multiplier(242, 220)[0] > 1.0     # +10 %
        assert self.echelle.multiplier(275, 220)[0] > \
               self.echelle.multiplier(242, 220)[0]           # +25 % > +10 %

    def test_la_perte_reduit_la_taille(self):
        """Le sens qui compte : perdre doit faire baisser la mise."""
        assert self.echelle.multiplier(209, 220)[0] < 1.0     # -5 %
        assert self.echelle.multiplier(165, 220)[0] < \
               self.echelle.multiplier(209, 220)[0]           # -25 % < -5 %

    def test_ce_n_est_pas_une_martingale(self):
        """A capital decroissant, la taille doit decroitre elle aussi."""
        tailles = [self.echelle.multiplier(eq, 220)[0]
                   for eq in (330, 275, 242, 220, 209, 187, 165, 140)]
        assert tailles == sorted(tailles, reverse=True), \
            "la taille doit diminuer de facon monotone quand le capital baisse"

    def test_bornes_respectees(self):
        assert self.echelle.multiplier(10_000, 220)[0] <= self.echelle.ceiling
        assert self.echelle.multiplier(1, 220)[0] >= self.echelle.floor

    def test_reference_inconnue_reste_neutre(self):
        assert self.echelle.multiplier(220, 0)[0] == 1.0

    def test_explication_fournie(self):
        _, pourquoi = self.echelle.multiplier(242, 220)
        assert "%" in pourquoi and "x" in pourquoi


class TestReductionParLesPertes:
    """Deux mecanismes de reduction s'ajoutent a l'echelle."""

    def gestionnaire(self, **kw):
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, min_risk_pct=0.1,
                                    max_risk_pct=2.0, **kw))
        rm.sync_account(equity=220.0, balance=220.0, currency="EUR")
        return rm

    def test_les_pertes_consecutives_reduisent(self):
        rm = self.gestionnaire()
        normal, _ = rm.effective_risk_pct()
        rm.account.consecutive_losses = 3
        apres, facteurs = rm.effective_risk_pct()
        assert apres < normal
        assert any("d'affilee" in f for f in facteurs)

    def test_le_drawdown_reduit(self):
        rm = self.gestionnaire()
        normal, _ = rm.effective_risk_pct()
        rm.account.peak_equity = 300.0        # drawdown de ~27 %
        apres, facteurs = rm.effective_risk_pct()
        assert apres < normal
        assert any("drawdown" in f for f in facteurs)

    def test_le_plafond_dur_n_est_jamais_franchi(self):
        """Meme apres une serie de gains, le plafond tient."""
        rm = self.gestionnaire()
        rm.account.reference_equity = 100.0
        rm.account.equity = 1000.0            # +900 %
        risque, _ = rm.effective_risk_pct(extra_multiplier=5.0)
        assert risque <= rm.config.max_risk_pct + 1e-9


class TestGlissement:
    """Le poste de cout qui n'apparait sur aucune facture."""

    def cout(self, ratio_glissement: float) -> float:
        univers = Universe()
        btc = univers.get("BTCUSD")
        rm = RiskManager(RiskConfig(commission_pct=0.001,
                                    slippage_spread_ratio=ratio_glissement))
        rm.sync_account(equity=1000.0, balance=1000.0, currency="EUR")
        return rm.execution_cost(btc, 0.001, 77000.0, spread=7.7)

    def test_le_glissement_augmente_le_cout(self):
        assert self.cout(0.5) > self.cout(0.0)

    def test_le_glissement_compte_les_deux_cotes(self):
        """Entree et sortie subissent chacune un glissement."""
        base = self.cout(0.0)
        un_demi = self.cout(0.5) - base
        un_entier = self.cout(1.0) - base
        assert un_entier == pytest.approx(2 * un_demi)

    def test_a_zero_le_comportement_est_celui_d_avant(self):
        """Le glissement doit pouvoir etre desactive pour comparer."""
        assert self.cout(0.0) > 0

    def test_le_spread_n_est_compte_qu_une_fois(self):
        """On achete a l'offre et on revend a la demande.

        L'ecart n'est franchi qu'une seule fois sur l'aller-retour. Le
        compter deux fois surestimerait le cout et refuserait des trades
        valables.
        """
        univers = Universe()
        btc = univers.get("BTCUSD")
        rm = RiskManager(RiskConfig(commission_pct=0.0, slippage_spread_ratio=0.0))
        rm.sync_account(equity=1000.0, balance=1000.0, currency="EUR")
        attendu = 7.7 * btc.value_per_price_unit(0.001)
        assert rm.execution_cost(btc, 0.001, 77000.0, spread=7.7) == pytest.approx(attendu)


class TestCoupeCircuits:
    def gestionnaire(self):
        rm = RiskManager(RiskConfig(daily_loss_limit_pct=5.0, weekly_loss_limit_pct=10.0,
                                    max_drawdown_pct=25.0))
        rm.sync_account(equity=220.0, balance=220.0, currency="EUR")
        return rm

    def test_perte_journaliere_arrete_la_journee(self):
        rm = self.gestionnaire()
        rm.account.day_start_equity = 220.0
        rm.account.equity = 200.0             # -9 %
        autorise, raison = rm.can_trade()
        assert not autorise and raison

    def test_drawdown_maximal_arrete_tout(self):
        rm = self.gestionnaire()
        rm.account.peak_equity = 400.0
        rm.account.equity = 250.0             # -37 %
        autorise, _ = rm.can_trade()
        assert not autorise
        assert rm.account.halted, "le drawdown maximal doit couper le robot"

    def test_compte_sain_peut_trader(self):
        rm = self.gestionnaire()
        autorise, raison = rm.can_trade()
        assert autorise, raison


class TestSpreadRelatifCrypto:
    """Un spread absolu n'a aucun sens sur 85 cryptos.

    Du BTC a 60 000 EUR au PEPE a 0,00001, la meme valeur absolue serait
    negligeable d'un cote et interdirait tout trade de l'autre.
    """

    def test_le_spread_suit_le_prix(self):
        from gold_bot.universe import Universe, spread_estime
        u = Universe()
        btc = u.get("BTCUSD")
        assert spread_estime(btc, 60000.0) > spread_estime(btc, 0.5)

    def test_meme_ratio_a_toutes_les_echelles(self):
        from gold_bot.universe import SPREAD_CRYPTO_RATIO, Universe, spread_estime
        u = Universe()
        btc = u.get("BTCUSD")
        for prix in (60000.0, 0.5, 0.00001):
            assert spread_estime(btc, prix) / prix == pytest.approx(SPREAD_CRYPTO_RATIO)

    def test_les_metaux_gardent_leur_spread_absolu(self):
        """L'or se cote en dollars, son spread aussi : rien a changer."""
        from gold_bot.universe import Universe, spread_estime
        or_ = Universe().get("XAUUSD")
        assert spread_estime(or_, 2500.0) == or_.typical_spread

    def test_les_cryptos_reglees_a_la_main_ne_sont_plus_penalisees(self):
        """Regression : XRP portait 0,0008 pour un prix de 0,5 EUR.

        Soit 16 points de base la ou le reel en vaut 1 ou 2 — ce qui
        provoquait 1090 rejets « spread » sur 1439 bougies.
        """
        from gold_bot.universe import Universe, spread_estime
        xrp = Universe().get("XRPUSD")
        assert spread_estime(xrp, 0.5) < xrp.typical_spread


class TestPausePurgee:
    """La pause est une sanction, pas une condamnation a perpetuite."""

    def gestionnaire(self):
        rm = RiskManager(RiskConfig(max_consecutive_losses=4,
                                    pause_after_losses_minutes=240.0))
        rm.sync_account(equity=1000.0, balance=1000.0, currency="EUR")
        return rm

    def test_la_pause_purgee_remet_le_compteur_a_zero(self):
        """Sans cela, chaque perte suivante redeclenche la pause.

        Mesure sur ADA : 1044 bougies bloquees sur 1439, soit 73 % de la
        periode passee en regime punitif dont le robot ne sortait plus.
        """
        import time
        rm = self.gestionnaire()
        rm.account.consecutive_losses = 6
        rm.account.paused_until = time.time() - 1      # pause deja terminee
        autorise, raison = rm.can_trade()
        assert rm.account.consecutive_losses == 0, raison
        assert autorise, raison

    def test_la_pause_en_cours_bloque_toujours(self):
        import time
        rm = self.gestionnaire()
        rm.account.consecutive_losses = 5
        rm.account.paused_until = time.time() + 3600
        autorise, raison = rm.can_trade()
        assert not autorise
        assert "pause" in raison
        assert rm.account.consecutive_losses == 5, "le compteur ne bouge pas pendant la pause"


class TestConstructionDuMoteur:
    """Regressions d'ordre d'initialisation.

    Deux fois de suite, du code a ete insere avant ce dont il dependait.
    Les tests ne le voyaient pas parce qu'aucun ne construisait le moteur
    complet — exactement le trou qui avait laissé passer les defauts du
    robot tiers.
    """

    def test_le_moteur_se_construit_entierement(self, tmp_path, monkeypatch):
        import logging
        logging.disable(logging.CRITICAL)
        for cle in ("BITVAVO_API_KEY", "BITVAVO_API_SECRET",
                    "OKX_API_KEY", "GB_STATE_FILE", "GB_TRADES_FILE"):
            monkeypatch.delenv(cle, raising=False)
        monkeypatch.chdir(tmp_path)

        from gold_bot.engine import TradingEngine
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load()
        cfg.engine.broker = "paper"
        cfg.engine.offline = True
        moteur = TradingEngine(cfg)

        # La ponderation lisait le journal AVANT que celui-ci existe.
        assert moteur.journal is not None
        assert moteur.poids is not None
        assert moteur.strategy.poids is moteur.poids

    def test_le_backtest_s_importe_avec_ses_dependances(self):
        """`spread_estime` manquait a l'import : cinq symboles en echec."""
        import inspect

        from gold_bot.backtest import Backtester
        source = inspect.getsource(Backtester.run)
        if "spread_estime" in source:
            import gold_bot.backtest as mod
            assert hasattr(mod, "spread_estime"), \
                "spread_estime est utilise mais pas importe"
