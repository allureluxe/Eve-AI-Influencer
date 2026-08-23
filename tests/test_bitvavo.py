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
        # L'unite d'entree suit le regime tarifaire en vigueur : M15
        # pendant la fenetre sans commission, D1 apres. Le calibrage
        # rebascule tout seul a l'expiration.
        assert cfg.strategy.entry_tf in ("M15", "H1", "H4", "D1")
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


class TestOperatorId:
    """Bitvavo exige un operatorId sur chaque ordre depuis MiCA.

    Au titre de la tracabilite : chaque ordre doit pouvoir etre rattache a
    l'operateur — humain ou automate — qui l'a emis. Sans lui, la
    plateforme repond « 400 [203] operatorId parameter is required » et
    aucun ordre ne part.
    """

    def test_present_a_l_achat(self, monkeypatch):
        b = broker_de_test(dry_run=False)
        b._regles["BTC-EUR"] = RegleMarche("BTC-EUR", min_notional=5.0)
        b._prix = lambda code: 60000.0
        b._prix_execute = lambda *a: 60000.0
        b._poser_stop = lambda pos: None
        b._account.margin_free = 10000.0
        envoye = {}
        monkeypatch.setattr(b, "_appel",
                            lambda m, c, params=None, corps=None, signe=True:
                            (envoye.update(corps or {}), {"orderId": "1"})[1])
        b.open_position(instrument_crypto("BTC", "crypto_major"),
                        Side.BUY, 0.001, 58000.0, 64000.0)
        assert envoye.get("operatorId") == 1

    def test_present_a_la_vente(self, monkeypatch):
        b = broker_de_test(dry_run=False)
        b._regles["BTC-EUR"] = RegleMarche("BTC-EUR", min_notional=5.0)
        b._prix = lambda code: 60000.0
        b._annuler_stop = lambda s: None
        from gold_bot.core import Position
        b._positions["BTCUSD"] = Position(
            id="BTCUSD", symbol="BTCUSD", side=Side.BUY, volume=0.001,
            entry_price=60000.0, stop_loss=58000.0, take_profit=64000.0,
            opened_at=0.0)
        envoye = {}
        monkeypatch.setattr(b, "_appel",
                            lambda m, c, params=None, corps=None, signe=True:
                            (envoye.update(corps or {}), {"filledAmount": "0.001",
                                                          "filledAmountQuote": "60"})[1])
        b.close_position("BTCUSD", reason="test")
        assert envoye.get("operatorId") == 1

    def test_configurable(self, monkeypatch):
        monkeypatch.setenv("BITVAVO_OPERATOR_ID", "42")
        assert BitvavoConfig.from_env().operator_id == 42

    def test_valeur_par_defaut(self, monkeypatch):
        monkeypatch.delenv("BITVAVO_OPERATOR_ID", raising=False)
        assert BitvavoConfig.from_env().operator_id == 1


class TestPromotionSansFrais:
    """Une fenetre sans commission doit porter sa propre fin.

    Le lendemain de l'expiration, un trade M15 coute 78 % du risque. Un
    robot qui resterait sur la configuration promotionnelle viderait le
    compte sans erreur ni alerte : chaque trade serait perdant d'avance.
    """

    @staticmethod
    def promo():
        from gold_bot.promotion import Promotion
        return Promotion.depuis_config({
            "active": True, "sans_frais_jusqu_au": "2026-08-29",
            "volume_plafond": 9980.0})

    def test_frais_annules_pendant_la_fenetre(self):
        import datetime as d
        p = self.promo()
        assert p.frais_effectifs(0.0025, d.date(2026, 8, 23)) == 0.0

    def test_le_dernier_jour_compte_encore(self):
        import datetime as d
        assert self.promo().en_cours(d.date(2026, 8, 29))

    def test_le_lendemain_le_tarif_normal_revient(self):
        """Le point critique : l'expiration doit etre automatique."""
        import datetime as d
        p = self.promo()
        assert not p.en_cours(d.date(2026, 8, 30))
        assert p.frais_effectifs(0.0025, d.date(2026, 8, 30)) == pytest.approx(0.0025)

    def test_le_volume_epuise_ferme_aussi_la_fenetre(self):
        """Une promotion se termine par la date OU par le volume."""
        import datetime as d
        p = self.promo()
        p.consommer(9980.0)
        assert not p.en_cours(d.date(2026, 8, 23))
        assert p.frais_effectifs(0.0025, d.date(2026, 8, 23)) == pytest.approx(0.0025)

    def test_promotion_inactive_ne_change_rien(self):
        from gold_bot.promotion import Promotion
        p = Promotion.depuis_config({"active": False})
        assert p.frais_effectifs(0.0025) == pytest.approx(0.0025)

    def test_date_illisible_ne_fait_pas_trader_gratuitement(self):
        """Dans le doute, on paie : l'inverse ferait trader a perte."""
        from gold_bot.promotion import Promotion
        p = Promotion.depuis_config({"active": True, "sans_frais_jusqu_au": "n'importe quoi"})
        assert not p.en_cours()
        assert p.frais_effectifs(0.0025) == pytest.approx(0.0025)

    def test_le_moteur_reverifie_a_chaque_cycle(self):
        """Sans cette verification, l'expiration ne serait jamais vue."""
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine)
        assert "self._verifier_promotion()" in source, \
            "la fenetre doit etre reverifiee dans la boucle, pas seulement au demarrage"
        # Et la verification doit recalibrer, pas seulement journaliser.
        methode = inspect.getsource(TradingEngine._verifier_promotion)
        assert "_calibrer_sur_le_capital" in methode

    def test_le_m15_devient_praticable_sans_commission(self):
        from gold_bot.calibrage import calibrer
        sans = calibrer(51.0, 5.0, 0.0000, 0.22, 0.6)
        avec = calibrer(51.0, 5.0, 0.0025, 0.22, 0.6)
        assert "M15" in sans.unites, "sans commission, le M15 doit passer"
        assert "M15" not in avec.unites, "avec commission, il ne doit plus passer"


class TestCommissionDuRisqueAligneeSurLaPromotion:
    """Le calibrage et le gestionnaire de risque doivent voir le meme tarif.

    Defaut mesure en production : la promotion annulait la commission dans
    le calibrage mais pas dans `execution_cost`. Le robot trouvait ses
    signaux — 4, 5, 3 valides par cycle — les validait, puis les rejetait
    TOUS au dimensionnement pour des frais que Bitvavo ne prelevait pas :
    46 % du risque annonce sur ETH, 100 % sur AVAX.

    Un seuil calcule sur un cout imaginaire est un seuil faux, et il
    bloque en silence.
    """

    def test_le_cout_chute_sans_commission(self):
        from gold_bot.risk import RiskConfig, RiskManager
        from gold_bot.universe import Universe, spread_estime
        eth = Universe().get("ETHUSD")
        prix, risque, stop_pct = 2500.0, 0.12, 0.0077
        lots = risque / (prix * stop_pct)

        def ratio(commission):
            rm = RiskManager(RiskConfig(commission_pct=commission,
                                        max_cost_ratio_pct=15.0))
            rm.sync_account(equity=51.0, balance=51.0, currency="EUR")
            return rm.execution_cost(eth, lots, prix,
                                     spread=spread_estime(eth, prix)) / risque

        assert ratio(0.0025) > 0.15, "avec commission, le trade doit etre refuse"
        assert ratio(0.0) <= 0.15, "sans commission, il doit passer"

    def test_le_moteur_aligne_les_deux(self):
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine._calibrer_sur_le_capital)
        assert "commission_pct = frais" in source, (
            "la commission du gestionnaire de risque doit suivre le meme "
            "regime tarifaire que le calibrage")

    def test_le_realignement_survit_a_l_expiration(self):
        """A la fin de la promotion, la commission doit REVENIR."""
        import inspect
        from gold_bot.engine import TradingEngine
        assert "_calibrer_sur_le_capital" in inspect.getsource(
            TradingEngine._verifier_promotion), (
            "l'expiration doit repasser par le calibrage, qui remet la "
            "commission reelle")


class TestDeuxInterrupteurs:
    """`.env` et le fichier de configuration portent chacun un dry_run.

    Le fichier l'emporte — c'est voulu, une configuration livree ne doit
    jamais s'armer toute seule. Mais la contradiction doit etre ANNONCEE :
    en production, un robot cense etre en argent reel ouvrait ses
    positions en simulation, la mention « (dry-run) » noyee dans le
    journal, et rien n'expliquait pourquoi.
    """

    def test_la_contradiction_est_signalee(self):
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine._build_broker)
        assert "SIMULATION IMPOSEE PAR LA CONFIGURATION" in source
        assert "BITVAVO_DRY_RUN" in source, \
            "le message doit nommer les DEUX reglages, pas seulement un"

    def test_le_fichier_reste_prioritaire(self):
        """Une configuration livree ne s'arme jamais toute seule."""
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine._build_broker)
        i = source.index("SIMULATION IMPOSEE")
        assert "bv.dry_run = True" in source[i:], \
            "apres l'avertissement, la simulation doit rester imposee"


# ==========================================================================
class TestRapprochementDesPositions:
    """Une position vendue par son stop n'existe plus, meme si le robot l'ignore.

    Le stop est un ordre reel depose chez Bitvavo : quand il part, l'actif
    est vendu sans que le robot en soit averti. Observe en production le
    23 aout 2026 : ETH vendu par son stop a 15h20, puis « [216] insufficient
    balance » toutes les vingt secondes jusqu'au soir. Le plus grave n'est
    pas la boucle mais ce qu'elle cache : une perte jamais comptabilisee,
    donc invisible pour le plafond de pertes journalieres.
    """

    @staticmethod
    def broker_avec_position(volume=0.0045, entree=2077.5, stop=2050.3):
        from gold_bot.core import Position
        b = broker_de_test(dry_run=False)
        b._regles["ETH-EUR"] = RegleMarche("ETH-EUR", min_amount=0.001,
                                           min_notional=5.0)
        b._positions["ETHUSD"] = Position(
            id="ETHUSD", symbol="ETHUSD", side=Side.BUY, volume=volume,
            entry_price=entree, stop_loss=stop, take_profit=2132.9,
            opened_at=1000.0)
        b._annuler_stop = lambda s: None
        return b

    def test_position_disparue_du_solde_est_fermee(self):
        b = self.broker_avec_position()
        b._ventes_depuis = lambda code, depuis: (2050.0, 0.0045, 0.02)
        b._soldes = {"EUR": 40.0}          # plus une seule unite d'ETH
        b._reconcilier({"ETH-EUR": 2050.0})
        assert "ETHUSD" not in b._positions

    def test_la_perte_est_comptabilisee(self):
        b = self.broker_avec_position()
        b._ventes_depuis = lambda code, depuis: (2050.0, 0.0045, 0.02)
        b._soldes = {"EUR": 40.0}
        b._reconcilier({"ETH-EUR": 2050.0})
        assert len(b.closed_trades()) == 1
        trade = b.closed_trades()[0]
        assert trade.symbol == "ETHUSD"
        assert trade.profit < 0            # vendu sous le prix d'entree
        assert "plateforme" in trade.reason

    def test_prix_de_sortie_lu_sur_les_executions_reelles(self):
        b = self.broker_avec_position()
        b._ventes_depuis = lambda code, depuis: (2049.0, 0.0045, 0.0)
        b._soldes = {"EUR": 40.0}
        b._reconcilier({"ETH-EUR": 2100.0})   # le marche est remonte depuis
        # C'est le prix reellement obtenu qui compte, pas le dernier cours.
        assert b.closed_trades()[0].exit_price == pytest.approx(2049.0, rel=1e-6)

    def test_sans_historique_le_stop_sert_d_estimation(self):
        b = self.broker_avec_position()
        b._ventes_depuis = lambda code, depuis: (0.0, 0.0, 0.0)
        b._soldes = {"EUR": 40.0}
        b._reconcilier({"ETH-EUR": 2100.0})
        assert b.closed_trades()[0].exit_price == pytest.approx(2050.3, rel=1e-3)

    def test_position_intacte_n_est_pas_touchee(self):
        b = self.broker_avec_position()
        b._soldes = {"ETH": 0.0045, "EUR": 10.0}
        b._reconcilier({"ETH-EUR": 2100.0})
        assert "ETHUSD" in b._positions
        assert b.closed_trades() == []

    def test_les_frais_en_actif_ne_declenchent_pas_de_liquidation(self):
        """0,25 % preleves en ETH ne sont pas une vente."""
        b = self.broker_avec_position()
        b._soldes = {"ETH": 0.0045 * 0.9975, "EUR": 10.0}
        b._reconcilier({"ETH-EUR": 2100.0})
        assert "ETHUSD" in b._positions

    def test_reliquat_invendable_ferme_quand_meme(self):
        """Garder ouverte une poussiere invendable rejouerait la meme boucle."""
        b = self.broker_avec_position()
        b._ventes_depuis = lambda code, depuis: (2050.0, 0.0044, 0.02)
        b._soldes = {"ETH": 0.0001, "EUR": 40.0}   # 0.20 EUR, sous le minimum
        b._reconcilier({"ETH-EUR": 2050.0})
        assert "ETHUSD" not in b._positions

    def test_vente_partielle_reduit_la_position(self):
        b = self.broker_avec_position(volume=0.02)
        b._ventes_depuis = lambda code, depuis: (2050.0, 0.01, 0.05)
        b._soldes = {"ETH": 0.01, "EUR": 40.0}     # 20 EUR : encore vendable
        b._reconcilier({"ETH-EUR": 2050.0})
        assert b._positions["ETHUSD"].volume == pytest.approx(0.01, rel=1e-6)
        assert b.closed_trades()[0].partial is True

    def test_le_mode_simulation_ne_rapproche_rien(self):
        """En simulation les positions n'ont aucun solde en face."""
        b = self.broker_avec_position()
        b.config = BitvavoConfig(api_key="c", api_secret="s", quote_asset="EUR",
                                 dry_run=True)
        b._soldes = {"EUR": 40.0}
        b._reconcilier({"ETH-EUR": 2050.0})
        assert "ETHUSD" in b._positions


class TestVenteRefuseeFauteDeSolde:
    """L'erreur 216 doit solder la position, jamais relancer le meme ordre."""

    @staticmethod
    def broker(monkeypatch, reponse_solde):
        from gold_bot.core import Position
        b = broker_de_test(dry_run=False)
        b._regles["ETH-EUR"] = RegleMarche("ETH-EUR", min_amount=0.001,
                                           min_notional=5.0)
        b._positions["ETHUSD"] = Position(
            id="ETHUSD", symbol="ETHUSD", side=Side.BUY, volume=0.0045,
            entry_price=2077.5, stop_loss=2050.3, take_profit=2132.9,
            opened_at=1000.0)
        b._annuler_stop = lambda s: None
        b._prix = lambda code: 2050.0
        b._prix_du_marche = lambda: {"ETH-EUR": 2050.0}
        b._ventes_depuis = lambda code, depuis: (2050.0, 0.0045, 0.02)
        tentatives = []

        def appel(methode, chemin, params=None, corps=None, signe=True):
            if chemin == "/order" and methode == "POST":
                tentatives.append(corps)
                raise BrokerError("Bitvavo 400 sur POST /order [216] You do "
                                  "not have sufficient balance to complete "
                                  "this operation.")
            if chemin == "/balance":
                return reponse_solde
            return {}

        monkeypatch.setattr(b, "_appel", appel)
        return b, tentatives

    def test_la_position_est_soldee(self, monkeypatch):
        b, _ = self.broker(monkeypatch, [{"symbol": "EUR", "available": "40",
                                          "inOrder": "0"}])
        b.close_position("ETHUSD", reason="objectif atteint")
        assert "ETHUSD" not in b._positions

    def test_le_trade_est_rendu_a_l_appelant(self, monkeypatch):
        """Sans trade rendu, le moteur ne journaliserait rien de la sortie."""
        b, _ = self.broker(monkeypatch, [{"symbol": "EUR", "available": "40",
                                          "inOrder": "0"}])
        trade = b.close_position("ETHUSD", reason="objectif atteint")
        assert trade is not None and trade.position_id == "ETHUSD"

    def test_l_ordre_n_est_pas_rejoue(self, monkeypatch):
        b, tentatives = self.broker(monkeypatch, [{"symbol": "EUR",
                                                   "available": "40",
                                                   "inOrder": "0"}])
        b.close_position("ETHUSD", reason="objectif atteint")
        b.close_position("ETHUSD", reason="objectif atteint")
        assert len(tentatives) == 1     # la seconde n'a plus de position

    def test_une_autre_erreur_remonte_toujours(self, monkeypatch):
        b = broker_de_test(dry_run=False)
        b._regles["ETH-EUR"] = RegleMarche("ETH-EUR")
        from gold_bot.core import Position
        b._positions["ETHUSD"] = Position(
            id="ETHUSD", symbol="ETHUSD", side=Side.BUY, volume=0.0045,
            entry_price=2077.5, stop_loss=2050.3, take_profit=2132.9,
            opened_at=1000.0)
        b._annuler_stop = lambda s: None
        monkeypatch.setattr(b, "_appel", lambda *a, **k: (_ for _ in ()).throw(
            BrokerError("Bitvavo 400 sur POST /order [203] operatorId parameter "
                        "is required")))
        with pytest.raises(BrokerError):
            b.close_position("ETHUSD", reason="test")


class TestLectureDuCodeErreur:
    def test_code_extrait_du_message(self):
        from gold_bot.brokers.bitvavo import code_erreur
        assert code_erreur(BrokerError("Bitvavo 400 sur POST /order [216] "
                                       "You do not have sufficient balance")) == 216

    def test_message_sans_code(self):
        from gold_bot.brokers.bitvavo import code_erreur
        assert code_erreur(BrokerError("Bitvavo injoignable")) == 0


class TestRepriseApresRedemarrage:
    """Un redemarrage ne doit pas abandonner les positions ouvertes.

    Bitvavo ne connait que des avoirs : au demarrage le robot repartait
    avec zero position, alors que l'actif etait toujours la et son stop
    depose chez la plateforme. Tout ce que le robot est SEUL a assurer
    s'arretait donc au premier redemarrage, sans le moindre message :
    l'objectif (il n'y a pas d'OCO chez Bitvavo), le break-even, le
    trailing, et le decompte des places occupees.
    """

    @staticmethod
    def position():
        from gold_bot.core import Position
        return Position(id="ETHUSD", symbol="ETHUSD", side=Side.BUY,
                        volume=0.0045, entry_price=2077.5, stop_loss=2050.3,
                        take_profit=2132.9, opened_at=1000.0)

    def test_la_position_redevient_geree(self):
        b = broker_de_test(dry_run=False)
        b._regles["ETH-EUR"] = RegleMarche("ETH-EUR")
        assert b.reprendre(self.position()) is True
        assert [p.id for p in b.positions()] == ["ETHUSD"]

    def test_reprise_idempotente(self):
        b = broker_de_test(dry_run=False)
        b._regles["ETH-EUR"] = RegleMarche("ETH-EUR")
        b.reprendre(self.position())
        b.reprendre(self.position())
        assert len(b.positions()) == 1

    def test_un_marche_inconnu_n_est_pas_repris(self):
        from gold_bot.core import Position
        b = broker_de_test(dry_run=False)
        b._regles["ETH-EUR"] = RegleMarche("ETH-EUR")   # XAU n'y est pas
        orpheline = Position(id="XAUUSD", symbol="XAUUSD", side=Side.BUY,
                             volume=1.0, entry_price=2000.0, stop_loss=1990.0,
                             take_profit=2020.0, opened_at=0.0)
        assert b.reprendre(orpheline) is False
        assert b.positions() == []

    def test_l_etat_memorise_suffit_a_reconstruire(self, tmp_path, monkeypatch):
        """Sans identite complete en memoire, rien n'est reprenable."""
        from gold_bot.state import StateStore
        monkeypatch.setenv("GB_STATE_FILE", str(tmp_path / "etat.json"))
        store = StateStore()
        origine = self.position()
        origine.breakeven_done = True
        origine.max_favorable = 2100.0
        store.remember_position(origine)
        store.save()

        relue = StateStore().position_memorisee("ETHUSD")
        assert relue is not None
        assert relue.entry_price == pytest.approx(2077.5)
        assert relue.volume == pytest.approx(0.0045)
        assert relue.stop_loss == pytest.approx(2050.3)
        assert relue.take_profit == pytest.approx(2132.9)
        # L'etat de gestion voyage avec : sinon le stop pourrait reculer.
        assert relue.breakeven_done is True
        assert relue.max_favorable == pytest.approx(2100.0)
        assert relue.initial_risk == pytest.approx(27.2, rel=1e-3)

    def test_enregistrement_ancien_sans_identite_est_ignore(self, tmp_path, monkeypatch):
        """Mieux vaut ne rien reprendre qu'une position aux niveaux inventes."""
        from gold_bot.state import StateStore
        monkeypatch.setenv("GB_STATE_FILE", str(tmp_path / "etat.json"))
        store = StateStore()
        store.state.position_meta["ETHUSD"] = {"initial_risk": 27.2,
                                               "breakeven_done": True}
        assert store.position_memorisee("ETHUSD") is None

    def test_position_disparue_pendant_l_arret_est_comptabilisee(self):
        """Reprise puis rapprochee : la sortie est enregistree, pas perdue."""
        b = broker_de_test(dry_run=False)
        b._regles["ETH-EUR"] = RegleMarche("ETH-EUR", min_amount=0.001,
                                           min_notional=5.0)
        b._annuler_stop = lambda s: None
        b._ventes_depuis = lambda code, depuis: (2050.0, 0.0045, 0.02)
        b.reprendre(self.position())
        b._soldes = {"EUR": 40.0}          # le stop est parti pendant l'arret
        b._reconcilier({"ETH-EUR": 2050.0})
        assert b.positions() == []
        assert len(b.closed_trades()) == 1


class TestLeStopSuitReellementLaPosition:
    """Le stop doit bouger CHEZ BITVAVO, pas seulement dans la memoire du robot.

    Le defaut le plus couteux trouve dans ce robot, et le plus discret.

    Le gestionnaire de position ecrit son nouveau stop dans
    Position.stop_loss avant d'emettre l'action, et cet objet est celui-la
    meme que le broker detient. modify_position comparait donc le niveau
    demande a Position.stop_loss — c'est-a-dire une valeur a elle-meme.
    L'ecart valait toujours zero, l'ordre n'etait jamais repose, et la
    methode renvoyait True.

    Le 23 aout : HBAR monte a +4,9R, le robot croit son stop suiveur a
    +3,6R, Bitvavo tient toujours l'ordre initial a -1R. Sortie a -1,03R.
    Meme histoire sur BTC (+1,20R -> -0,09R) et FET (+1,27R -> -0,07R) :
    le break-even a 0,8R n'a jamais ete depose.

    Invisible parce que le simulateur, lui, deplace le stop sans condition :
    aucun backtest ne pouvait reveler le probleme.
    """

    @staticmethod
    def broker(monkeypatch):
        from gold_bot.core import Position
        b = broker_de_test(dry_run=False)
        b._regles["HBAR-EUR"] = RegleMarche("HBAR-EUR", price_precision=5,
                                            amount_decimals=8, min_notional=5.0)
        position = Position(
            id="HBARUSD", symbol="HBARUSD", side=Side.BUY, volume=306.5,
            entry_price=0.067153, stop_loss=0.066746, take_profit=0.068,
            opened_at=0.0)
        b._positions["HBARUSD"] = position
        b._stop_pose["HBARUSD"] = 0.066746      # ordre initial chez Bitvavo
        envoyes = []

        def appel(methode, chemin, params=None, corps=None, signe=True):
            if methode == "POST" and chemin == "/order":
                envoyes.append(corps)
                return {"orderId": "stop-1"}
            return {}

        monkeypatch.setattr(b, "_appel", appel)
        return b, position, envoyes

    def test_le_break_even_part_vers_la_plateforme(self, monkeypatch):
        b, position, envoyes = self.broker(monkeypatch)
        # Ce que fait le gestionnaire de position : il ecrit AVANT d'appeler.
        nouveau = 0.067214
        position.stop_loss = nouveau

        assert b.modify_position("HBARUSD", stop_loss=nouveau) is True
        stops = [c for c in envoyes if c.get("orderType") == "stopLossLimit"]
        assert len(stops) == 1, "l'ordre stop n'a pas ete repose chez Bitvavo"
        assert float(stops[0]["triggerAmount"]) == pytest.approx(nouveau, rel=1e-4)

    def test_le_niveau_retenu_est_celui_envoye(self, monkeypatch):
        b, position, _ = self.broker(monkeypatch)
        position.stop_loss = 0.067214
        b.modify_position("HBARUSD", stop_loss=0.067214)
        assert b._stop_pose["HBARUSD"] == pytest.approx(0.067214, rel=1e-4)

    def test_un_deplacement_negligeable_ne_coute_pas_d_appel(self, monkeypatch):
        """Le garde-fou d'origine reste utile : il ne doit pas disparaitre."""
        b, position, envoyes = self.broker(monkeypatch)
        position.initial_risk = 0.000407
        infime = 0.066748      # 0,005R plus haut, sous le seuil de 0,15R
        position.stop_loss = infime
        b.modify_position("HBARUSD", stop_loss=infime)
        assert [c for c in envoyes if c.get("orderType") == "stopLossLimit"] == []

    def test_stop_jamais_depose_est_toujours_pose(self, monkeypatch):
        """Apres un redemarrage, le robot ignore ce que tient la plateforme."""
        b, position, envoyes = self.broker(monkeypatch)
        b._stop_pose.pop("HBARUSD")
        position.stop_loss = 0.066750
        b.modify_position("HBARUSD", stop_loss=0.066750)
        assert len([c for c in envoyes if c.get("orderType") == "stopLossLimit"]) == 1

    def test_l_annulation_oublie_le_niveau(self, monkeypatch):
        b, _, _ = self.broker(monkeypatch)
        b._annuler_stop("HBARUSD")
        assert "HBARUSD" not in b._stop_pose

    def test_toute_la_montee_du_stop_arrive_chez_bitvavo(self, monkeypatch):
        """Le scenario HBAR complet : trois remontees, trois ordres reels."""
        b, position, envoyes = self.broker(monkeypatch)
        position.initial_risk = 0.000407
        for niveau in (0.067214, 0.067800, 0.068500):
            position.stop_loss = niveau
            assert b.modify_position("HBARUSD", stop_loss=niveau) is True
        stops = [c for c in envoyes if c.get("orderType") == "stopLossLimit"]
        assert len(stops) == 3
        envoyes_tries = [float(c["triggerAmount"]) for c in stops]
        assert envoyes_tries == sorted(envoyes_tries)
