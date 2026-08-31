#!/usr/bin/env python3
"""Chien de garde : arrete le robot si le capital passe sous un plancher dur.

Pose le 31 aout, a la demande de l'operateur. Les coupe-circuits internes
du bot sont laches pour un petit compte (drawdown -25 %, et la perte
journaliere -4 % est remise a zero a chaque redemarrage). Ce script est
INDEPENDANT du bot et de toute session : il tourne via cron toutes les
5 min, lit le solde reel chez Bitvavo, et coupe le service si la perte
depuis le pic depasse la limite.

  PIC de reference : 97.35 EUR (maximum historique au 31 aout)
  LIMITE           : 10 EUR de perte  ->  plancher 87.35 EUR

Quand il declenche : `systemctl stop robot-dual-live`, puis il pose un
fichier temoin et NE REDEMARRE JAMAIS le bot tout seul. Retirer le
fichier temoin (data/CHIEN_DE_GARDE_DECLENCHE) et redemarrer a la main
apres avoir compris ce qui s'est passe.

Lecture d'equite impossible (API Bitvavo injoignable) => AUCUNE ACTION.
On ne coupe jamais sur une donnee manquante.
"""
from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys
from dataclasses import replace

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

PIC_EUR = 97.35
LIMITE_PERTE_EUR = 10.0
# Plancher = pic - limite. Surchargeable par CHIEN_PLANCHER_EUR (reglage
# a chaud sans toucher au code, et test du declenchement).
PLANCHER_EUR = float(os.environ.get("CHIEN_PLANCHER_EUR", PIC_EUR - LIMITE_PERTE_EUR))

SERVICE = "robot-dual-live"
TEMOIN = os.path.join(RACINE, "data", "CHIEN_DE_GARDE_DECLENCHE")
JOURNAL = os.path.join(RACINE, "data", "chien_de_garde.log")


def _log(ligne: str) -> None:
    horo = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    texte = f"{horo}  {ligne}\n"
    try:
        # Cap simple : on garde les 1000 dernieres lignes.
        lignes = []
        if os.path.exists(JOURNAL):
            with open(JOURNAL, "r", encoding="utf-8") as f:
                lignes = f.readlines()
        lignes.append(texte)
        if len(lignes) > 1000:
            lignes = lignes[-1000:]
        with open(JOURNAL, "w", encoding="utf-8") as f:
            f.writelines(lignes)
    except Exception:
        pass
    print(texte, end="")


def _service_actif() -> bool:
    try:
        r = subprocess.run(["systemctl", "is-active", SERVICE],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def _lire_equite() -> float | None:
    try:
        from gold_bot.env import charger_env
        charger_env()
        from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig
        cfg = BitvavoConfig.from_env()
        broker = BitvavoBroker(replace(cfg, dry_run=True))
        if not broker.connect():
            _log(f"lecture equite : connexion Bitvavo refusee "
                 f"({getattr(broker, '_last_error', 'raison inconnue')}) "
                 f"-> AUCUNE ACTION")
            return None
        return float(broker.account().equity)
    except Exception as exc:  # noqa: BLE001
        _log(f"lecture equite impossible : {str(exc)[:160]} -> AUCUNE ACTION")
        return None


def main() -> int:
    if os.path.exists(TEMOIN):
        try:
            quand = open(TEMOIN, encoding="utf-8").read().strip()
        except Exception:
            quand = "?"
        _log(f"deja declenche ({quand}) — robot laisse a l'arret, "
             f"rien a faire. Retirer {os.path.basename(TEMOIN)} pour rearmer.")
        return 0

    equite = _lire_equite()
    if equite is None:
        return 0

    marge = equite - PLANCHER_EUR
    actif = _service_actif()

    if equite <= PLANCHER_EUR:
        _log(f"DECLENCHEMENT : equite {equite:.2f} EUR <= plancher "
             f"{PLANCHER_EUR:.2f} EUR (perte {PIC_EUR - equite:.2f} depuis le pic). "
             f"Arret de {SERVICE}.")
        try:
            r = subprocess.run(["sudo", "-n", "systemctl", "stop", SERVICE],
                               capture_output=True, text=True, timeout=30)
            ok = (r.returncode == 0)
            _log(f"  systemctl stop -> {'OK' if ok else 'ECHEC'} "
                 f"{r.stderr.strip()[:160]}")
        except Exception as exc:  # noqa: BLE001
            _log(f"  systemctl stop a echoue : {str(exc)[:160]}")
        try:
            with open(TEMOIN, "w", encoding="utf-8") as f:
                f.write(_dt.datetime.now(_dt.timezone.utc).strftime(
                    "%Y-%m-%d %H:%M:%S UTC") + f" — equite {equite:.2f} EUR")
        except Exception:
            pass
        return 0

    _log(f"OK : equite {equite:.2f} EUR | plancher {PLANCHER_EUR:.2f} | "
         f"marge {marge:.2f} EUR | service {'actif' if actif else 'ARRETE'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
