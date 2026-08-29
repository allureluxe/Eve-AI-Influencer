"""Etat reel de la passerelle IBKR, avant de lancer quoi que ce soit.

POURQUOI CE MODULE EXISTE
-------------------------
IBKR ne s'ouvre pas avec une cle d'API comme Bitvavo. Il faut un IB Gateway
(ou TWS) demarre, authentifie avec identifiant, mot de passe ET un second
facteur — chez cet operateur, un code recu par SMS. Le robot ne parle jamais
au serveur d'IBKR : il parle a ce Gateway, en local, sur un port TCP.

Il y a donc TROIS etats, et pas deux, alors que le superviseur n'en
distinguait que deux :

  1. le port n'ecoute pas          -> le Gateway n'est pas lance ;
  2. le port ecoute, mais la poignee de main API n'aboutit pas
                                   -> le Gateway tourne et attend le CODE SMS,
                                      ou l'API n'est pas activee ;
  3. la poignee de main aboutit et un compte est retourne
                                   -> la, et seulement la, on peut trader.

Confondre 2 et 3 est ce qui produisait la boucle de redemarrage : un simple
`socket.create_connection()` reussit des l'etat 2. Le superviseur croyait la
voie libre, lancait le moteur, le moteur echouait sur la connexion API, le
processus mourait, le superviseur le relancait — indefiniment, sans que le
journal ne dise jamais qu'il manquait un code SMS.

Ce module fait la vraie poignee de main et nomme l'etat.
"""
from __future__ import annotations

import logging
import os
import socket
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Etats possibles, du plus casse au plus utilisable.
HORS_LIGNE = "hors_ligne"          # rien n'ecoute sur le port
NON_AUTHENTIFIE = "non_authentifie"  # le port ecoute, l'API ne repond pas
DEPENDANCE_ABSENTE = "dependance_absente"  # ib_async n'est pas installe
PRETE = "prete"                    # poignee de main faite, compte connu


@dataclass
class EtatPasserelle:
    """Ce que le Gateway repond, et ce qu'il faut en faire."""

    etat: str
    host: str
    port: int
    comptes: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def utilisable(self) -> bool:
        return self.etat == PRETE

    def resume(self) -> str:
        if self.etat == PRETE:
            return (f"Gateway IBKR prete sur {self.host}:{self.port} — "
                    f"compte(s) : {', '.join(self.comptes) or 'aucun'}")
        if self.etat == HORS_LIGNE:
            return (f"Gateway IBKR absente : rien n'ecoute sur {self.host}:{self.port}. "
                    "Lancer IB Gateway et s'y connecter.")
        if self.etat == DEPENDANCE_ABSENTE:
            return f"dependance IBKR absente : pip install ib_async ({self.detail})"
        return (f"Gateway IBKR NON AUTHENTIFIEE sur {self.host}:{self.port} : le port "
                "ecoute mais l'API ne repond pas. Le Gateway attend probablement le "
                "code de securite (SMS) ou l'API n'est pas activee dans "
                "Configuration > API > Settings. Aucun ordre ne partira tant que "
                f"cet ecran n'est pas franchi. [{self.detail}]")


def port_ouvert(host: str, port: int, timeout: float = 2.0) -> bool:
    """Le Gateway ecoute-t-il ? Ne dit RIEN de l'authentification."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


def etat_passerelle(host: str | None = None, port: int | None = None,
                    client_id: int | None = None, timeout: float = 8.0) -> EtatPasserelle:
    """Poignee de main API complete. C'est le seul verdict qui compte.

    Un `clientId` distinct de celui du robot est utilise par defaut : deux
    connexions au meme identifiant se chassent l'une l'autre chez IBKR, et
    une sonde ne doit jamais deconnecter le moteur qu'elle surveille.
    """
    host = host or os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(port if port is not None else os.getenv("IBKR_PORT", "4001"))
    if client_id is None:
        sonde = os.getenv("IBKR_PROBE_CLIENT_ID", "").strip()
        client_id = int(sonde) if sonde else int(os.getenv("IBKR_CLIENT_ID", "27")) + 100

    if not port_ouvert(host, port, timeout=min(timeout, 3.0)):
        return EtatPasserelle(HORS_LIGNE, host, port)

    try:
        from ib_async import IB
    except ImportError as exc:
        return EtatPasserelle(DEPENDANCE_ABSENTE, host, port, detail=str(exc)[:120])

    ib = IB()
    try:
        # `readonly=True` : la sonde ne doit jamais pouvoir passer un ordre.
        ib.connect(host, port, clientId=client_id, readonly=True, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - toute panne signifie « pas prete »
        return EtatPasserelle(NON_AUTHENTIFIE, host, port, detail=str(exc)[:160])

    try:
        comptes = [c for c in (ib.managedAccounts() or []) if c]
        if not comptes:
            # Session ouverte mais aucun compte : IBKR n'a pas fini de valider
            # l'ouverture de session. Ce n'est pas encore utilisable.
            return EtatPasserelle(NON_AUTHENTIFIE, host, port,
                                  detail="aucun compte retourne par le Gateway")
        return EtatPasserelle(PRETE, host, port, comptes=comptes)
    finally:
        try:
            ib.disconnect()
        except Exception:  # noqa: BLE001
            pass
