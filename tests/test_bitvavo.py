"""Execution sur Bitvavo.

L'API de Bitvavo n'est pas joignable depuis l'environnement de
developpement : ces tests sont donc la seule verification possible avant le
premier ordre reel. Ils portent sur ce qui casse silencieusement quand on
se trompe — la signature, les arrondis, et la devise de cotation.

Le point le plus dangereux est le dernier. Bitvavo cote en EUR, toutes les
autres sources en USD. Une bascule silencieuse de l'une vers l'autre ferait
calculer des stops 8 % a cote du marche ou les ordres partent : le trade
serait faux, pas approximatif.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.brokers.base import BrokerError
from gold_bot.brokers.bitvavo import (ACTIFS, BitvavoBroker, BitvavoConfig,
                                      RegleMarche, formater, marche)
from gold_bot.core import Side
from gold_bot.datasources import PROVIDER_CLASSES, DataRegistry
from gold_bot.datasources.providers import (BinanceProvider, BitvavoProvider,
                                            YahooProvider)
from gold_bot.universe import CATALOGUE_CRYPTO, instrument_crypto


def broker_de_test(**kw) -> BitvavoBroker:
    cfg = BitvavoConfig(api_key="cle", api_secret="secret", quote_asset="EUR",
                        dry_run=kw.pop("dry_run", True), **kw)
    return BitvavoBroker(cfg)


# ==========================================================================
class TestSignature:
    """La signature doit reproduire exactement l'algorithme officiel.

    Reference : createSignature() du client Python publie par Bitvavo.
    Un espace de difference dans la serialisation du corps et la plateforme
    rejette l'ordre.
    """

    @staticmethod
    def reference(horodatage, methode, chemin, corps, secret):
        message = str(horodatage) + methode + "/v2" + chemin
        if corps is not None and len(corps.keys()) > 0:
            message += json.dumps(corps, separators=(",", ":"))
        return hmac.new(secret.encode("utf-8"), message.encode("utf-8"),
                        hashlib.sha256).hexdigest()

    def test_get_sans_corps(self):
        b = broker_de_test()
        assert b._signer(1700000000000, "GET", "/balance", None) == \
            self.reference(1700000000000, "GET", "/balance", None, "secret")

    def test_get_avec_parametres(self):
        """Les parametres font partie du chemin signe, pas du corps."""
        b = broker_de_test()
        chemin = "/order?market=BTC-EUR&orderId=abc"
        assert b._signer(1700000000000, "GET", chemin, None) == \
            self.reference(1700000000000, "GET", chemin, None, "secret")

    def test_post_avec_corps(self):
        b = broker_de_test()
        corps = {"market": "BTC-EUR", "side": "buy", "orderType": "market",
                 "amount": "0.001"}
        assert b._signer(1700000000000, "POST", "/order", corps) == \
            self.reference(1700000000000, "POST", "/order", corps, "secret")

    def test_corps_vide_ignore(self):
        """Un corps vide ne doit rien ajouter au message signe."""
        b = broker_de_test()
        assert b._signer(1, "GET", "/account", {}) == b._signer(1, "GET", "/account", None)

    def test_ordre_des_cles_preserve(self):
        """Le corps est signe tel qu'il sera envoye, pas reordonne."""
        b = broker_de_test()
        a = b._signer(1, "POST", "/order", {"market": "BTC-EUR", "side": "buy"})
        c = b._signer(1, "POST", "/order", {"side": "buy", "market": "BTC-EUR"})
        assert a != c, "l'ordre des cles change la chaine signee : elle doit etre figee"


# ==========================================================================
class TestCorrespondanceDesMarches:
    def test_format_bitvavo(self):
        assert marche("BTCUSD", "EUR") == "BTC-EUR"

    def test_or_absent_du_catalogue_crypto(self):
        """Bitvavo ne cote pas l'or : le symbole doit etre rejete, pas devine."""
        assert marche("XAUUSD", "EUR") is None

    def test_catalogue_aligne_sur_l_univers(self):
        """Une seconde liste tenue a la main divergerait au premier ajout."""
        assert set(ACTIFS.values()) == set(CATALOGUE_CRYPTO)

    def test_source_et_execution_alignees(self):
        """Lire les prix sur un catalogue plus etroit ferait des trous muets."""
        assert set(BitvavoProvider.ACTIFS) == set(ACTIFS)


# ==========================================================================
class TestArrondis:
    """`pricePrecision` compte les chiffres SIGNIFICATIFS chez Bitvavo.

    Le confondre avec un nombre de decimales casse un bout du catalogue ou
    l'autre : soit le BTC a cinq decimales inutiles, soit le PEPE arrondi a
    zero.
    """

    def test_prix_haut_arrondi_a_l_unite(self):
        r = RegleMarche("BTC-EUR", price_precision=5)
        assert r.arrondir_prix(61234.678) == pytest.approx(61235.0)

    def test_prix_bas_garde_ses_chiffres_utiles(self):
        r = RegleMarche("PEPE-EUR", price_precision=5)
        arrondi = r.arrondir_prix(0.0000123456)
        assert arrondi == pytest.approx(0.000012346, rel=1e-9)
        assert arrondi > 0, "un arrondi decimal naif ecraserait ce prix a zero"

    def test_quantite_arrondie_vers_le_bas(self):
        """Vers le bas toujours : arrondir a la hausse depasserait le risque."""
        r = RegleMarche("BTC-EUR", amount_decimals=8)
        assert r.arrondir_quantite(0.123456789) == pytest.approx(0.12345678)

    def test_quantite_negative_ou_nulle(self):
        r = RegleMarche("BTC-EUR", amount_decimals=8)
        assert r.arrondir_quantite(0.0) == 0.0
        assert r.arrondir_quantite(-1.0) == 0.0


class TestFormatage:
    def test_pas_de_notation_scientifique(self):
        """`str(1e-05)` donne « 1e-05 », que Bitvavo refuse."""
        assert "e" not in formater(0.00001).lower()
        assert formater(0.00001) == "0.00001"

    def test_zeros_inutiles_retires(self):
        assert formater(1.5000) == "1.5"
        assert formater(2.0) == "2"

    def test_zero(self):
        assert formater(0.0) == "0"


# ==========================================================================
class TestGardeFousALOuverture:
    def test_vente_a_decouvert_refusee(self):
        b = broker_de_test()
        inst = instrument_crypto("BTC", "crypto_major")
        with pytest.raises(BrokerError, match="achat"):
            b.open_position(inst, Side.SELL, 0.001, 50000.0, 70000.0)

    def test_ouverture_sans_stop_refusee(self):
        """Une position sans protection est inacceptable, meme en simulation."""
        b = broker_de_test()
        inst = instrument_crypto("BTC", "crypto_major")
        with pytest.raises(BrokerError, match="stop-loss"):
            b.open_position(inst, Side.BUY, 0.001, 0.0, 70000.0)

    def test_notionnel_sous_le_minimum_refuse(self):
        b = broker_de_test()
        b._regles["BTC-EUR"] = RegleMarche("BTC-EUR", min_notional=5.0)
        b._prix = lambda code: 60000.0
        inst = instrument_crypto("BTC", "crypto_major")
        with pytest.raises(BrokerError, match="notionnel"):
            b.open_position(inst, Side.BUY, 0.00001, 58000.0, 64000.0)

    def test_marge_pour_les_frais(self):
        """Un ordre calibre au centime pres serait refuse par la plateforme.

        Les frais se prelevent EN PLUS du notionnel : engager 100 % du solde
        disponible echoue pour quelques centimes de commission.
        """
        b = broker_de_test()
        b._regles["BTC-EUR"] = RegleMarche("BTC-EUR", min_notional=5.0)
        b._prix = lambda code: 60000.0
        b._account.margin_free = 60.0
        inst = instrument_crypto("BTC", "crypto_major")
        with pytest.raises(BrokerError, match="disponible"):
            b.open_position(inst, Side.BUY, 0.001, 58000.0, 64000.0)


# ==========================================================================
class TestDisponibiliteDesSymboles:
    def test_avant_chargement_on_ne_prejuge_pas(self):
        """Filtrer avant de connaitre les marches viderait tout l'univers."""
        b = broker_de_test()
        assert b.supports("BTCUSD") is True

    def test_apres_chargement_les_marches_font_foi(self):
        b = broker_de_test()
        b._regles["BTC-EUR"] = RegleMarche("BTC-EUR")
        assert b.supports("BTCUSD") is True
        assert b.supports("PEPEUSD") is False

    def test_symbole_hors_catalogue(self):
        b = broker_de_test()
        assert b.supports("XAUUSD") is False


# ==========================================================================
class TestDeviseDeCotation:
    """Le garde-fou le plus important de ce connecteur.

    Bitvavo cote en euros, Binance et Yahoo en dollars. Les melanger pour un
    meme instrument ferait calculer les niveaux sur une echelle de prix
    differente de celle ou les ordres partent.
    """

    def test_registre_en_euros_ecarte_les_sources_en_dollars(self):
        r = DataRegistry(providers=[BitvavoProvider(), BinanceProvider(), YahooProvider()],
                         devise_crypto="EUR")
        noms = [p.name for p in r.usable("crypto")]
        assert "bitvavo" in noms
        assert "binance" not in noms
        assert "yahoo" not in noms

    def test_sans_contrainte_toutes_les_sources_restent(self):
        r = DataRegistry(providers=[BitvavoProvider(), BinanceProvider()], devise_crypto="")
        assert len(r.usable("crypto")) == 2

    def test_dollars_equivalents_entre_eux(self):
        """USDT, USDC et USD valent un dollar a moins d'un pour cent pres."""
        r = DataRegistry(providers=[BinanceProvider()], devise_crypto="USDC")
        assert [p.name for p in r.usable("crypto")] == ["binance"]

    def test_l_euro_n_est_pas_un_dollar(self):
        r = DataRegistry(providers=[BinanceProvider()], devise_crypto="EUR")
        assert r.usable("crypto") == []

    def test_la_contrainte_ne_touche_pas_les_autres_classes(self):
        """L'or et le forex ne sont pas concernes : ils gardent leurs sources."""
        r = DataRegistry(providers=[YahooProvider()], devise_crypto="EUR")
        assert [p.name for p in r.usable("metal")] == ["yahoo"]

    def test_bitvavo_prioritaire_dans_le_registre_par_defaut(self):
        """La source du lieu d'execution doit passer avant les autres."""
        noms = [c.__name__ for c in PROVIDER_CLASSES]
        assert noms.index("BitvavoProvider") < noms.index("BinanceProvider")


# ==========================================================================
class TestLectureDesErreurs:
    def test_code_et_message_extraits(self):
        code, message = BitvavoBroker._lire_erreur(
            '{"errorCode":203,"error":"symbol parameter is required"}')
        assert code == 203
        assert "symbol" in message

    def test_reponse_illisible_ne_casse_pas(self):
        code, message = BitvavoBroker._lire_erreur("<html>502</html>")
        assert code == 0
        assert message

    def test_instant_de_levee_du_bannissement(self):
        instant = BitvavoBroker._instant_de_levee(
            "Rate limit reached, ban lifted at 1700000000000.")
        assert instant == pytest.approx(1700000000.0)

    def test_message_sans_horodatage_retombe_sur_une_attente(self):
        """Faute de date lisible, mieux vaut attendre que marteler l'API."""
        import time
        instant = BitvavoBroker._instant_de_levee("Rate limit reached.")
        assert instant > time.time()


# ==========================================================================
class TestQuota:
    def test_quota_confortable_ne_bloque_pas(self):
        b = broker_de_test()
        b._quota_restant = 500
        b._attendre_le_quota()          # ne doit pas dormir

    def test_quota_epuise_mais_deja_expire(self):
        import time
        b = broker_de_test()
        b._quota_restant = 0
        b._quota_reset = time.time() - 10
        b._attendre_le_quota()
        assert b._quota_restant == 1000

    def test_entetes_de_quota_lues(self):
        b = broker_de_test()
        b._noter_le_quota({"Bitvavo-Ratelimit-Remaining": "42",
                           "Bitvavo-Ratelimit-ResetAt": "1700000000000"})
        assert b._quota_restant == 42
        assert b._quota_reset == pytest.approx(1700000000.0)

    def test_entetes_illisibles_ignorees(self):
        b = broker_de_test()
        b._quota_restant = 900
        b._noter_le_quota({"bitvavo-ratelimit-remaining": "n/a"})
        assert b._quota_restant == 900


# ==========================================================================
class TestBougies:
    def test_ordre_chronologique_retabli(self, monkeypatch):
        """Bitvavo renvoie la bougie la plus RECENTE en premier.

        Tout le robot raisonne dans l'ordre chronologique : oublier ce
        renversement inverserait chaque tendance lue.
        """
        recu = [
            [1700000120000, "3", "3", "3", "3", "1"],
            [1700000060000, "2", "2", "2", "2", "1"],
            [1700000000000, "1", "1", "1", "1", "1"],
        ]
        monkeypatch.setattr("gold_bot.datasources.providers.http_get",
                            lambda *a, **k: recu)
        p = BitvavoProvider()
        monkeypatch.setattr(p, "throttle", lambda: None)
        bougies = p.fetch_candles("BTCUSD", "crypto", "M1", 3)
        assert [c.close for c in bougies] == [1.0, 2.0, 3.0]
        assert bougies[0].ts < bougies[-1].ts

    def test_symbole_inconnu_n_est_pas_une_panne(self, monkeypatch):
        """Un 400 sur une paire absente ne doit pas couper la source.

        La confondre avec une panne mettrait Bitvavo en quarantaine pour
        tous les autres marches.
        """
        from gold_bot.datasources.base import ProviderError, SymbolNotSupported

        def refuse(*a, **k):
            exc = ProviderError("400")
            exc.status = 400
            raise exc

        monkeypatch.setattr("gold_bot.datasources.providers.http_get", refuse)
        p = BitvavoProvider()
        monkeypatch.setattr(p, "throttle", lambda: None)
        with pytest.raises(SymbolNotSupported):
            p.fetch_candles("BTCUSD", "crypto", "H1", 100)

    def test_m3_reconstruit_depuis_la_minute(self, monkeypatch):
        """Bitvavo n'expose pas M3 : il doit etre agrege, pas refuse.

        L'horodatage de depart est aligne sur une frontiere de trois
        minutes : `resample` decoupe sur des frontieres absolues, donc des
        bougies non alignees produisent legitimement un seau partiel a
        chaque extremite. Ce n'est pas ce qu'on teste ici.
        """
        debut = 1700000100000              # divisible par 180 s
        recu = [[debut + i * 60000, "1", "2", "0.5", "1.5", "1"]
                for i in range(9)][::-1]
        monkeypatch.setattr("gold_bot.datasources.providers.http_get",
                            lambda *a, **k: recu)
        p = BitvavoProvider()
        monkeypatch.setattr(p, "throttle", lambda: None)
        bougies = p.fetch_candles("BTCUSD", "crypto", "M3", 3)
        assert len(bougies) == 3, "neuf bougies M1 alignees font trois bougies M3"
        assert bougies[0].volume == pytest.approx(3.0), "les volumes doivent s'additionner"

    def test_unite_de_temps_inconnue_refusee(self):
        p = BitvavoProvider()
        from gold_bot.datasources.base import ProviderError
        with pytest.raises(ProviderError, match="unite de temps"):
            p.fetch_candles("BTCUSD", "crypto", "M7", 10)


# ==========================================================================
class TestFraisEtEchelleDeTemps:
    """L'arithmetique qui a fait passer la configuration de H1 a H4."""

    def test_le_h1_de_binance_ne_tient_plus_sur_bitvavo(self):
        aller_retour_bitvavo = 2 * 0.0025
        stop_h1 = 0.0154
        assert aller_retour_bitvavo / stop_h1 > 0.15, (
            "a 0,50 % d'aller-retour, un stop H1 laisse les frais depasser "
            "15 % du risque : c'est pourquoi la configuration passe en H4")

    def test_le_h4_elargi_tient(self):
        aller_retour_bitvavo = 2 * 0.0025
        stop_h4 = 0.036
        assert aller_retour_bitvavo / stop_h4 <= 0.15

    def test_configuration_livree_coherente(self):
        """La commission declaree doit etre celle de Bitvavo, pas de Binance."""
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.engine.broker == "bitvavo"
        assert cfg.engine.currency == "EUR"
        assert cfg.risk.commission_pct == pytest.approx(0.0025)
        assert cfg.strategy.entry_tf == "H4"
        assert cfg.validate() == []

    def test_configuration_livree_en_simulation(self):
        """On ne livre jamais une configuration armee en reel par defaut."""
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.engine.dry_run is True

    def test_plafond_journalier_illimite(self):
        """Demande explicite : le robot ne doit pas se brider."""
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.risk.max_daily_trades == 0
