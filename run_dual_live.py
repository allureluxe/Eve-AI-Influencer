#!/usr/bin/env python3
"""Lance ensemble les moteurs reels Bitvavo et IBKR.

Bitvavo demarre seul : une cle d'API suffit. IBKR non — il faut un IB Gateway
authentifie, second facteur (SMS) compris. Le moteur IBKR n'est donc jamais
lance tant que la POIGNEE DE MAIN API n'aboutit pas.

La version precedente se contentait de tester si le port TCP acceptait une
connexion. Or IB Gateway ouvre ce port des qu'il tourne, y compris quand il
est bloque sur l'ecran du code de securite : le superviseur croyait la voie
libre, lancait le moteur, le moteur echouait, mourait, et etait relance —
en boucle, sans que rien ne dise qu'il manquait un code SMS.

Le test est maintenant celui de `gold_bot/ibkr_readiness`, qui va jusqu'a
demander la liste des comptes. Et tout redemarrage d'enfant passe par un
recul progressif : un moteur qui echoue vite n'est plus relance vite.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gold_bot.ibkr_readiness import PRETE, etat_passerelle  # noqa: E402

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable or "/usr/bin/python3"
CHILDREN = {
    "bitvavo": [PYTHON, str(ROOT / "run_dual_scalping.py"), "--config", str(ROOT / "robot.bitvavo.json")],
    "ibkr": [PYTHON, str(ROOT / "run_dual_scalping.py"), "--config", str(ROOT / "robot.ibkr.json")],
}

procs: dict[str, subprocess.Popen] = {}
stopping = False
IBKR_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.environ.get("IBKR_PORT", "4001"))

# Recul progressif par enfant : date du dernier demarrage, duree d'attente
# courante, et nombre d'echecs rapides consecutifs.
RECUL_MIN = 5.0
RECUL_MAX = 300.0
_recul: dict[str, dict] = {}


def log(msg: str) -> None:
    print(f"[DUAL] {msg}", flush=True)


def ibkr_api_ready() -> tuple[bool, str]:
    """Le Gateway est-il REELLEMENT utilisable ? (poignee de main complete)

    Retourne aussi la phrase a journaliser : c'est elle qui distingue
    « Gateway eteinte » de « Gateway en attente du code SMS », et c'est cette
    distinction qui manquait quand le robot tournait a vide.
    """
    etat = etat_passerelle(IBKR_HOST, IBKR_PORT)
    return etat.etat == PRETE, etat.resume()


def peut_demarrer(name: str) -> bool:
    """Le recul progressif autorise-t-il un nouveau demarrage maintenant ?"""
    info = _recul.get(name)
    if not info:
        return True
    reste = info["prochain_essai"] - time.time()
    if reste > 0:
        if not info.get("annonce"):
            log(f"{name}: nouvelle tentative dans {reste:.0f}s (recul apres echec rapide)")
            info["annonce"] = True
        return False
    return True


def noter_sortie(name: str, proc: subprocess.Popen) -> None:
    """Un enfant vient de s'arreter : allonger ou reinitialiser le recul.

    Un moteur qui a tenu plus d'une minute a fait son travail ; son arret est
    un incident isole et il repart tout de suite. Un moteur qui meurt en
    quelques secondes echoue sur sa configuration ou sa connexion : le
    relancer aussitot ne fait que remplir le journal.
    """
    duree = time.time() - _recul.get(name, {}).get("demarre_a", 0.0)
    code = proc.returncode
    # L'enfant mort est retire tout de suite : sans cela la boucle le
    # redecouvrait a chaque tour et doublait le recul a chaque passage.
    if procs.get(name) is proc:
        procs.pop(name, None)
    if duree >= 60.0:
        _recul[name] = {"attente": RECUL_MIN, "prochain_essai": 0.0}
        log(f"{name} s'est arrete (code {code}) apres {duree:.0f}s; redemarrage immediat")
        return
    info = _recul.setdefault(name, {"attente": RECUL_MIN})
    attente = min(RECUL_MAX, max(RECUL_MIN, info.get("attente", RECUL_MIN) * 2))
    info.update({"attente": attente, "prochain_essai": time.time() + attente,
                 "annonce": False})
    log(f"{name} s'est arrete (code {code}) apres seulement {duree:.0f}s; "
        f"attente de {attente:.0f}s avant de reessayer")


def stop_child(name: str) -> None:
    proc = procs.pop(name, None)
    # Arret VOULU : il ne compte jamais comme un echec, donc pas de recul —
    # y compris quand l'enfant venait deja de se terminer. Sinon une coupure
    # de passerelle laissait derriere elle une attente de plusieurs minutes
    # qui retardait le redemarrage une fois le Gateway revenu.
    _recul.pop(name, None)
    if not proc or proc.poll() is not None:
        return
    log(f"arret {name}: la passerelle IBKR n'est plus utilisable")
    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    deadline = time.time() + 15
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.2)
    if proc.poll() is None:
        proc.kill()


def stop_all(signum=None, frame=None) -> None:
    global stopping
    if stopping:
        return
    stopping = True
    log(f"arret demande ({signum}); arret propre des deux moteurs")
    for proc in procs.values():
        if proc.poll() is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
    deadline = time.time() + 55
    while time.time() < deadline:
        if not any(p.poll() is None for p in procs.values()):
            return
        time.sleep(0.25)
    for proc in procs.values():
        if proc.poll() is None:
            proc.kill()


def start(name: str) -> None:
    if not peut_demarrer(name):
        return
    env = os.environ.copy()
    if name == "ibkr":
        env["IBKR_HOST"] = IBKR_HOST
        env["IBKR_PORT"] = str(IBKR_PORT)
        env["IBKR_TRADING_LIVE"] = "1"
        env["IBKR_ALLOW_SHORT"] = "1"
    elif name == "bitvavo":
        env["BITVAVO_DRY_RUN"] = "0"
    log(f"demarrage {name}: {' '.join(CHILDREN[name])}")
    procs[name] = subprocess.Popen(CHILDREN[name], cwd=ROOT, env=env)
    _recul.setdefault(name, {"attente": RECUL_MIN})["demarre_a"] = time.time()


def main() -> int:
    signal.signal(signal.SIGTERM, stop_all)
    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGHUP, stop_all)

    # Bitvavo demarre seul : une cle d'API lui suffit. IBKR attend une
    # passerelle reellement authentifiee, et n'est jamais relance en boucle
    # tant qu'elle ne l'est pas.
    start("bitvavo")
    derniere_phrase = ""
    prochaine_sonde = 0.0
    pret = False

    while not stopping:
        # La sonde ouvre une vraie session API : on ne la relance pas toutes
        # les trois secondes. Toutes les 20 s suffisent largement, un Gateway
        # ne s'authentifie pas plus vite que l'operateur ne lit son SMS.
        if time.time() >= prochaine_sonde:
            pret, phrase = ibkr_api_ready()
            prochaine_sonde = time.time() + 20.0
            if phrase != derniere_phrase:
                log(phrase)
                derniere_phrase = phrase

        ibkr_proc = procs.get("ibkr")
        ibkr_alive = ibkr_proc is not None and ibkr_proc.poll() is None

        if not pret:
            if ibkr_alive:
                stop_child("ibkr")
        elif not ibkr_alive:
            if ibkr_proc is not None:
                noter_sortie("ibkr", ibkr_proc)
            start("ibkr")

        bitvavo = procs.get("bitvavo")
        if bitvavo is not None and bitvavo.poll() is not None:
            noter_sortie("bitvavo", bitvavo)
            start("bitvavo")
        elif bitvavo is None:
            start("bitvavo")

        time.sleep(3)

    stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
