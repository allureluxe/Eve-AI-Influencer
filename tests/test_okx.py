"""Execution sur OKX Europe.

L'API d'OKX n'est pas joignable depuis l'environnement de developpement :
ces tests sont la seule verification possible avant le premier ordre reel.

Ils portent sur les trois pieges propres a l'API v5, chacun capable de
casser silencieusement :
  - l'horodatage signe est une date ISO, pas un nombre de millisecondes ;
  - une reponse HTTP 200 peut porter un echec metier ;
  - sur un achat au marche au comptant, `sz` designe par defaut un montant
    en euros et non une quantite d'actif.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.brokers.base import BrokerError
from gold_bot.brokers.okx import (ACTIFS, OkxBroker, OkxConfig, RegleInstrument,
                                  decimales_du_pas, formater, horodatage_iso,
                                  marche)
from gold_bot.core import Side
from gold_bot.datasources import PROVIDER_CLASSES, DataRegistry
from gold_bot.datasources.providers import BinanceProvider, OkxProvider
from gold_bot.universe import CATALOGUE_CRYPTO, instrument_crypto


def broker_de_test(**kw) -> OkxBroker:
    cfg = OkxConfig(api_key="cle", api_secret="secret", passphrase="phrase",
                    quote_asset="EUR", dry_run=kw.pop("dry_run", True), **kw)
    return OkxBroker(cfg)


# ==========================================================================
class TestSignature:
    """Reference : utils.signature() du SDK Python publie par OKX."""

    @staticmethod
    def reference(horodatage, methode, chemin, corps, secret):
        message = str(horodatage) + methode.upper() + chemin + corps
        return base64.b64encode(hmac.new(secret.encode("utf-8"),
                                         message.encode("utf-8"),
                                         hashlib.sha256).digest()).decode()

    def test_get_sans_corps(self):
        b = broker_de_test()
        h = "2026-08-22T12:00:00.000Z"
        assert b._signer(h, "GET", "/api/v5/account/balance", "") == \
            self.reference(h, "GET", "/api/v5/account/balance", "", "secret")

    def test_post_avec_corps(self):
        b = broker_de_test()
        h = "2026-08-22T12:00:00.000Z"
        corps = json.dumps({"instId": "BTC-EUR", "side": "buy"}, separators=(",", ":"))
        assert b._signer(h, "POST", "/api/v5/trade/order", corps) == \
            self.reference(h, "POST", "/api/v5/trade/order", corps, "secret")

    def test_signature_encodee_en_base64(self):
        """OKX attend du base64, pas de l'hexadecimal comme Bitvavo."""
        b = broker_de_test()
        signature = b._signer("2026-08-22T12:00:00.000Z", "GET", "/x", "")
        assert base64.b64decode(signature)          # doit se decoder
        assert len(base64.b64decode(signature)) == 32

    def test_methode_mise_en_majuscules(self):
        b = broker_de_test()
        h = "2026-08-22T12:00:00.000Z"
        assert b._signer(h, "get", "/x", "") == b._signer(h, "GET", "/x", "")


class TestHorodatage:
    """Le piege le plus couteux : OKX signe une date ISO, pas un entier."""

    def test_format_iso_en_millisecondes(self):
        h = horodatage_iso()
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z", h), h

    def test_pas_un_nombre_de_millisecondes(self):
        assert not horodatage_iso().isdigit()


# ==========================================================================
class TestEnveloppeV5:
    """Une reponse HTTP 200 peut porter un echec : `code` fait foi."""

    def test_succes_rend_les_donnees(self):
        data = OkxBroker._extraire('{"code":"0","msg":"","data":[{"a":1}]}', "/x")
        assert data == [{"a": 1}]

    def test_code_non_nul_leve_une_erreur(self):
        with pytest.raises(BrokerError, match=r"\[51008\]"):
            OkxBroker._extraire('{"code":"51008","msg":"solde insuffisant","data":[]}', "/x")

    def test_detail_de_l_ordre_refuse_remonte(self):
        """Sur un ordre refuse, le motif utile est dans data[0], pas dans msg."""
        brut = ('{"code":"1","msg":"operation failed","data":'
                '[{"sCode":"51121","sMsg":"quantite sous le minimum"}]}')
        with pytest.raises(BrokerError, match="51121"):
            OkxBroker._extraire(brut, "/x")

    def test_reponse_illisible(self):
        with pytest.raises(BrokerError, match="illisible"):
            OkxBroker._extraire("<html>502</html>", "/x")


# ==========================================================================
class TestCorrespondanceDesMarches:
    def test_format_okx(self):
        assert marche("BTCUSD", "EUR") == "BTC-EUR"

    def test_or_rejete(self):
        assert marche("XAUUSD", "EUR") is None

    def test_catalogue_aligne_sur_l_univers(self):
        assert set(ACTIFS.values()) == set(CATALOGUE_CRYPTO)

    def test_source_et_execution_alignees(self):
        assert set(OkxProvider.ACTIFS) == set(ACTIFS)

    def test_unites_de_temps_en_majuscules(self):
        """OKX refuse « 4h » et accepte « 4H » : la casse compte."""
        assert OkxProvider.INTERVALS["H4"] == "4H"
        assert OkxProvider.INTERVALS["D1"] == "1D"
        assert OkxProvider.INTERVALS["M15"] == "15m"


# ==========================================================================
class TestArrondis:
    def test_quantite_arrondie_vers_le_bas(self):
        r = RegleInstrument("BTC-EUR", lot_size=0.00000001)
        assert r.arrondir_quantite(0.123456789) == pytest.approx(0.12345678)

    def test_prix_arrondi_au_pas(self):
        r = RegleInstrument("BTC-EUR", tick_size=0.1)
        assert r.arrondir_prix(61234.67) == pytest.approx(61234.7)

    def test_decimales_deduites_du_pas(self):
        assert decimales_du_pas(0.001) == 3
        assert decimales_du_pas(1.0) == 0
        assert decimales_du_pas(0.00000001) == 8

    def test_pas_de_notation_scientifique(self):
        assert "e" not in formater(0.00000001).lower()


# ==========================================================================
class TestGardeFousALOuverture:
    def test_vente_a_decouvert_refusee(self):
        b = broker_de_test()
        with pytest.raises(BrokerError, match="achat"):
            b.open_position(instrument_crypto("BTC", "crypto_major"),
                            Side.SELL, 0.001, 50000.0, 70000.0)

    def test_ouverture_sans_stop_refusee(self):
        b = broker_de_test()
        with pytest.raises(BrokerError, match="stop-loss"):
            b.open_position(instrument_crypto("BTC", "crypto_major"),
                            Side.BUY, 0.001, 0.0, 70000.0)

    def test_quantite_sous_le_minimum_refusee(self):
        b = broker_de_test()
        b._regles["BTC-EUR"] = RegleInstrument("BTC-EUR", lot_size=1e-8, min_size=0.0001)
        b._prix = lambda code: 60000.0
        with pytest.raises(BrokerError, match="minimum"):
            b.open_position(instrument_crypto("BTC", "crypto_major"),
                            Side.BUY, 0.00001, 58000.0, 64000.0)

    def test_marge_pour_les_frais(self):
        b = broker_de_test()
        b._regles["BTC-EUR"] = RegleInstrument("BTC-EUR", lot_size=1e-8)
        b._prix = lambda code: 60000.0
        b._account.margin_free = 60.0
        with pytest.raises(BrokerError, match="disponible"):
            b.open_position(instrument_crypto("BTC", "crypto_major"),
                            Side.BUY, 0.001, 58000.0, 64000.0)


class TestOrdreAttache:
    """Stop ET objectif attaches a l'entree : l'avantage d'OKX sur Bitvavo."""

    def test_ordre_porte_ses_deux_protections(self, monkeypatch):
        b = broker_de_test(dry_run=False)
        b._regles["BTC-EUR"] = RegleInstrument("BTC-EUR", tick_size=0.1, lot_size=1e-8)
        b._prix = lambda code: 60000.0
        b._prix_execute = lambda code, oid: 60000.0
        b._account.margin_free = 10000.0

        envoye = {}

        def faux_appel(methode, chemin, params=None, corps=None, signe=True):
            envoye["corps"] = corps
            return [{"ordId": "42"}]

        monkeypatch.setattr(b, "_appel", faux_appel)
        b.open_position(instrument_crypto("BTC", "crypto_major"),
                        Side.BUY, 0.001, 58000.0, 64000.0)

        corps = envoye["corps"]
        attaches = corps["attachAlgoOrds"][0]
        assert attaches["slTriggerPx"] == "58000"
        assert attaches["tpTriggerPx"] == "64000"
        assert attaches["slOrdPx"] == "-1", "sortie au marche au declenchement"

    def test_quantite_exprimee_en_actif_pas_en_euros(self, monkeypatch):
        """Sans tgtCcy, OKX lirait `sz` comme un montant en euros.

        L'ordre partirait sans erreur et achèterait la mauvaise taille :
        c'est le genre de bug qui ne se voit que sur le releve de compte.
        """
        b = broker_de_test(dry_run=False)
        b._regles["BTC-EUR"] = RegleInstrument("BTC-EUR", tick_size=0.1, lot_size=1e-8)
        b._prix = lambda code: 60000.0
        b._prix_execute = lambda code, oid: 60000.0
        b._account.margin_free = 10000.0

        envoye = {}
        monkeypatch.setattr(b, "_appel",
                            lambda m, c, params=None, corps=None, signe=True:
                            (envoye.update(corps=corps), [{"ordId": "1"}])[1])
        b.open_position(instrument_crypto("BTC", "crypto_major"),
                        Side.BUY, 0.001, 58000.0, 64000.0)
        assert envoye["corps"]["tgtCcy"] == "base_ccy"
        assert envoye["corps"]["sz"] == "0.001"
        assert envoye["corps"]["tdMode"] == "cash"


# ==========================================================================
class TestDeviseDeCotation:
    def test_registre_en_euros_ecarte_les_sources_en_dollars(self):
        r = DataRegistry(providers=[OkxProvider(), BinanceProvider()], devise_crypto="EUR")
        assert [p.name for p in r.usable("crypto")] == ["okx"]

    def test_okx_prioritaire_dans_le_registre(self):
        noms = [c.__name__ for c in PROVIDER_CLASSES]
        assert noms.index("OkxProvider") < noms.index("BinanceProvider")

    def test_devise_du_lieu_d_execution(self):
        from gold_bot.engine import _devise_du_lieu_d_execution
        assert _devise_du_lieu_d_execution("okx") == "EUR"
        assert _devise_du_lieu_d_execution("bitvavo") == "EUR"
        assert _devise_du_lieu_d_execution("binance_spot") == "", \
            "un lieu en dollars garde toutes ses sources de secours"


# ==========================================================================
class TestBougies:
    def test_bougie_non_cloturee_ecartee(self, monkeypatch):
        """La derniere bougie d'OKX est encore en train de bouger.

        La garder ferait decider le robot sur un prix non fige : le signal
        apparait puis disparait, et le journal devient incomprehensible.
        """
        rows = [
            ["1700000120000", "3", "3", "3", "3", "1", "1", "1", "0"],   # en cours
            ["1700000060000", "2", "2", "2", "2", "1", "1", "1", "1"],
            ["1700000000000", "1", "1", "1", "1", "1", "1", "1", "1"],
        ]
        monkeypatch.setattr("gold_bot.datasources.providers.http_get",
                            lambda *a, **k: {"code": "0", "data": rows})
        p = OkxProvider()
        monkeypatch.setattr(p, "throttle", lambda: None)
        bougies = p.fetch_candles("BTCUSD", "crypto", "M1", 3)
        assert [c.close for c in bougies] == [1.0, 2.0], \
            "la bougie en cours (confirm=0) doit etre ecartee"

    def test_ordre_chronologique_retabli(self, monkeypatch):
        rows = [["1700000060000", "2", "2", "2", "2", "1", "1", "1", "1"],
                ["1700000000000", "1", "1", "1", "1", "1", "1", "1", "1"]]
        monkeypatch.setattr("gold_bot.datasources.providers.http_get",
                            lambda *a, **k: {"code": "0", "data": rows})
        p = OkxProvider()
        monkeypatch.setattr(p, "throttle", lambda: None)
        bougies = p.fetch_candles("BTCUSD", "crypto", "M1", 2)
        assert bougies[0].ts < bougies[1].ts

    def test_instrument_inconnu_n_est_pas_une_panne(self, monkeypatch):
        from gold_bot.datasources.base import SymbolNotSupported
        monkeypatch.setattr("gold_bot.datasources.providers.http_get",
                            lambda *a, **k: {"code": "51001", "msg": "instrument inconnu"})
        p = OkxProvider()
        monkeypatch.setattr(p, "throttle", lambda: None)
        with pytest.raises(SymbolNotSupported):
            p.fetch_candles("BTCUSD", "crypto", "H1", 100)

    def test_erreur_reelle_reste_une_panne(self, monkeypatch):
        from gold_bot.datasources.base import ProviderError, SymbolNotSupported
        monkeypatch.setattr("gold_bot.datasources.providers.http_get",
                            lambda *a, **k: {"code": "50011", "msg": "trop de requetes"})
        p = OkxProvider()
        monkeypatch.setattr(p, "throttle", lambda: None)
        with pytest.raises(ProviderError) as exc:
            p.fetch_candles("BTCUSD", "crypto", "H1", 100)
        assert not isinstance(exc.value, SymbolNotSupported)


# ==========================================================================
class TestFraisEtEchelleDeTemps:
    """L'arithmetique qui autorise le H1 sur OKX la ou Bitvavo impose H4."""

    def test_le_h1_tient_sur_okx(self):
        aller_retour = 2 * 0.0010
        assert aller_retour / 0.0154 <= 0.15, (
            "a 0,20 % d'aller-retour, un stop H1 laisse les frais sous "
            "15 % du risque : c'est ce qui rend le H1 possible ici")

    def test_okx_deux_fois_et_demie_moins_cher_que_bitvavo(self):
        assert (2 * 0.0025) / (2 * 0.0010) == pytest.approx(2.5)

    def test_configuration_livree_coherente(self):
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.okx.json")
        assert cfg.engine.broker == "okx"
        assert cfg.engine.currency == "EUR"
        assert cfg.risk.commission_pct == pytest.approx(0.0010)
        assert cfg.strategy.entry_tf == "H1", "le H1 est tout l'interet d'OKX"
        assert cfg.engine.dry_run is True, "on ne livre jamais arme en reel"
        assert cfg.risk.max_daily_trades == 0, "demande explicite : pas de bridage"
        assert cfg.validate() == []


# ==========================================================================
class TestDeuxRobotsEnParallele:
    """Faire tourner un robot par plateforme est un usage prevu.

    Avec un chemin d'etat fixe, les deux ecriraient dans le meme fichier :
    compteurs de pertes fausses, journaux melanges, plafonds de risque
    inoperants. C'est silencieux, et donc dangereux.
    """

    def test_etats_separes_par_plateforme(self, tmp_path, monkeypatch):
        from gold_bot.state import StateStore, TradeJournal
        monkeypatch.delenv("GB_STATE_FILE", raising=False)
        monkeypatch.delenv("GB_TRADES_FILE", raising=False)
        monkeypatch.chdir(tmp_path)
        assert StateStore(instance="okx").path != StateStore(instance="bitvavo").path
        assert TradeJournal(instance="okx").path != TradeJournal(instance="bitvavo").path

    def test_variable_d_environnement_prioritaire(self, tmp_path, monkeypatch):
        from gold_bot.state import StateStore
        monkeypatch.setenv("GB_STATE_FILE", "/tmp/impose.json")
        assert StateStore(instance="okx").path == "/tmp/impose.json"

    def test_historique_commun_repris(self, tmp_path, monkeypatch):
        """Un robot deja en production ne doit pas perdre son historique."""
        from gold_bot.state import chemin_par_instance
        monkeypatch.delenv("GB_STATE_FILE", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "state.json").write_text("{}")
        assert chemin_par_instance("data/state.json", "GB_STATE_FILE",
                                   "binance_spot") == "data/state.json"

    def test_sans_instance_le_chemin_reste_celui_d_avant(self, monkeypatch):
        from gold_bot.state import chemin_par_instance
        monkeypatch.delenv("GB_STATE_FILE", raising=False)
        assert chemin_par_instance("data/state.json", "GB_STATE_FILE", "") == "data/state.json"


class TestBacktestCoherent:
    def test_le_rejeu_utilise_la_meme_devise_que_le_moteur(self):
        """Un backtest en dollars pour une config en euros ne mesure rien.

        Les resultats seraient coherents entre eux mais sans rapport avec
        le marche ou les ordres partiront : le backtest doit rejouer ce que
        le robot vivra, pas une variante.
        """
        from gold_bot.backtest import Backtester
        from gold_bot.settings import BotConfig
        bt = Backtester(BotConfig.load("robot.okx.json"))
        assert bt.registry.devise_crypto == "EUR"
        assert [p.name for p in bt.registry.usable("crypto")] == ["okx", "bitvavo"]
