#!/usr/bin/env python3
"""Ce que le robot fait REELLEMENT, en une commande.

Ecrit parce que la question « est-ce que tout roule ? » n'a pas de reponse
utile depuis un terminal : il faut lire la version deployee, la
configuration en service, le regime tarifaire du jour, et l'etat du
processus — quatre endroits differents. Ici tout est au meme endroit, et
chaque ligne dit si c'est normal ou pas.

    python3 etat.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.calibrage import COUT_INCOMPRESSIBLE, calibrer, duree_stop_temporel
from gold_bot.promotion import Promotion
from gold_bot.runtime_context import instance_key, runtime_report
from gold_bot.settings import BotConfig
from gold_bot.state import TradeJournal, ancrer
from gold_bot.universe import Universe

VERT, ROUGE, JAUNE, GRIS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"
CONFIG = os.getenv("GB_CONFIG", "robot.bitvavo.json")


def ligne(etiquette: str, valeur: str, etat: str = "", note: str = "") -> None:
    couleur = {"ok": VERT, "non": ROUGE, "attention": JAUNE}.get(etat, "")
    marque = {"ok": "OK ", "non": "NON", "attention": " ! "}.get(etat, "   ")
    # Le code de fin ne s'ecrit que s'il y a une couleur a fermer : sinon il
    # s'affiche tel quel sur les terminaux qui ne les interpretent pas.
    prefixe = f"{couleur}{marque}{FIN}" if couleur else marque
    suffixe = f"  {GRIS}{note}{FIN}" if note else ""
    print(f"  {prefixe} {etiquette:<26} {valeur}{suffixe}")


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.abspath(__file__)),
                              timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def titre(texte: str) -> None:
    print(f"\n{texte}\n" + "-" * 66)


def universe_lookup(symbole: str):
    try:
        return Universe().get(symbole)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    print("=" * 66)
    print("  ETAT DU ROBOT")
    print("=" * 66)

    # ---------------------------------------------------------- version
    titre("Version deployee")
    local = git("rev-parse", "--short", "HEAD")
    sujet = git("log", "-1", "--format=%s")
    git("fetch", "--quiet", "origin", git("rev-parse", "--abbrev-ref", "HEAD"))
    retard = git("rev-list", "--count", "HEAD..@{u}") or "0"
    ligne("commit", f"{local}  {sujet[:40]}")
    if retard.isdigit() and int(retard) > 0:
        ligne("a jour", f"{retard} commit(s) de retard", "attention",
              "git pull && sudo ./service.sh demarrer")
    else:
        ligne("a jour", "oui", "ok")

    # ---------------------------------------------------------- service
    titre("Processus")
    actif = subprocess.run(["pgrep", "-f", "run_bot.py run"],
                           capture_output=True).returncode == 0
    ligne("robot en marche", "oui" if actif else "NON", "ok" if actif else "non",
          "" if actif else "sudo ./service.sh demarrer")

    # ------------------------------------------------------ configuration
    cfg = BotConfig.load(CONFIG)
    cle = instance_key(cfg)
    contexte = runtime_report(cfg)
    titre(f"Configuration ({CONFIG})")
    reel = not cfg.engine.dry_run
    ligne("mode", "ARGENT REEL" if reel else "simulation",
          "attention" if reel else "ok")
    ligne("lieu d'execution", cfg.engine.broker)
    ligne("instance", cle)
    ligne("source chargee", cfg.source_path or CONFIG)
    ligne("repertoire courant", contexte["cwd"])

    levier_ok = cfg.risk.max_leverage <= 1.0
    ligne("levier", f"{cfg.risk.max_leverage:g}x", "ok" if levier_ok else "non",
          "" if levier_ok else "decision de l'operateur : 1x (voir CLAUDE.md)")

    plafond = cfg.risk.max_cost_ratio_pct
    plafond_ok = plafond <= 15.0
    ligne("plafond de cout", f"{plafond:g} %", "ok" if plafond_ok else "non",
          "" if plafond_ok else "decision de l'operateur : 15 % (voir CLAUDE.md)")

    # ---------------------------------------------------------- tarif
    titre("Regime tarifaire")
    promo = Promotion.depuis_config(cfg.promotion)
    aujourd_hui = dt.date.today()
    en_cours = promo.en_cours(aujourd_hui)
    frais = promo.frais_effectifs(0.0025, aujourd_hui)
    if not promo.active:
        ligne("fenetre sans frais", "aucune declaree", "attention",
              "rien ne ramenera le robot au D1 automatiquement")
    elif en_cours:
        ligne("fenetre sans frais", f"en cours jusqu'au {promo.fin}", "ok",
              f"{promo.jours_restants(aujourd_hui)} jour(s) restant(s)")
    else:
        ligne("fenetre sans frais", f"terminee le {promo.fin}", "ok",
              "tarif normal revenu automatiquement")
    ligne("frais retenus", f"{frais * 100:.2f} % par cote")

    # ------------------------------------------------------- calibrage
    titre("Ce que le capital permet")
    cal = calibrer(equity=cfg.engine.start_balance, ticket_minimum=5.0,
                   frais_par_cote=frais,
                   risk_pct_demande=cfg.risk.base_risk_pct,
                   risk_pct_max=cfg.risk.max_risk_pct,
                   plafond_cout_pct=cfg.risk.max_cost_ratio_pct,
                   plafond_positions=cfg.risk.max_positions,
                   part_engageable_pct=cfg.risk.max_capital_engaged_pct)
    unite = cal.unite_conseillee or cfg.strategy.entry_tf
    ligne("unites tenables", ", ".join(cal.unites) or "AUCUNE",
          "ok" if cal.unites else "non")
    ligne("unite retenue", unite)

    delai = duree_stop_temporel(cfg.strategy.entry_tf,
                                cfg.trade.time_stop_minutes, unite)
    ligne("stop temporel", f"{delai / 1440:.1f} jour(s)" if delai >= 1440
          else f"{delai:.0f} min")

    stop_pct = {"M1": .0013, "M3": .0022, "M5": .0042, "M15": .0077,
                "M30": .011, "H1": .0154, "H4": .0308, "D1": .06}.get(unite)
    if stop_pct:
        cout_r = (2 * frais + COUT_INCOMPRESSIBLE) / stop_pct
        tp = cfg.trade.tp_r_multiple
        seuil = (1 + cout_r) / ((tp - cout_r) + (1 + cout_r)) * 100
        ligne("cout par trade", f"{cout_r:.2f} R")
        ligne("reussite necessaire", f"{seuil:.1f} %",
              "ok" if seuil < 45 else "attention",
              "pour seulement rentrer dans ses frais")

    # ------------------------------------------------- positions ouvertes
    #
    # « Il ne fait plus rien depuis trois heures » : en D1 c'est souvent
    # qu'il TIENT, pas qu'il dort. Sans voir ce qu'il detient ni ce qui le
    # bloque, l'attente normale et la panne se ressemblent.
    from gold_bot.state import StateStore
    store = StateStore(instance=cle)
    store.load()
    etat = store.state
    ouvertes = [store.position_memorisee(i) for i in etat.position_meta]
    ouvertes = [p for p in ouvertes if p is not None]

    titre("Positions tenues")
    if etat.halted:
        ligne("robot en securite", etat.halt_reason[:44] or "oui", "non",
              "il ne prendra plus rien tant que ce n'est pas leve")
    if not ouvertes:
        ligne("positions", "aucune", "", "il cherche")
    else:
        groupes = set()
        for pos in ouvertes:
            age = (time.time() - pos.opened_at) / 3600.0
            inst = universe_lookup(pos.symbol)
            groupe = getattr(inst, "correlation_group", "") if inst else ""
            groupes.add(groupe)
            ligne(pos.symbol,
                  f"{pos.volume:.6g} @ {pos.entry_price:.6g}",
                  "", f"depuis {age:.0f} h — stop {pos.stop_loss:.6g} "
                      f"objectif {pos.take_profit:.6g}")
        plein = len(ouvertes) >= cfg.risk.max_positions
        ligne("places occupees", f"{len(ouvertes)} / {cfg.risk.max_positions}",
              "attention" if plein else "ok",
              "plus aucune ouverture possible" if plein else "")
        if cfg.risk.max_per_correlation_group == 1 and groupes:
            ligne("groupes pris", ", ".join(sorted(g for g in groupes if g)) or "-",
                  "", "un seul actif par groupe correle")

    # --------------------------------------------------------- resultats
    titre("Resultats reels")
    journal = TradeJournal(instance=cle)
    stats = journal.stats()
    # Le chemin est affiche systematiquement : le journal retombe sur le
    # fichier commun quand le fichier suffixe n'existe pas, et se tromper
    # de nom fait archiver ou lire le mauvais historique.
    ligne("journal", journal.path.replace(os.path.expanduser("~"), "~"))
    if not stats.get("trades"):
        ligne("trades enregistres", "aucun", "attention")
    else:
        ligne("trades", str(stats["trades"]))
        ligne("reussite", f"{stats['taux_reussite_pct']:.1f} %")
        ligne("resultat net", f"{stats['profit_net']:+.2f} {cfg.engine.currency}",
              "ok" if stats["profit_net"] >= 0 else "attention")
        ligne("esperance", f"{stats['esperance_R']:+.3f} R")
        porte = stats.get("objectif_median_atteint_R")
        if porte:
            ligne("objectif median atteint", f"{porte:.2f} R",
                  "attention" if porte < cfg.trade.tp_r_multiple * .75 else "ok",
                  f"objectif vise : {cfg.trade.tp_r_multiple:.2f} R")

    print("\n" + "=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
