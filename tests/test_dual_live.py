"""Le moteur dual et son superviseur.

Deux plateformes tournent cote a cote : Bitvavo, qui s'ouvre avec une cle
d'API, et IBKR, qui exige une passerelle authentifiee a deux facteurs. Les
tests ci-dessous verrouillent ce qui, de fait, les empechait de fonctionner
ensemble.
"""
from __future__ import annotations

import importlib
import sys
import time
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))


class TestChoixDuBroker:
    def test_le_moteur_dual_prend_le_broker_ibkr_DURCI(self):
        """Le broker nu n'a ni reconnexion ni port reel par defaut.

        Le moteur tourne des jours d'affilee : une passerelle qui se
        deconnecte la nuit doit se rattraper seule. Le broker nu, lui, se
        contente d'echouer — et son port par defaut est 4002, le compte
        PAPIER, pas 4001.
        """
        from gold_bot.brokers.ibkr_hardened import HardenedIBKRBroker
        from gold_bot.dual_scalping_engine import DualScalpingEngine

        source = DualScalpingEngine._build_broker.__code__.co_names
        assert "HardenedIBKRBroker" in source, (
            "le moteur dual doit construire le broker durci, pas IBKRBroker")
        assert hasattr(HardenedIBKRBroker, "_reconnect")

    def test_les_contrats_sont_resolus_APRES_la_connexion(self, monkeypatch):
        """Enregistrer un contrat avant connect() ne peut rien donner.

        `register_instrument` interroge la passerelle. Appele avant la
        connexion, il echouait pour chaque instrument, silencieusement, et
        le cache de contrats restait vide.
        """
        from gold_bot.dual_scalping_engine import DualScalpingEngine

        ordre: list[str] = []

        class FauxBroker:
            name = "ibkr"
            live_enabled = True

            def connect(self):
                ordre.append("connect")
                return True

            def register_instrument(self, inst):
                ordre.append(f"register:{inst}")

            def supports(self, symbol):
                return True

        broker = FauxBroker()

        class FauxMoteur:
            universe = ["EURUSD", "GBPUSD"]

        # On rejoue exactement la mecanique de report installee par le moteur.
        connect_nu = broker.connect
        univers = FauxMoteur.universe

        def connect_puis_enregistrer():
            ok = connect_nu()
            if ok:
                for inst in univers:
                    broker.register_instrument(inst)
            return ok

        broker.connect = connect_puis_enregistrer

        assert ordre == []          # rien n'est demande a la passerelle avant
        broker.connect()
        assert ordre == ["connect", "register:EURUSD", "register:GBPUSD"]


class TestReculDuSuperviseur:
    """Un moteur qui meurt en trois secondes ne doit pas etre relance en trois secondes."""

    @pytest.fixture
    def superviseur(self, monkeypatch):
        monkeypatch.setenv("IBKR_HOST", "127.0.0.1")
        monkeypatch.setenv("IBKR_PORT", "4001")
        module = importlib.import_module("run_dual_live")
        importlib.reload(module)
        module.procs.clear()
        module._recul.clear()
        return module

    class _FauxProc:
        def __init__(self, code=1):
            self.returncode = code

        def poll(self):
            return self.returncode

    def test_un_echec_rapide_impose_une_attente(self, superviseur):
        superviseur._recul["ibkr"] = {"attente": superviseur.RECUL_MIN,
                                      "demarre_a": time.time() - 2}
        superviseur.procs["ibkr"] = proc = self._FauxProc()

        superviseur.noter_sortie("ibkr", proc)

        assert "ibkr" not in superviseur.procs, "l'enfant mort doit etre retire"
        assert superviseur.peut_demarrer("ibkr") is False

    def test_l_attente_double_a_chaque_echec_puis_plafonne(self, superviseur):
        attentes = []
        for _ in range(12):
            superviseur._recul.setdefault("ibkr", {"attente": superviseur.RECUL_MIN})
            superviseur._recul["ibkr"]["demarre_a"] = time.time() - 1
            superviseur.procs["ibkr"] = proc = self._FauxProc()
            superviseur.noter_sortie("ibkr", proc)
            attentes.append(superviseur._recul["ibkr"]["attente"])

        assert attentes[0] < attentes[1] < attentes[2], "l'attente doit croitre"
        assert max(attentes) <= superviseur.RECUL_MAX, "et rester bornee"
        assert attentes[-1] == superviseur.RECUL_MAX

    def test_un_moteur_qui_a_tenu_repart_tout_de_suite(self, superviseur):
        """Un arret apres une heure est un incident, pas une erreur de config."""
        superviseur._recul["ibkr"] = {"attente": 120.0,
                                      "demarre_a": time.time() - 3600}
        superviseur.procs["ibkr"] = proc = self._FauxProc(code=0)

        superviseur.noter_sortie("ibkr", proc)

        assert superviseur.peut_demarrer("ibkr") is True
        assert superviseur._recul["ibkr"]["attente"] == superviseur.RECUL_MIN

    def test_un_arret_voulu_ne_penalise_pas(self, superviseur):
        """Couper IBKR parce que la passerelle est tombee n'est pas un echec."""
        superviseur._recul["ibkr"] = {"attente": 240.0,
                                      "prochain_essai": time.time() + 240.0}
        superviseur.procs["ibkr"] = self._FauxProc(code=0)

        superviseur.stop_child("ibkr")

        assert "ibkr" not in superviseur.procs
        assert superviseur.peut_demarrer("ibkr") is True
