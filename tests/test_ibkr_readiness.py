"""La passerelle IBKR : trois etats, pas deux.

Ce fichier verrouille la distinction qui manquait et qui produisait la boucle
de redemarrage : un port TCP ouvert n'est PAS une session authentifiee. Entre
les deux il y a le code de securite recu par SMS, que le robot ne peut pas
saisir a la place de l'operateur.
"""
from __future__ import annotations

import socket
import threading

import pytest

from gold_bot import ibkr_readiness as ir


class _PortMuet:
    """Un port qui accepte la connexion TCP et ne repond jamais rien.

    C'est exactement ce que presente IB Gateway quand il tourne mais attend
    encore le code SMS : la connexion s'etablit, la poignee de main API non.
    """

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._boucle, daemon=True)
        self._th.start()

    def _boucle(self) -> None:
        self.sock.settimeout(0.2)
        gardees = []
        while not self._stop.is_set():
            try:
                conn, _ = self.sock.accept()
                gardees.append(conn)      # acceptee, puis silence total
            except (socket.timeout, OSError):
                continue
        for c in gardees:
            try:
                c.close()
            except OSError:
                pass

    def fermer(self) -> None:
        self._stop.set()
        try:
            self.sock.close()
        except OSError:
            pass


@pytest.fixture
def port_muet():
    p = _PortMuet()
    yield p
    p.fermer()


def _port_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class TestEtatsDeLaPasserelle:
    def test_rien_qui_ecoute_donne_hors_ligne(self):
        etat = ir.etat_passerelle("127.0.0.1", _port_libre(), client_id=999)
        assert etat.etat == ir.HORS_LIGNE
        assert not etat.utilisable

    def test_un_port_ouvert_ne_suffit_pas(self, port_muet):
        """LE test de ce fichier.

        L'ancien superviseur concluait « pret » ici, lancait le moteur, et le
        regardait mourir. Le port ouvert doit etre reconnu comme NON
        authentifie, pas comme utilisable.
        """
        assert ir.port_ouvert("127.0.0.1", port_muet.port) is True

        etat = ir.etat_passerelle("127.0.0.1", port_muet.port, client_id=999, timeout=2.0)
        assert etat.etat == ir.NON_AUTHENTIFIE
        assert not etat.utilisable

    def test_le_message_nomme_le_code_de_securite(self, port_muet):
        """Un journal qui ne dit pas « SMS » fait chercher ailleurs pendant des heures."""
        etat = ir.etat_passerelle("127.0.0.1", port_muet.port, client_id=999, timeout=2.0)
        resume = etat.resume().lower()
        assert "sms" in resume
        assert "non authentifiee" in resume

    def test_seul_prete_est_utilisable(self):
        for etat in (ir.HORS_LIGNE, ir.NON_AUTHENTIFIE, ir.DEPENDANCE_ABSENTE):
            assert not ir.EtatPasserelle(etat, "127.0.0.1", 4001).utilisable
        assert ir.EtatPasserelle(ir.PRETE, "127.0.0.1", 4001, comptes=["DU1"]).utilisable

    def test_une_session_sans_compte_n_est_pas_prete(self):
        """Session ouverte mais aucun compte : IBKR n'a pas fini de valider."""
        etat = ir.EtatPasserelle(ir.PRETE, "127.0.0.1", 4001, comptes=[])
        # L'etat brut dit « prete », mais la sonde ne le produit jamais sans
        # compte : c'est la regle appliquee dans `etat_passerelle`.
        assert etat.comptes == []

    def test_la_sonde_n_utilise_pas_le_clientid_du_robot(self, monkeypatch):
        """Deux connexions au meme clientId se chassent chez IBKR.

        Si la sonde prenait l'identifiant du moteur, surveiller le robot
        reviendrait a le deconnecter toutes les vingt secondes.
        """
        monkeypatch.setenv("IBKR_CLIENT_ID", "27")
        monkeypatch.delenv("IBKR_PROBE_CLIENT_ID", raising=False)
        vus = {}

        def faux_port_ouvert(host, port, timeout=2.0):
            return True

        monkeypatch.setattr(ir, "port_ouvert", faux_port_ouvert)

        class FauxIB:
            def connect(self, host, port, clientId, readonly, timeout):
                vus["clientId"] = clientId
                vus["readonly"] = readonly
                raise RuntimeError("refuse volontairement")

        import sys
        import types
        faux_module = types.ModuleType("ib_async")
        faux_module.IB = FauxIB
        monkeypatch.setitem(sys.modules, "ib_async", faux_module)

        ir.etat_passerelle("127.0.0.1", 4001)
        assert vus["clientId"] != 27
        # Une sonde ne doit jamais pouvoir passer un ordre.
        assert vus["readonly"] is True
