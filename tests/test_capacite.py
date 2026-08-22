"""Capacite du compte et etendue de l'univers.

Ces deux points, et non les filtres de strategie, expliquaient qu'un compte
de 59 USDC ne prenne qu'un trade par jour :
  - `capital_tier` forcait une seule position sous 100 de capital ;
  - l'univers ne contenait que quatre cryptos, toutes dans le meme groupe de
    correlation, ce qui interdisait d'en tenir deux a la fois.
"""
from __future__ import annotations

import math

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.brokers.binance import ACTIFS, paire
from gold_bot.engine import positions_tenables
from gold_bot.universe import (CATALOGUE_CRYPTO, DEFAULT_UNIVERSE, Instrument,
                               Universe, instrument_crypto)


class TestCapaciteDuCompte:
    def test_petit_compte_tient_plusieurs_positions(self):
        """Regression : 59,53 USDC etait bride a une seule position."""
        positions, palier = positions_tenables(59.53, 5.0, 80.0, 6)
        assert positions > 1, "un compte de 59 USDC peut tenir plusieurs tickets de 5"
        assert positions == 6
        assert palier == "moyen"

    def test_capacite_suit_le_ticket_minimum(self):
        """A capital egal, un ticket plus cher permet moins de lignes."""
        petit, _ = positions_tenables(100.0, 5.0, 80.0, 10)
        gros, _ = positions_tenables(100.0, 20.0, 80.0, 10)
        assert petit > gros

    def test_capital_insuffisant_reste_a_une_position(self):
        positions, palier = positions_tenables(5.0, 5.0, 80.0, 6)
        assert positions == 1
        assert palier == "insuffisant"

    def test_plafond_de_configuration_respecte(self):
        """Un gros capital ne depasse jamais max_positions."""
        positions, _ = positions_tenables(1_000_000.0, 5.0, 80.0, 4)
        assert positions == 4

    def test_coussin_de_liquidites_conserve(self):
        """On n'engage jamais 100 % du capital."""
        engage_tout, _ = positions_tenables(100.0, 5.0, 100.0, 50)
        engage_partiel, _ = positions_tenables(100.0, 5.0, 80.0, 50)
        assert engage_partiel < engage_tout
        assert engage_partiel == 16   # 80 / 5

    def test_valeurs_degenerees(self):
        assert positions_tenables(0.0, 5.0, 80.0, 6)[0] == 1
        assert positions_tenables(100.0, 0.0, 80.0, 6)[0] == 1
        assert positions_tenables(100.0, 5.0, 80.0, 0)[0] == 0


class TestEtendueUnivers:
    def test_catalogue_large(self):
        """L'univers doit couvrir les cryptos principales, pas quatre paires."""
        cryptos = [i for i in Universe() if i.asset_class == "crypto"]
        assert len(cryptos) >= 50, f"seulement {len(cryptos)} cryptos"

    def test_chaque_actif_a_un_instrument(self):
        symboles = {i.symbol for i in Universe()}
        for actif in CATALOGUE_CRYPTO:
            assert f"{actif}USD" in symboles

    def test_groupes_de_correlation_varies(self):
        """Plusieurs groupes : sinon une seule position crypto a la fois."""
        groupes = {i.correlation_group for i in Universe() if i.asset_class == "crypto"}
        assert len(groupes) >= 5, f"groupes trouves : {groupes}"

    def test_les_majeures_ne_sont_plus_dans_un_groupe_fourre_tout(self):
        """Regression : BTC, ETH, SOL et XRP partageaient le groupe 'crypto'."""
        u = Universe()
        groupes = {s: u.get(s).correlation_group
                   for s in ("BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD")}
        assert len(set(groupes.values())) > 1, groupes
        assert "crypto" not in groupes.values()

    def test_pas_de_doublon(self):
        symboles = [i.symbol for i in DEFAULT_UNIVERSE]
        assert len(symboles) == len(set(symboles))

    def test_les_reglages_manuels_sont_preserves(self):
        """La generation automatique ne doit pas ecraser les paires reglees."""
        btc = Universe().get("BTCUSD")
        assert btc.digits == 2
        assert btc.min_lot == 0.001
        assert math.isfinite(btc.max_spread)

    def test_traduction_en_code_binance(self):
        assert paire("PEPEUSD", "USDC") == "PEPEUSDC"
        assert paire("BTCUSD", "USDT") == "BTCUSDT"
        assert paire("INCONNUUSD", "USDC") is None

    def test_actifs_et_catalogue_coherents(self):
        assert len(ACTIFS) == len(CATALOGUE_CRYPTO)


class TestInstrumentGenere:
    def test_valeurs_par_defaut_permissives(self):
        """Le broker corrige les lots au demarrage : ne rien bloquer ici."""
        inst = instrument_crypto("PEPE", "crypto_meme")
        assert inst.symbol == "PEPEUSD"
        assert inst.correlation_group == "crypto_meme"
        assert inst.weekend is True
        assert inst.min_lot > 0
        assert inst.max_lot > inst.min_lot

    def test_plafond_de_spread_absolu_desactive(self):
        """Un seuil absolu n'a pas de sens du BTC a 77000 au PEPE a 0,00001.

        Le controle qui compte est relatif a l'ATR, donc valable a toutes les
        echelles de prix.
        """
        inst = instrument_crypto("PEPE", "crypto_meme")
        assert inst.max_spread == math.inf

    def test_niveaux_ronds_desactives(self):
        """Sans echelle de prix de reference, les chiffres ronds n'ont pas de sens."""
        from gold_bot.chart import round_numbers
        inst = instrument_crypto("BONK", "crypto_meme")
        assert inst.round_step == 0.0
        assert round_numbers(0.000012, inst.round_step) == []

    def test_normalisation_du_lot_fonctionne(self):
        inst = instrument_crypto("SUI", "crypto_l1")
        inst.min_lot, inst.lot_step = 0.1, 0.1     # ce que ferait Binance
        assert inst.normalize_lot(0.35, round_down=True) == 0.3


class TestScanParallele:
    """Le scan doit tenir un univers large dans un cycle court.

    Sequentiellement, 85 instruments a ~0,5 s de reseau chacun demandent plus
    de 40 secondes : le robot passerait son temps en retard sur lui-meme.
    """

    def _scanner(self, nb_instruments: int, max_workers: int, latence: float):
        import time as _time
        from gold_bot.scanner import Scanner
        from gold_bot.universe import Universe, instrument_crypto

        instruments = [instrument_crypto(f"TEST{i}", "crypto_l1")
                       for i in range(nb_instruments)]
        scanner = Scanner(registry=None, universe=Universe(instruments),
                          strategy=None, max_workers=max_workers)

        appels = []

        def fausse_evaluation(instrument, score_bonus=0.0, now=None):
            appels.append(instrument.symbol)
            _time.sleep(latence)          # simule l'attente reseau
            raise RuntimeError("evaluation neutralisee")

        scanner.evaluate_symbol = fausse_evaluation
        return scanner, appels

    def test_tous_les_instruments_sont_evalues(self):
        scanner, appels = self._scanner(20, max_workers=8, latence=0.0)
        result = scanner.scan()
        assert result.scanned == 20
        assert len(appels) == 20
        assert len(result.errors) == 20   # toutes neutralisees, aucune ne casse le cycle

    def test_un_instrument_en_erreur_ne_casse_pas_le_cycle(self):
        scanner, _ = self._scanner(5, max_workers=4, latence=0.0)
        result = scanner.scan()
        assert result.best is None
        assert all("erreur interne" in m for m in result.errors.values())

    def test_le_parallelisme_accelere_reellement(self):
        import time as _time

        sequentiel, _ = self._scanner(12, max_workers=1, latence=0.02)
        debut = _time.perf_counter()
        sequentiel.scan()
        duree_sequentielle = _time.perf_counter() - debut

        parallele, _ = self._scanner(12, max_workers=6, latence=0.02)
        debut = _time.perf_counter()
        parallele.scan()
        duree_parallele = _time.perf_counter() - debut

        assert duree_parallele < duree_sequentielle / 2, (
            f"sequentiel {duree_sequentielle:.3f}s, parallele {duree_parallele:.3f}s")

    def test_contextes_crees_sans_doublon(self):
        """Deux fils ne doivent pas creer deux contextes pour le meme symbole."""
        scanner, _ = self._scanner(30, max_workers=8, latence=0.0)
        scanner.scan()
        assert len(scanner.contexts) == 30
        assert len(set(scanner.contexts)) == 30

    def test_un_seul_instrument_reste_sequentiel(self):
        scanner, appels = self._scanner(1, max_workers=8, latence=0.0)
        scanner.scan()
        assert len(appels) == 1
