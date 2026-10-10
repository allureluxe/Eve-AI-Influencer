"""L'univers se relit chez Bitvavo toutes les heures, pas seulement au demarrage.

9 oct. 2026 : MAGIC (+86 % dans la journee) casse son plus-haut vers 8h,
mais n'entre dans l'univers qu'au redemarrage de 18h13 — il n'etait calcule
qu'au demarrage. Une crypto qui se reveille en cours de journee etait
invisible jusqu'au redemarrage suivant.
"""
from __future__ import annotations

from types import SimpleNamespace

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

import gold_bot.universe as univers
from gold_bot.engine import TradingEngine
from gold_bot.universe import ACTIFS_PAR_SYMBOLE, DEFAULT_UNIVERSE, Universe


class Courtier:
    def __init__(self):
        self.recharges = 0
        self.enregistres = []

    def supports(self, sym):
        return sym.upper() in ACTIFS_PAR_SYMBOLE

    def rafraichir_marches(self):
        self.recharges += 1

    def register_instrument(self, inst):
        self.enregistres.append(inst.symbol)


def _moteur(broker="bitvavo", symbols=None):
    m = object.__new__(TradingEngine)
    m.universe = Universe()
    m.broker = Courtier()
    m.config = SimpleNamespace(engine=SimpleNamespace(
        broker=broker, symbols=symbols or [], univers_dynamique_bitvavo=False))
    return m


def _decouvertes(monkeypatch, actifs):
    monkeypatch.setattr(univers, "cryptos_bitvavo",
                        lambda *a, **k: {a_: "crypto_alt" for a_ in actifs})


def test_le_premier_passage_ne_relit_rien(monkeypatch):
    _decouvertes(monkeypatch, ["ZZREVEILUSD"[:-3]])
    m = _moteur()
    assert m._rafraichir_univers(maintenant=1000.0) == []
    assert m.universe.get("ZZREVEILUSD") is None


def test_une_crypto_qui_se_reveille_entre_dans_le_scan_dans_l_heure(monkeypatch):
    _decouvertes(monkeypatch, ["ZZREVEIL"])
    m = _moteur()
    m._rafraichir_univers(maintenant=1000.0)
    assert m._rafraichir_univers(maintenant=1000.0 + 1800) == [], "trop tot"
    nouvelles = m._rafraichir_univers(maintenant=1000.0 + 3600)
    assert nouvelles == ["ZZREVEILUSD"]
    inst = m.universe.get("ZZREVEILUSD")
    assert inst is not None and inst.enabled, "la crypto n'est pas scannee"
    assert "ZZREVEILUSD" in m.broker.enregistres, "le courtier ne la connait pas"
    assert m.broker.recharges == 1, "sans regles de marche, supports() la refuse"


def test_une_crypto_retombee_est_exclue_des_achats_mais_pas_retiree(monkeypatch):
    _decouvertes(monkeypatch, ["ZZRETOMBE"])
    m = _moteur()
    m._rafraichir_univers(maintenant=0.0)
    m._rafraichir_univers(maintenant=3600.0)
    _decouvertes(monkeypatch, ["AUTRECHOSE"])
    m._rafraichir_univers(maintenant=7200.0)
    inst = m.universe.get("ZZRETOMBEUSD")
    assert inst is not None, "une position detenue perdrait sa gestion"
    assert inst.enabled is False


def test_le_catalogue_ecrit_en_dur_n_est_jamais_touche(monkeypatch):
    _decouvertes(monkeypatch, ["ZZSEULE"])
    m = _moteur()
    avant = {i.symbol: i.enabled for i in m.universe if i.symbol in
             {d.symbol for d in DEFAULT_UNIVERSE}}
    m._rafraichir_univers(maintenant=0.0)
    m._rafraichir_univers(maintenant=3600.0)
    apres = {s: m.universe.get(s).enabled for s in avant}
    assert apres == avant


def test_panne_reseau_rien_ne_change(monkeypatch):
    monkeypatch.setattr(univers, "cryptos_bitvavo", lambda *a, **k: {})
    m = _moteur()
    etat = {i.symbol: i.enabled for i in m.universe}
    m._rafraichir_univers(maintenant=0.0)
    m._rafraichir_univers(maintenant=3600.0)
    assert {i.symbol: i.enabled for i in m.universe} == etat


def test_liste_fixee_a_la_main_ou_autre_courtier_pas_de_rafraichissement(monkeypatch):
    _decouvertes(monkeypatch, ["ZZFIXE"])
    for m in (_moteur(symbols=["BTCUSD"]), _moteur(broker="ibkr")):
        m._rafraichir_univers(maintenant=0.0)
        assert m._rafraichir_univers(maintenant=3600.0) == []
        assert m.universe.get("ZZFIXEUSD") is None
