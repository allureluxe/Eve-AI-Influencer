"""Un journal noye ne vaut pas mieux qu'un journal muet.

Deux mesures en production le 30 aout, sur la meme cadence de 3 secondes :

- 70 instruments en sommeil sur le spread, re-annonces nominativement a
  chaque cycle : environ 1 400 lignes par minute qui disent toutes la
  meme chose, et qui noient la seule qui compte —
  « aucune opportunite (volatilite x7) ».
- sept cryptos refusees a la volatilite, avec un motif affichant a la
  fois le percentile et le ratio ATR/prix sans dire lequel des deux
  refusait. C'est le plancher ABSOLU qui mordait (0,40 % d'ATR mesure
  pour 0,75 % exiges), pas le percentile — mais on ne pouvait pas le
  lire.

Un motif de refus qui ne se lit pas fait chercher du mauvais cote
pendant des heures. C'est arrive deux fois sur ce depot.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.scanner import ScanResult, Scanner
from gold_bot.settings import BotConfig
from gold_bot.strategy import Strategy, StrategyConfig
from gold_bot.trade_manager import TradeManager, TradeManagerConfig
from gold_bot.universe import Universe


class TestLesEndormisSontResumes:

    @staticmethod
    def _scanner():
        # report() ne touche ni au reseau ni au registre : il ne lit que le
        # resultat qu'on lui passe.
        cfg = BotConfig.load("robot.bitvavo.json")
        strategie = Strategy(cfg.strategy, TradeManager(cfg.trade), macro=None)
        return Scanner(None, Universe(), strategie)

    def test_soixante_dix_endormis_tiennent_en_une_ligne(self):
        res = ScanResult()
        for i in range(70):
            res.errors[f"X{i}USD"] = "en sommeil : spread trop large pour l'unite de temps"
        lignes = self._scanner().report(res)
        sommeil = [l for l in lignes if "en sommeil" in l]
        assert len(sommeil) == 1, (
            f"{len(sommeil)} lignes de sommeil : le journal reproduit le "
            "bruit du scan a chaque cycle")
        assert "70" in sommeil[0], sommeil

    def test_le_motif_du_sommeil_reste_lisible(self):
        """Resumer n'est pas taire : le motif doit survivre au comptage."""
        res = ScanResult()
        res.errors["AAAUSD"] = "en sommeil : spread trop large pour l'unite de temps"
        res.errors["BBBUSD"] = "en sommeil : donnees indisponibles"
        lignes = " | ".join(self._scanner().report(res))
        assert "spread trop large" in lignes
        assert "donnees indisponibles" in lignes

    def test_les_autres_refus_restent_nominatifs(self):
        """Un refus qui n'est pas un sommeil designe encore son instrument.

        C'est l'envers du test precedent : agreger tout rendrait le
        diagnostic impossible.
        """
        res = ScanResult()
        res.errors["SOLUSD"] = "exposition deja prise"
        lignes = self._scanner().report(res)
        assert any("SOLUSD" in l and "exposition" in l for l in lignes), lignes


class TestLeMotifDeVolatiliteNommeSonCritere:
    """Percentile et ratio ATR/prix ne se lisent pas sur la meme echelle.

    Un percentile est relatif a l'histoire de l'instrument, un ratio
    ATR/prix est absolu. Afficher les deux valeurs sans dire laquelle
    refuse laisse chercher du mauvais cote — c'est ce qui s'est passe le
    30 aout, ou le plancher absolu mordait pendant que le journal mettait
    le percentile en avant.
    """

    @staticmethod
    def _refus(plancher_absolu=0.0, percentile_min=0.0, percentile_max=1.0):
        import time
        from gold_bot.core import Tick
        from helpers import pullback_setup_indicators

        cfg = StrategyConfig()
        cfg.min_atr_price_ratio = plancher_absolu
        cfg.min_atr_percentile = percentile_min
        cfg.max_atr_percentile = percentile_max
        strategie = Strategy(cfg, TradeManager(TradeManagerConfig()), macro=None)

        ind = pullback_setup_indicators(1)
        inds = {"M1": ind, "M5": ind, "M15": ind, "H1": ind}
        prix = ind.last.close
        maintenant = time.mktime(time.strptime("2026-08-25 14:00:00",
                                               "%Y-%m-%d %H:%M:%S"))
        ev = strategie.evaluate(Universe().get("XAUUSD"), inds,
                                Tick(maintenant, prix - 0.15, prix + 0.15),
                                now=maintenant)
        gate = next((g for g in ev.gates if g.name == "volatilite"), None)
        assert gate is not None and not gate.passed, (
            "le filtre de volatilite n'a pas refuse : le test ne mesure rien")
        return gate.detail

    def test_le_plancher_absolu_est_nomme_et_explique(self):
        """Le cas du 30 aout : sept cryptos sous 0,75 % d'ATR."""
        motif = self._refus(plancher_absolu=0.99)
        assert "marche trop calme" in motif, motif
        assert "plafond de cout" in motif, (
            "le motif doit dire POURQUOI un marche calme est refuse — sinon "
            f"il ressemble a un reglage trop strict : {motif}")

    def test_le_percentile_bas_est_distingue_du_plancher(self):
        motif = self._refus(percentile_min=0.99)
        assert "historique" in motif, motif
        assert "marche trop calme" not in motif, (
            f"les deux criteres sont confondus : {motif}")

    def test_la_volatilite_extreme_est_distinguee_des_deux(self):
        motif = self._refus(percentile_max=0.0)
        assert "extreme" in motif, motif


class TestLePlancherDeVolatiliteEstLaBorneDeCout:
    """Le 0,75 % en service n'est pas un chiffre choisi : il se calcule.

    Le stop vaut atr_stop_mult x ATR, donc 1 R. Des frais de f % du prix
    pesent f / (atr_stop_mult x ATR) en R. Exiger que ce poids reste sous
    max_cost_ratio_pct revient a exiger un ATR minimal — et c'est
    exactement le reglage livre. S'ils divergent, le robot evalue en
    boucle des trades que le dimensionnement refusera.
    """

    def test_le_reglage_livre_egale_la_borne_calculee(self):
        cfg = BotConfig.load("robot.bitvavo.json")
        borne = cfg.atr_minimal_utile()
        assert borne > 0
        assert abs(cfg.strategy.min_atr_price_ratio - borne) < 1e-6, (
            f"plancher livre {cfg.strategy.min_atr_price_ratio:.5f} contre "
            f"borne calculee {borne:.5f} : sous le plancher le robot "
            "evaluerait des trades que le plafond de cout refuse ensuite")


class TestUneTraceDActiviteNEstPasUneAlerte:
    """« AUCUNE RECHERCHE » doit designer une panne, pas un cycle normal.

    Le 30 aout, onze lignes WARNING « delai minimal entre deux trades non
    ecoule » ont fait croire a un robot bloque toute la journee. Elles
    prouvaient l'inverse : `last_trade_ts` vaut `trade.closed_at`, donc
    chacune marque une CLOTURE de trade moins de trente secondes plus
    tot. Onze de ces lignes, c'est onze trades fermes.

    Une alerte qui se declenche sur le fonctionnement normal ne protege
    plus de rien : on apprend a l'ignorer, et le jour ou le drawdown
    arrive on l'ignore aussi.
    """

    def test_le_delai_entre_trades_est_routinier(self):
        from gold_bot.risk import DELAI_NON_ECOULE, refus_routinier
        assert refus_routinier(DELAI_NON_ECOULE)

    def test_les_places_occupees_sont_routinieres(self):
        from gold_bot.risk import PLACES_OCCUPEES, refus_routinier
        assert refus_routinier(f"{PLACES_OCCUPEES} (6)")

    def test_un_coupe_circuit_reste_une_alerte(self):
        """L'envers, et il compte davantage : ces refus-la exigent qu'on
        intervienne, ils ne se resolvent pas seuls."""
        from gold_bot.risk import refus_routinier
        for motif in ("robot arrete : drawdown maximal atteint (48.2%)",
                      "limite de perte journaliere atteinte (-4.10%)",
                      "limite de perte hebdomadaire atteinte (-8.30%)",
                      "pause apres pertes (45 min restantes)",
                      "capital inconnu ou nul"):
            assert not refus_routinier(motif), motif

    def test_les_motifs_produits_par_can_trade_sont_reconnus(self):
        """Le piege : une constante renommee d'un cote seulement.

        Si le texte de can_trade cesse de correspondre a la constante, le
        refus redevient une alerte en silence — et personne ne s'en rend
        compte avant de revoir onze WARNING dans le journal.
        """
        import time
        from gold_bot.core import Position, Side
        from gold_bot.risk import RiskConfig, RiskManager, refus_routinier

        rm = RiskManager(RiskConfig(min_seconds_between_trades=60.0, max_positions=1))
        rm.sync_account(1000.0, 1000.0, "EUR")
        rm.account.last_trade_ts = time.time()
        ok, why = rm.can_trade([])
        assert not ok and refus_routinier(why), why

        rm2 = RiskManager(RiskConfig(min_seconds_between_trades=0.0, max_positions=1))
        rm2.sync_account(1000.0, 1000.0, "EUR")
        pos = Position(id="p1", symbol="SOLUSD", side=Side.BUY, volume=1.0,
                       entry_price=100.0, stop_loss=98.0, take_profit=104.0,
                       opened_at=time.time(), initial_risk=2.0)
        ok, why = rm2.can_trade([pos])
        assert not ok and refus_routinier(why), why
