#!/usr/bin/env python3
"""Chien de garde : arrete le robot si le capital passe sous un plancher dur.

Pose le 31 aout, a la demande de l'operateur. Les coupe-circuits internes
du bot sont laches pour un petit compte (drawdown -25 %, et la perte
journaliere -4 % est remise a zero a chaque redemarrage). Ce script est
INDEPENDANT du bot et de toute session : il tourne via cron toutes les
5 min, lit le solde reel chez Bitvavo, et coupe le service si la perte
depuis le pic depasse la limite.

  PLANCHER = reference x (1 - 24 %). La reference suit les nouveaux
  sommets toute seule, et se recale a la main apres un mouvement d'argent.

  POURQUOI UN POURCENTAGE, ET PLUS UN MONTANT EN EUROS.

  Le 4 septembre l'operateur a retire ~50 EUR. L'equite est passee de
  157 a 107, le plancher est reste a 130, et le robot a ete coupe alors
  que les trades du jour ne faisaient que -3,17 EUR. Le chien de garde
  n'avait pas tort : il protegeait un capital qui n'existait plus.

  Un plancher en euros se perime a chaque virement. Un plancher en
  pourcentage suit le capital. Le 24 % vient de la mesure : simulation
  portefeuille de la strategie sur 6 mois, le recul atteint 24 % du
  capital neuf fois sur dix (38 EUR sur 159), et 33 % au pire.

  UN RETRAIT N'EST PAS RECALE AUTOMATIQUEMENT, ET C'EST VOULU. Une chute
  brutale peut etre un virement — ou un krach qui traverse les stops. Les
  confondre desarmerait la protection au pire moment. Le robot s'arrete
  donc dans les deux cas, et un humain tranche avec `--recaler`.

Quand il declenche : `systemctl stop robot-dual-live`, puis il pose un
fichier temoin et NE REDEMARRE JAMAIS le bot tout seul. Retirer le
fichier temoin (data/CHIEN_DE_GARDE_DECLENCHE) et redemarrer a la main
apres avoir compris ce qui s'est passe.

Lecture d'equite impossible (API Bitvavo injoignable) => AUCUNE ACTION.
On ne coupe jamais sur une donnee manquante.
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os
import subprocess
import sys
from dataclasses import replace

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

PLANCHER_PCT = 0.24        # recul tolere sous la reference
REFERENCE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "data", "chien_de_garde_reference.json")


def _reference(equite: float | None = None) -> float:
    """Capital de reference : le sommet connu, ou l'equite si inconnu."""
    try:
        with open(REFERENCE, encoding="utf-8") as f:
            return float(_json.load(f)["reference"])
    except Exception:  # noqa: BLE001
        return equite or 0.0


def _ecrire_reference(valeur: float, motif: str) -> None:
    try:
        os.makedirs(os.path.dirname(REFERENCE), exist_ok=True)
        with open(REFERENCE, "w", encoding="utf-8") as f:
            _json.dump({"reference": round(valeur, 2), "motif": motif,
                        "quand": _dt.datetime.now(_dt.timezone.utc).isoformat()}, f)
    except Exception:  # noqa: BLE001
        pass

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
    if "--recaler" in sys.argv:
        eq = _lire_equite()
        if eq is None:
            print("equite illisible : rien recale")
            return 1
        _ecrire_reference(eq, "recalage manuel apres mouvement de tresorerie")
        for f in (TEMOIN,):
            if os.path.exists(f):
                os.remove(f)
                _log("temoin retire : le chien de garde est rearme")
        _log(f"RECALAGE : reference -> {eq:.2f} EUR, "
             f"plancher -> {eq * (1 - PLANCHER_PCT):.2f} EUR")
        return 0

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

    # La reference suit les nouveaux sommets toute seule. Elle ne DESCEND
    # jamais sans decision humaine : une baisse peut etre un retrait comme
    # une perte, et les confondre desarmerait la protection.
    ref = _reference(equite)
    if equite > ref:
        _ecrire_reference(equite, "nouveau sommet")
        ref = equite
    PLANCHER_EUR = ref * (1 - PLANCHER_PCT)
    marge = equite - PLANCHER_EUR
    actif = _service_actif()

    if equite <= PLANCHER_EUR:
        _log(f"DECLENCHEMENT : equite {equite:.2f} EUR <= plancher "
             f"{PLANCHER_EUR:.2f} EUR (perte {ref - equite:.2f} depuis la reference "
             f"{ref:.2f}). Si c'est un RETRAIT et non une perte : "
             f"ops/chien_de_garde.py --recaler. "
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
