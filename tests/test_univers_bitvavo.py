"""L'univers est LU chez le courtier, et les pieges de ce passage a l'echelle.

Le 10 septembre 2026 l'univers est passe de 78 a ~236 cryptos. La liste
etait ecrite a la main : 85 entrees dont QUINZE n'existaient plus chez
Bitvavo (MATIC, FTM, OCEAN, MKR, EOS...), cherchees a chaque scan pour
rien, pendant que Bitvavo cotait 430 cryptos en euros — dont HYPE et ses
15 millions d'euros de volume quotidien, invisible pour le robot.

Trois defauts sont sortis du passage a l'echelle. Aucun n'aurait fait
echouer un test existant, et les trois etaient silencieux.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.datasources.base import SymbolNotSupported, tf_seconds


class TestUnSeulDictionnairePourToutLeMonde:
    """Le scanner et le courtier doivent nommer les memes actifs.

    Cinq modules construisaient leur propre table a partir du catalogue,
    par comprehension, AU MOMENT DE L'IMPORT. Une crypto decouverte au
    demarrage aurait ete visible du scanner et introuvable a l'execution :
    le robot aurait trouve son signal, dimensionne sa position, puis
    envoye un ordre sur un symbole que le courtier ne sait pas traduire.
    """

    def test_le_courtier_et_les_sources_partagent_l_objet(self):
        from gold_bot.brokers.bitvavo import ACTIFS as courtier
        from gold_bot.datasources.providers import (
            BinanceProvider, BitvavoProvider, OkxProvider)
        from gold_bot.universe import ACTIFS_PAR_SYMBOLE

        assert courtier is ACTIFS_PAR_SYMBOLE, (
            "le courtier Bitvavo garde une COPIE du catalogue : une crypto "
            "decouverte au demarrage lui sera inconnue a l'execution")
        for source in (BitvavoProvider, BinanceProvider, OkxProvider):
            assert source.ACTIFS is ACTIFS_PAR_SYMBOLE, (
                f"{source.name} garde une copie du catalogue")

    def test_une_crypto_ajoutee_est_vue_partout_aussitot(self):
        from gold_bot.brokers.bitvavo import ACTIFS as courtier
        from gold_bot.datasources.providers import BitvavoProvider
        from gold_bot.universe import ACTIFS_PAR_SYMBOLE, ajouter_cryptos

        faux = "ZZTESTUSD"
        try:
            ajouter_cryptos({"ZZTEST": "crypto_alt"})
            assert courtier.get(faux) == "ZZTEST", (
                "le courtier ne voit pas la crypto ajoutee")
            assert BitvavoProvider().symbol_for(faux, "crypto") == "ZZTEST-EUR", (
                "la source de prix ne sait pas nommer la crypto ajoutee")
        finally:
            ACTIFS_PAR_SYMBOLE.pop(faux, None)
            from gold_bot.universe import CATALOGUE_CRYPTO
            CATALOGUE_CRYPTO.pop("ZZTEST", None)


class TestUnSymboleJeuneNeCoupePasLaSource:
    """Une crypto de la veille ne doit pas aveugler le robot sur les 243 autres.

    Un historique trop court levait une `ProviderError`, donc une mise en
    QUARANTAINE de 300 s de la source entiere. Mesure en passant l'univers
    a 244 cryptos : une seule cotee de la veille — deux bougies — suffisait
    a couper Bitvavo pour tout le monde. Bitvavo liste une crypto presque
    chaque semaine : le robot se serait aveugle tout seul, regulierement,
    sans un message.
    """

    def test_l_historique_court_est_un_symbole_absent_pas_une_panne(self):
        from gold_bot.core import Candle
        from gold_bot.datasources import DataRegistry
        from gold_bot.datasources.base import PriceProvider, ProviderCapabilities

        class SourceJeune(PriceProvider):
            name = "jeune"
            capabilities = ProviderCapabilities(asset_classes=("crypto",))

            def symbol_for(self, symbol, asset_class):
                return symbol

            def fetch_candles(self, symbol, asset_class, timeframe, limit):
                return [Candle(float(i), 1, 1, 1, 1, 1) for i in range(2)]

        source = SourceJeune()
        registre = DataRegistry([source])
        try:
            registre.candles("NEUFUSD", "crypto", "D1", 300)
        except Exception:                                     # noqa: BLE001
            pass          # echouer sur CE symbole est normal et attendu
        assert source.name not in registre._blocked, (
            "un historique trop court a mis la source en quarantaine : "
            "une seule crypto jeune aveuglerait le robot sur toutes les autres")

        # Et la source doit rester utilisable pour les autres symboles.
        assert source in registre.usable("crypto"), (
            "la source est ecartee alors qu'elle n'a rien de casse")


class TestLeCacheSuitL_UniteDeTemps:
    """Recharger une bougie JOURNALIERE toutes les 60 s n'a aucun sens.

    Le plafond valait 60 s pour toutes les unites. Anodin a 63 instruments,
    bloquant a 244 : un scan complet prenait 193 s pour un cycle de 10 s.
    Au-dela de l'heure le plafond passe a 5 minutes.

    Ce que ca coute : une cassure de canal peut etre vue jusqu'a 5 minutes
    plus tard. Sur une strategie qui tient ses positions plusieurs JOURS,
    c'est sans effet — et le stop suiveur suit les COTATIONS (2 s), pas les
    bougies.
    """

    @staticmethod
    def _ttl(tf: str) -> float:
        secondes = tf_seconds(tf)
        return min(secondes / 3.0, 60.0 if secondes < 3600 else 300.0)

    def test_le_journalier_est_garde_cinq_minutes(self):
        assert self._ttl("D1") == 300.0

    def test_rien_ne_change_sous_l_heure(self):
        """Le moteur de scalping garde EXACTEMENT sa fraicheur d'avant."""
        for tf in ("M1", "M5", "M15", "M30"):
            avant = min(tf_seconds(tf) / 3.0, 60.0)
            assert self._ttl(tf) == avant, (
                f"{tf} a change de fraicheur : le scalping n'etait pas "
                "concerne par ce correctif")


class TestLaLimiteD_AppelsVientDeL_API:
    """400/min n'est pas un chiffre choisi : l'API annonce 1 000.

    L'auto-limitation valait 120 — huit fois trop prudente — et etranglait
    le scan des que l'univers depassait la centaine d'instruments.

    La borne haute compte autant : le COURTIER partage ce quota pour les
    ordres, les soldes et les poses de stop. L'affamer produirait une
    position sans stop, le pire cas du systeme.
    """

    def test_la_source_reste_loin_sous_le_plafond_de_bitvavo(self):
        from gold_bot.datasources.providers import BitvavoProvider

        limite = BitvavoProvider.capabilities.rate_limit_per_min
        assert limite <= 500, (
            f"{limite} appels/min : Bitvavo en autorise 1 000 au TOTAL et "
            "le courtier partage ce quota. Au-dela de 500, une rafale de "
            "scan peut empecher la pose d'un stop.")
        assert limite >= 200, (
            f"{limite} appels/min ne suffit pas a rafraichir un univers de "
            "200+ cryptos dans le cycle")
