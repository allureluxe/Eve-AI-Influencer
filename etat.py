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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.calibrage import (COUT_INCOMPRESSIBLE, calibrer,
                                duree_stop_temporel, stops_typiques_pour)
from gold_bot.notifiers import TelegramChannel
from gold_bot.promotion import Promotion
from gold_bot.settings import BotConfig, charger_env
from gold_bot.state import TradeJournal, ancrer
from gold_bot.capacite import AUCUN_PLAFOND, places_simultanees
from gold_bot.engine import positions_tenables
from gold_bot.risk import RiskManager
from gold_bot.sorties import categorie_de_sortie
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


def capital_connu(etat, cfg) -> tuple[float, str]:
    """Le capital reel du compte, et d'ou vient le chiffre.

    `engine.start_balance` vaut 1000 par defaut et n'est pas renseigne dans
    la configuration en service : s'en servir faisait calculer tout ce
    rapport sur un compte imaginaire dix fois trop gros — et annoncer des
    unites de temps « tenables » que le vrai capital ne tient pas.

    Le robot enregistre le capital du compte a chaque cycle. C'est cette
    valeur qu'on lit, et on dit laquelle a servi.
    """
    if etat.account_reference and etat.account_reference > 0:
        return etat.account_reference, "capital enregistre par le robot"
    if etat.peak_equity and etat.peak_equity > 0:
        return etat.peak_equity, "dernier sommet connu"
    return cfg.engine.start_balance, "AUCUN capital reel connu : valeur par defaut"


def universe_lookup(symbole: str):
    try:
        return Universe().get(symbole)
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    # Les cles vivent dans .env, que seule l'unite systemd injectait : cette
    # commande tournait donc sans, et lisait un compte fictif.
    charger_env()

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
    titre(f"Configuration ({CONFIG})")
    reel = not cfg.engine.dry_run
    ligne("mode", "ARGENT REEL" if reel else "simulation",
          "attention" if reel else "ok")
    ligne("lieu d'execution", cfg.engine.broker)

    levier_ok = cfg.risk.max_leverage <= 1.0
    ligne("levier", f"{cfg.risk.max_leverage:g}x", "ok" if levier_ok else "non",
          "" if levier_ok else "decision de l'operateur : 1x (voir CLAUDE.md)")

    plafond = cfg.risk.max_cost_ratio_pct
    plafond_ok = plafond <= 15.0
    ligne("plafond de cout", f"{plafond:g} %", "ok" if plafond_ok else "non",
          "" if plafond_ok else "decision de l'operateur : 15 % (voir CLAUDE.md)")

    # --------------------------------------------------- notifications
    #
    # Un robot qui ne previent pas est un robot qu'on surveille a l'oeil.
    # Le canal echouait en silence sur un 404 — lisible comme une panne de
    # Telegram alors que c'est le token qui est refuse.
    tg = TelegramChannel()
    souci = tg.diagnostic()
    ligne("alertes Telegram",
          "actives" if not souci else "INACTIVES",
          "ok" if not souci else "non", souci)

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
    from gold_bot.state import StateStore
    store = StateStore(instance=cfg.engine.broker)
    store.load()
    etat = store.state
    capital, provenance = capital_connu(etat, cfg)

    titre("Ce que le capital permet")
    ligne("capital", f"{capital:.2f} {cfg.engine.currency}",
          "attention" if provenance.startswith("AUCUN") else "",
          provenance)
    # Sur quoi ce robot calibre-t-il ? Un stop typique de crypto n'a rien a
    # voir avec un stop typique de forex ; le confondre faisait annoncer
    # des unites de temps « tenables » que le capital ne tient pas.
    classe = Universe().classe_dominante()
    cal = calibrer(equity=capital, ticket_minimum=5.0,
                   frais_par_cote=frais,
                   risk_pct_demande=cfg.risk.base_risk_pct,
                   risk_pct_max=cfg.risk.max_risk_pct,
                   plafond_cout_pct=cfg.risk.max_cost_ratio_pct,
                   plafond_positions=cfg.risk.max_positions,
                   part_engageable_pct=cfg.risk.max_capital_engaged_pct,
                   classe_actif=classe)
    unite = cal.unite_conseillee or cfg.strategy.entry_tf
    ligne("unites tenables", ", ".join(cal.unites) or "AUCUNE",
          "ok" if cal.unites else "non")
    ligne("unite retenue", unite)

    delai = duree_stop_temporel(cfg.strategy.entry_tf,
                                cfg.trade.time_stop_minutes, unite)
    ligne("stop temporel", f"{delai / 1440:.1f} jour(s)" if delai >= 1440
          else f"{delai:.0f} min")

    # Le tableau vient de calibrage.py, il n'est PAS recopie ici : la copie
    # locale avait garde les valeurs du forex quand celles de la crypto ont
    # ete corrigees, et cette commande annoncait un cout par trade calcule
    # sur un stop 30 % trop court.
    stop_pct = stops_typiques_pour(classe).get(unite)
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

    # --------------------------------------------------- capacite
    #
    # « Il prend peu de positions, il y a un truc qui va pas. » C'est
    # verifiable : trois reglages plafonnent le nombre de positions
    # simultanees, et un seul est le plus serre. Sans ce calcul, on
    # desserre au hasard celui qui ne bridait rien.
    titre("Combien de positions le robot peut-il tenir")
    r = cfg.risk
    try:
        univers = Universe()
        symboles = cfg.engine.symbols or univers.symbols()
        groupes = {getattr(univers.get(s), "correlation_group", "")
                   for s in symboles}
        groupes.discard("")
        n_groupes = len(groupes)
    except Exception:  # noqa: BLE001
        symboles, n_groupes = [], 0

    # Le risque par trade reellement applique, echelle anti-martingale
    # comprise : c'est lui qui consomme le budget de risque total, pas la
    # valeur de base affichee dans la configuration.
    #
    # Le capital vient de la meme source que la section « Ce que le capital
    # permet » ci-dessus : `start_balance`. Un chiffre lu deux fois dans ce
    # rapport doit venir du meme endroit, sinon deux sections se
    # contredisent sans qu'on sache laquelle croire.
    reference = etat.account_reference or capital
    risque_par_trade = r.base_risk_pct
    if capital > 0:
        rm = RiskManager(r)
        rm.account.equity = capital
        rm.account.reference_equity = reference
        risque_par_trade, _ = rm.effective_risk_pct()

    # Ce que le ticket minimum de la plateforme laisse tenir : le projet
    # sait deja le calculer, on ne le refait pas ici.
    # On demande le plafond SANS le limiter par `max_positions` : sinon la
    # fonction renvoie `max_positions` lui-meme et la ligne « capital »
    # ferait croire que le capital bride alors qu'elle ne fait que repeter
    # un autre verrou. C'est `places_simultanees` qui compare, pas elle.
    par_capital = 0
    if capital > 0:
        par_capital, _ = positions_tenables(
            capital, 5.0, r.max_capital_engaged_pct, AUCUN_PLAFOND)

    cap = places_simultanees(
        max_positions=r.max_positions,
        max_par_groupe=r.max_per_correlation_group,
        n_groupes=n_groupes,
        max_risque_total_pct=r.max_total_risk_pct,
        risque_par_trade_pct=risque_par_trade,
        places_par_capital=par_capital)
    limites, places, bride = cap.limites, cap.places, cap.bride_par

    ligne("instruments scannes", str(len(symboles)),
          "", f"{n_groupes} groupes correles disponibles")
    ligne("risque par trade", f"{risque_par_trade:.2f} %",
          "", f"budget total {r.max_total_risk_pct:.1f} %")
    for nom, v in limites.items():
        serre = nom in bride
        ligne(nom, f"{v} positions", "attention" if serre else "ok",
              "<- c'est LUI qui bride" if serre else "")
    ligne("places simultanees", str(places), "attention" if places <= 3 else "ok",
          f"{len(bride)} verrous a la meme hauteur : en desserrer un seul "
          f"ne changera rien" if cap.plusieurs_verrous else "")

    # --------------------------------------------------------- resultats
    titre("Resultats reels")
    journal = TradeJournal(instance=cfg.engine.broker)
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


    # ------------------------------------------- comment ils se terminent
    #
    # « Toutes mes positions se ferment en stop. » Le motif enregistre est
    # le meme quand le stop d'origine est touche (perte pleine) et quand
    # un stop remonte au break-even ou porte par le trailing est touche
    # (gain verrouille). Les separer est la seule facon de savoir si le
    # robot protege ses gains ou s'il ne gagne jamais.
    from gold_bot.sorties import EXPLICATION, duree_lisible, repartition
    termines = [t for t in journal.trades if not t.partial]
    if termines:
        titre("Comment les trades se sont termines")
        parts = repartition(termines)
        n = len(termines)
        for cat, compte in parts.items():
            if not compte:
                continue
            gains = [t for t in termines
                     if categorie_de_sortie(t.reason, t.r_multiple) == cat]
            r_moyen = sum(t.r_multiple for t in gains) / len(gains)
            ligne(cat, f"{compte:>3}  ({compte/n*100:.0f} %)",
                  "ok" if r_moyen > 0 else "attention",
                  f"{r_moyen:+.2f} R en moyenne — {EXPLICATION[cat]}")
        durees = [(t.closed_at - t.opened_at) / 3600.0 for t in termines
                  if t.closed_at >= t.opened_at]
        if durees:
            durees.sort()
            mediane = durees[len(durees) // 2]
            ligne("duree mediane", duree_lisible(mediane), "",
                  f"stop temporel a {cfg.trade.time_stop_minutes/60:.0f} h")
        # Combien le robot a-t-il rendu au marche ?
        favorable = sum(t.max_favorable_r for t in termines) / n
        realise = sum(t.r_multiple for t in termines) / n
        ligne("monte a / garde", f"{favorable:.2f} R  ->  {realise:+.2f} R",
              "attention" if favorable - realise > 0.5 else "ok",
              f"{favorable - realise:.2f} R rendus au marche")

    print("\n" + "=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
