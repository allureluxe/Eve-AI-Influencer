"""La veille de l'agent : des controles chiffres, sans modele de langage.

Decision de l'operateur, 3 oct. 2026 : l'agent doit AGIR, pas seulement
repondre -- « surveiller le robot, prevenir ». Sa boucle autonome existait
mais echouait a chaque cycle : le modele gratuit (Groq) epuisait son quota
quotidien en quelques heures. Ces controles-ci ne coutent rien, tournent
toutes les 5 minutes dans le service de l'agent, et previennent l'operateur
(onglet Alertes + notification) quand quelque chose cloche.

Ils ne MODIFIENT rien : ni robot, ni configuration, ni ordre. Ils regardent
et ils previennent. Chaque probleme n'est annonce qu'une fois par 6 heures.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

RACINE = Path(__file__).resolve().parents[1]
SERVICES_SIMULATION = ("robot-demo", "robot-demo2", "robot-demo3", "robot-lab")
SILENCE_SECONDES = 6 * 3600


@dataclass
class Alerte:
    cle: str            # identifiant stable du probleme, pour ne pas le repeter
    niveau: str         # "warning" ou "critical"
    titre: str
    corps: str


# ---------------------------------------------------------------- controles purs

def positions_sous_le_stop(meta: dict, bids: dict[str, float]) -> list[str]:
    """Positions reelles dont le prix de vente est au stop ou dessous."""
    sous = []
    for sym, m in meta.items():
        if float(m.get("volume") or 0) <= 0 or not m.get("stop_loss"):
            continue
        bid = bids.get(sym[:-3] + "-EUR") if sym.endswith("USD") else None
        if bid and bid <= float(m["stop_loss"]):
            sous.append(sym[:-3])
    return sous


def controler(etat_reel: dict, maintenant: float, actif: Callable[[str], bool],
              bids: dict[str, float], memoire_libre_mo: float, disque_pct: float,
              lab_maj: Optional[float], deja_sous_stop: set[str],
              sauvegarde_maj: Optional[float] = None) -> tuple[list[Alerte], set[str]]:
    """Tous les controles. Rend les alertes et les positions vues sous le stop.

    Une position sous son stop n'alerte qu'au 2e controle consecutif : le
    filet du robot doit avoir eu le temps de la vendre (un cycle = 10 s).
    """
    alertes: list[Alerte] = []
    if not actif("robot-trading"):
        alertes.append(Alerte("reel-arrete", "critical", "Robot réel arrêté",
                              "Le service robot-trading ne tourne plus. Vos stops restent "
                              "posés chez Bitvavo, mais plus rien ne les remonte."))
    else:
        dernier = float(etat_reel.get("last_cycle") or 0)
        if dernier and maintenant - dernier > 600:
            alertes.append(Alerte("reel-fige", "critical", "Robot réel figé",
                                  f"Aucun cycle depuis {int((maintenant - dernier) / 60)} min, "
                                  "alors que le service tourne."))
    sous = set(positions_sous_le_stop(etat_reel.get("position_meta") or {}, bids))
    persistantes = sorted(sous & deja_sous_stop)
    if persistantes:
        alertes.append(Alerte("sous-stop-" + "-".join(persistantes), "critical",
                              "Position sous son stop, non vendue",
                              f"{', '.join(persistantes)} : le prix est passé sous le stop "
                              "et la position est toujours ouverte."))
    for s in SERVICES_SIMULATION:
        if not actif(s):
            alertes.append(Alerte(f"arret-{s}", "warning", f"{s} arrêté",
                                  "Simulation à l'arrêt : aucun argent en jeu, mais elle ne mesure plus rien."))
    if memoire_libre_mo < 500:
        alertes.append(Alerte("memoire", "warning", "Mémoire du serveur presque pleine",
                              f"{memoire_libre_mo:.0f} Mo libres : le système risque de couper un robot."))
    if disque_pct > 85:
        alertes.append(Alerte("disque", "warning", "Disque presque plein",
                              f"Disque rempli à {disque_pct:.0f} %."))
    if lab_maj is not None and maintenant - lab_maj > 6 * 3600:
        alertes.append(Alerte("lab-bloque", "warning", "Le Lab ne produit plus",
                              f"Aucun résultat depuis {int((maintenant - lab_maj) / 3600)} h."))
    if sauvegarde_maj is not None and maintenant - sauvegarde_maj > 30 * 3600:
        alertes.append(Alerte("sauvegarde", "warning", "Sauvegarde en retard",
                              f"Dernière sauvegarde il y a {int((maintenant - sauvegarde_maj) / 3600)} h "
                              "(elle doit tourner chaque nuit à 3h40)."))
    return alertes, sous


# ---------------------------------------------------------------- lectures reelles

def _actif(service: str) -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", service], capture_output=True,
                           text=True, timeout=10)
        return r.stdout.strip() == "active"
    except Exception:  # noqa: BLE001 - un controle rate n'est pas une panne
        return True


def _bids() -> dict[str, float]:
    try:
        with urllib.request.urlopen("https://api.bitvavo.com/v2/ticker/book", timeout=15) as r:
            return {b["market"]: float(b["bid"]) for b in json.load(r) if b.get("bid")}
    except Exception:  # noqa: BLE001
        return {}


def _memoire_libre_mo() -> float:
    try:
        for ligne in open("/proc/meminfo"):
            if ligne.startswith("MemAvailable:"):
                return int(ligne.split()[1]) / 1024
    except OSError:
        pass
    return 1e9


class Veille:
    """Etat de la veille entre deux passages (vit dans le service de l'agent)."""

    def __init__(self, prevenir: Callable[[Alerte], None]) -> None:
        self.prevenir = prevenir
        self._annonce: dict[str, float] = {}
        self._sous_stop: set[str] = set()

    def passer(self) -> list[Alerte]:
        maintenant = time.time()
        try:
            etat = json.loads((RACINE / "data/state.json").read_text())
        except Exception:  # noqa: BLE001
            etat = {}
        lab = RACINE / "data/lab-book.jsonl"
        sauv = RACINE / "data/sauvegarde_quotidienne.log"
        disque = shutil.disk_usage(str(RACINE))
        alertes, self._sous_stop = controler(
            etat, maintenant, _actif, _bids(), _memoire_libre_mo(),
            disque.used / disque.total * 100, lab.stat().st_mtime if lab.exists() else None,
            self._sous_stop, sauv.stat().st_mtime if sauv.exists() else None)
        nouvelles = []
        for a in alertes:
            if maintenant - self._annonce.get(a.cle, 0.0) >= SILENCE_SECONDES:
                self._annonce[a.cle] = maintenant
                nouvelles.append(a)
                try:
                    self.prevenir(a)
                except Exception:  # noqa: BLE001 - prevenir ne doit jamais casser l'agent
                    pass
        return nouvelles


def prevenir_par_l_application(a: Alerte) -> None:
    """Onglet Alertes (compte reel) + notification sur le telephone."""
    from gold_bot.notifiers import AlluxeBotChannel, FirebasePushChannel, Notifier
    notifier = Notifier([AlluxeBotChannel(compte="reel"), FirebasePushChannel()])
    envoyer = notifier.critical if a.niveau == "critical" else notifier.warning
    envoyer(f"Agent : {a.titre}", a.corps)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(RACINE))
    os.chdir(RACINE)
    from gold_bot.env import charger_env
    charger_env()
    for a in Veille(lambda a: None).passer():
        print(f"[{a.niveau}] {a.titre} -- {a.corps}")
    print("veille passee")
