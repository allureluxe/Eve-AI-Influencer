#!/usr/bin/env python3
"""Compare plusieurs strategies sur l'historique, et les classe.

POURQUOI CET OUTIL EXISTE

Pendant deux jours, les reglages ont ete essayes EN ARGENT REEL : chaque
essai coutait des euros, prenait des heures, et ne donnait qu'un seul
echantillon. Le 28 aout au soir : 72 trades, 2,8 % de reussite, aucune
position fermee en positif.

Le moteur de rejeu du projet permet de faire l'inverse — essayer vingt
configurations en quelques minutes, sur des annees d'historique, sans
engager un centime. C'est la seule facon honnete de repondre a « est-ce
que ce systeme fonctionne ? ».

CE QUE CET OUTIL DIT, ET CE QU'IL NE DIT PAS

Il mesure ce qu'une configuration AURAIT fait sur le passe. Il ne promet
rien sur l'avenir. Un backtest ne reproduit ni les elargissements de
spread sur annonce, ni le glissement reel, ni les ordres refuses — il est
donc toujours un peu plus optimiste que la realite.

Une regle a ne pas oublier : sous 30 trades, un resultat ne veut rien
dire. L'outil le signale au lieu de laisser croire a une decouverte.

    python3 comparer.py                       les variantes livrees
    python3 comparer.py --bars 2000           plus d'historique
    python3 comparer.py --symbols BTCUSD,ETHUSD,SOLUSD
"""
from __future__ import annotations

import argparse
import copy
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.env import charger_env
from gold_bot.settings import BotConfig

# Les cles des sources de prix (TWELVEDATA_API_KEY, etc.) et la devise de
# cotation vivent dans le .env : sans lui, le rejeu tourne sur les seules
# sources gratuites et ne mesure pas la meme chose que le robot.
charger_env()

from gold_bot.backtest import Backtester  # noqa: E402

# Les cryptos les plus liquides de l'univers : spreads les plus serres,
# donc le terrain le PLUS favorable. Ce qui echoue ici echouera partout.
SYMBOLES = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD",
            "AVAXUSD", "LINKUSD", "DOTUSD"]

MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def variante(nom: str, **reglages) -> tuple[str, dict]:
    return nom, reglages


# --------------------------------------------------------------------------
# LES CANDIDATES
# --------------------------------------------------------------------------
# Deux familles, et une raison de les opposer.
#
# 1. SUIVI DE TENDANCE LENT. C'est la seule approche crypto qui dispose de
#    preuves publiees serieuses : le momentum de serie temporelle. La
#    litterature converge sur des horizons LONGS — un travail de reference
#    trouve son optimum a 28 jours de lecture pour 5 jours de detention,
#    avec un Sharpe de 1,51 contre 0,84 pour l'achat simple. Traduit ici :
#    entree en D1 ou H4, tendance ponderee lourd, pas de contre-tendance,
#    accord entre unites de temps exige, stop large, objectif lointain.
#
#    Le tarif Bitvavo pousse dans le meme sens : a 0,60 % l'aller-retour,
#    les frais valent 33 % du risque en H1 et 10 % en D1. Les deux
#    raisonnements — la preuve et l'arithmetique — designent le meme
#    endroit, ce qui est rare et vaut d'etre teste.
#
# 2. RAPIDE ET NOMBREUX. Ce que l'operateur veut : beaucoup de trades. On
#    ne l'ecarte pas par principe, on le MESURE. Si le H1 ou le M30 tient
#    face aux frais sur l'historique, tant mieux ; s'il perd, le rejeu le
#    dira en quelques minutes au lieu de plusieurs jours d'argent reel.
#
# La question n'est pas « laquelle est la meilleure en theorie » mais
# « laquelle a une esperance positive APRES frais, sur assez de trades
# pour que ca veuille dire quelque chose ».

TENDANCE = dict(
    mode="quorum", min_confirmations=3, require_candle_confirmation=False,
    require_mtf_alignment=True, allow_counter_trend=False,
    min_adx=20.0, min_rr=1.8,
    w_trend=0.30, w_momentum=0.24, w_candles=0.10, w_chart=0.08,
    w_divergence=0.06, w_zones=0.06, w_volume=0.06, w_macro=0.05, w_news=0.05,
)

D1 = dict(entry_tf="D1", trigger_tf="H4", context_tf="D1", bias_tf="D1")
H4 = dict(entry_tf="H4", trigger_tf="H1", context_tf="D1", bias_tf="D1")
H1 = dict(entry_tf="H1", trigger_tf="M15", context_tf="H4", bias_tf="H4")
M30 = dict(entry_tf="M30", trigger_tf="M15", context_tf="H1", bias_tf="H4")

VARIANTES = [
    # --- Famille 1 : suivi de tendance, du plus lent au plus rapide ---
    variante("D1 tendance — objectif 3R", **D1, **TENDANCE,
             plafond_cout=15.0, atr_stop_mult=1.5, tp_r_multiple=3.0),
    variante("D1 tendance — objectif 2R", **D1, **TENDANCE,
             plafond_cout=15.0, atr_stop_mult=1.5, tp_r_multiple=2.0),
    variante("H4 tendance — objectif 3R", **H4, **TENDANCE,
             plafond_cout=20.0, atr_stop_mult=1.5, tp_r_multiple=3.0),
    variante("H4 tendance — objectif 2R", **H4, **TENDANCE,
             plafond_cout=20.0, atr_stop_mult=1.5, tp_r_multiple=2.0),
    variante("H1 tendance — objectif 2R", **H1, **TENDANCE,
             plafond_cout=35.0, atr_stop_mult=1.6, tp_r_multiple=2.0),

    # --- Famille 2 : rapide et nombreux, ce que l'operateur demande ---
    # Sans aucun override : cette ligne suit la configuration EN SERVICE,
    # quelle qu'elle soit. Elle s'appelait « H1 en service » et est restee
    # ainsi apres le passage au M30 : elle affichait alors des resultats
    # identiques a la variante M30, ce qui ressemblait a un bug alors que
    # c'etait le meme reglage teste deux fois. Un libelle qui nomme un
    # reglage plutot que son role finit toujours par mentir.
    variante("configuration en service (temoin)"),
    variante("H1 — contre-tendance permise", **H1, allow_counter_trend=True,
             require_mtf_alignment=False, min_confirmations=2),
    variante("H1 — objectif court 1,3R", **H1, tp_r_multiple=1.3, min_rr=1.2),
    variante("M30 — plafond desserre a 50 %", **M30, plafond_cout=50.0,
             atr_stop_mult=1.6, tp_r_multiple=2.0),

    # --- Temoins : est-ce que chaque barriere sert a quelque chose ? ---
    # Une barriere qui n'ameliore rien coute des trades pour rien ; une
    # barriere dont le retrait ameliore le resultat n'etait pas une
    # protection, c'etait un frein.
    variante("H4 tendance SANS accord multi-unites", **H4, **{
        **TENDANCE, "require_mtf_alignment": False},
        plafond_cout=20.0, atr_stop_mult=1.5, tp_r_multiple=3.0),
    variante("H4 tendance SANS filtre ADX", **H4, **{
        **TENDANCE, "min_adx": 0.0},
        plafond_cout=20.0, atr_stop_mult=1.5, tp_r_multiple=3.0),
    variante("H4 tendance — stop large 2,2 ATR", **H4, **TENDANCE,
             plafond_cout=20.0, atr_stop_mult=2.2, tp_r_multiple=3.0),
]


def config_pour(base: BotConfig, reglages: dict) -> BotConfig:
    cfg = copy.deepcopy(base)
    for cle, valeur in reglages.items():
        # Le plafond de cout vit dans trois sections et doit rester
        # coherent : le desaccorder ferait filtrer a un endroit ce qu'un
        # autre laisse passer.
        if cle == "plafond_cout":
            cfg.risk.max_cost_ratio_pct = valeur
            cfg.strategy.max_cost_ratio_pct = valeur
            cfg.trade.max_cost_ratio_pct = valeur
            continue
        if cle == "risque_pct":
            cfg.risk.base_risk_pct = valeur
            continue
        # `min_rr` existe dans DEUX sections et les deux comptent : la
        # strategie s'en sert pour filtrer, le dimensionnement pour
        # refuser. N'en regler qu'une laissait passer au second ce que le
        # premier venait d'ecarter.
        if cle == "min_rr":
            cfg.strategy.min_rr = valeur
            cfg.risk.min_rr = valeur
            continue
        cible = cfg.trade if hasattr(cfg.trade, cle) else cfg.strategy
        setattr(cible, cle, valeur)

    # Le stop temporel doit suivre l'unite de temps, sinon on compare une
    # strategie D1 a qui on laisse douze heures pour se former. La variante
    # garde la main si elle l'a fixe explicitement.
    if "time_stop_minutes" not in reglages:
        depart = MINUTES.get(base.strategy.entry_tf, 60)
        arrivee = MINUTES.get(cfg.strategy.entry_tf, depart)
        cfg.trade.time_stop_minutes = base.trade.time_stop_minutes / depart * arrivee

    # L'objectif ne peut pas etre sous le ratio minimal exige : la
    # configuration serait rejetee, et la variante ne mesurerait rien.
    if cfg.trade.tp_r_multiple < cfg.risk.min_rr:
        cfg.risk.min_rr = cfg.strategy.min_rr = cfg.trade.tp_r_multiple

    # Meme regle de coherence que dans BotConfig.validate() : un filtre de
    # spread plus permissif que le plafond de cout laisserait entrer ce que
    # le dimensionnement refusera ensuite, et la variante compterait des
    # occasions qu'elle ne peut pas prendre.
    plafond_en_r = cfg.risk.max_cost_ratio_pct / 100.0
    cfg.strategy.max_spread_atr_ratio = min(
        cfg.strategy.max_spread_atr_ratio, plafond_en_r * cfg.trade.atr_stop_mult)
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="robot.bitvavo.json")
    ap.add_argument("--bars", type=int, default=1500)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--capital", type=float, default=186.0)
    ap.add_argument("--spread-x", type=float, default=1.0,
                    help="multiplie le spread suppose : 1 = modele, 3 = pessimiste")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--long-seulement", action="store_true", dest="long_seulement",
                    help="ignorer les ventes a decouvert : ce que donnerait "
                         "la strategie sur un compte au comptant")
    ap.add_argument("--hors-ligne", action="store_true", dest="hors_ligne",
                    help="donnees SYNTHETIQUES : verifie que le banc d'essai "
                         "tourne, ne dit rien d'une strategie")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s %(message)s")
    if not args.verbose:
        logging.getLogger("gold_bot").setLevel(logging.ERROR)

    # LE SPREAD EST LE POINT FAIBLE DU REJEU.
    #
    # Le modele suppose 0,05 % du prix pour toutes les cryptos. Les
    # journaux du 28 aout montrent des spreads reels de 2 a 20 % de l'ATR,
    # soit 0,06 a 1,2 % du prix selon l'instrument : le modele est juste
    # sur les plus liquides et beaucoup trop optimiste ailleurs.
    #
    # Un avantage qui disparait quand on double le spread n'est pas un
    # avantage, c'est une hypothese. Ce reglage permet de le verifier.
    if args.spread_x != 1.0:
        import gold_bot.backtest as _bt
        _origine = _bt.spread_estime
        _bt.spread_estime = lambda inst, prix: _origine(inst, prix) * args.spread_x

    base = BotConfig.load(args.config)
    symboles = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
                or SYMBOLES)

    registre = None
    if args.hors_ligne:
        # On passe par registre_pour() et non par le constructeur de bas
        # niveau : c'est le point de construction UNIQUE du projet, celui
        # qui porte le verrou de devise. Il a deja ete contourne deux fois,
        # et chaque oubli donnait des prix en dollars pour des ordres en
        # euros, sans la moindre erreur. Le mode hors ligne se demande donc
        # par la configuration, pas par un appel direct.
        from gold_bot.engine import registre_pour
        hors_ligne = copy.deepcopy(base)
        hors_ligne.engine.offline = True
        registre = registre_pour(hors_ligne)
        print("\n  !! DONNEES SYNTHETIQUES !!  Ce mode verifie que le banc")
        print("     d'essai fonctionne. Les resultats ne disent RIEN d'une")
        print("     strategie : le hasard n'a pas de tendance a suivre.\n")

    print("=" * 78)
    print(f"  COMPARAISON DE STRATEGIES — {len(symboles)} instruments, "
          f"{args.bars} bougies, capital {args.capital:.0f} EUR")
    print("=" * 78)
    print(f"  Frais supposes : {base.risk.commission_pct*100:.2f} % par cote "
          f"(tarif normal, hors promotion)")
    print(f"  Spread suppose : modele x{args.spread_x:g}"
          + ("   <- test de robustesse" if args.spread_x != 1.0 else ""))
    print(f"  Sens autorises : "
          + ("ACHAT SEUL (compte au comptant)" if args.long_seulement
             else "achat ET vente a decouvert (compte de marge)"))
    print("  Chaque variante ne change qu'une chose par rapport a la config en service.")
    print(f"  Instruments : {', '.join(symboles)}\n")

    resultats = []
    for nom, reglages in VARIANTES:
        cfg = config_pour(base, reglages)
        debut = time.time()
        trades, gagnants, somme_r, profit, dd = 0, 0, 0.0, 0.0, 0.0
        echecs = []
        for sym in symboles:
            try:
                res = Backtester(
                    cfg, registry=registre,
                    autorise_vente=(None if not args.long_seulement else False),
                ).run(sym, bars=args.bars, start_balance=args.capital)
            except Exception as exc:  # noqa: BLE001
                echecs.append(f"{sym}: {str(exc)[:40]}")
                continue
            reels = [t for t in res.trades if not t.partial]
            trades += len(reels)
            gagnants += sum(1 for t in reels if t.profit > 0)
            somme_r += sum(t.r_multiple for t in reels)
            profit += res.end_balance - res.start_balance
            dd = max(dd, res.stats().get("drawdown_max", 0.0) or 0.0)
        resultats.append({
            "nom": nom, "trades": trades, "gagnants": gagnants,
            "reussite": gagnants / trades * 100 if trades else 0.0,
            "esperance": somme_r / trades if trades else 0.0,
            "profit": profit, "drawdown": dd,
            "secondes": time.time() - debut, "echecs": echecs,
        })
        etat = f"{trades:>4} trades" if trades else " aucun trade"
        print(f"  {nom:<34} {etat}   {time.time()-debut:>5.0f}s")

    resultats.sort(key=lambda r: (r["esperance"], r["profit"]), reverse=True)

    print("\n" + "=" * 78)
    print("  CLASSEMENT — par esperance en R (le seul chiffre qui se compare)")
    print("=" * 78)
    print(f"  {'variante':<34}{'trades':>7}{'reussite':>10}"
          f"{'esperance':>11}{'profit':>10}{'recul':>9}")
    for r in resultats:
        fiable = "" if r["trades"] >= 30 else "  (trop peu)"
        print(f"  {r['nom']:<34}{r['trades']:>7}{r['reussite']:>9.1f}%"
              f"{r['esperance']:>+11.3f}{r['profit']:>+10.2f}"
              f"{-r['drawdown']:>9.2f}{fiable}")

    solides = [r for r in resultats if r["trades"] >= 30]
    print("\n" + "-" * 78)
    if not solides:
        print("  Aucune variante n'atteint 30 trades : rien de concluant.")
        print("  Relance avec --bars 4000, ou avec plus d'instruments.")
    else:
        best = solides[0]
        print(f"  Meilleure sur {best['trades']} trades : {best['nom']}")
        print(f"     esperance {best['esperance']:+.3f} R par trade, "
              f"reussite {best['reussite']:.1f} %")
        if best["esperance"] <= 0:
            print("\n  AUCUNE VARIANTE N'EST GAGNANTE SUR L'HISTORIQUE.")
            print("  Ce n'est pas un reglage a corriger : c'est la strategie")
            print("  elle-meme qui ne trouve pas d'avantage sur ces marches.")
            print("  NE PAS armer en reel. Relancer avec --bars 4000 et plus")
            print("  d'instruments avant de conclure, puis s'arreter la.")
        else:
            # La gagnante est ECRITE, pas seulement affichee : recopier des
            # reglages a la main depuis un tableau est exactement la facon
            # dont une configuration testee devient une configuration
            # differente de celle qu'on a testee.
            reglages = next(rg for nom, rg in VARIANTES if nom == best["nom"])
            ecrire_candidate(config_pour(base, reglages), best, args)

    for r in resultats:
        if r["echecs"]:
            print(f"\n  {r['nom']} — donnees manquantes : {'; '.join(r['echecs'][:3])}")
    print("=" * 78)
    return 0


def ecrire_candidate(cfg: BotConfig, best: dict, args) -> None:
    """Enregistre la variante gagnante en configuration prete a relire.

    Elle n'est PAS armee : `dry_run` reste vrai. Un rejeu gagnant est une
    raison de regarder de plus pres, jamais une raison d'engager de
    l'argent — le rejeu ignore les elargissements de spread sur annonce,
    le glissement reel et les ordres refuses.
    """
    import dataclasses
    import json

    cfg.engine.dry_run = True
    sections = {}
    for nom in ("engine", "strategy", "risk", "trade", "objectives"):
        section = getattr(cfg, nom, None)
        if section is None:
            continue
        # `vars()` ne marche pas ici : ces sections sont des dataclasses
        # declarees avec slots=True, donc sans __dict__. C'est justement ce
        # qui les rend compactes et sures — on passe donc par les champs
        # declares, seule facon fiable de les enumerer.
        sections[nom] = {champ.name: getattr(section, champ.name)
                         for champ in dataclasses.fields(section)
                         if not champ.name.startswith("_")}
    sections["promotion"] = dict(getattr(cfg, "promotion", {}) or {})
    sections["_note"] = (
        f"Gagnante du rejeu du {time.strftime('%Y-%m-%d')} : « {best['nom']} » — "
        f"{best['trades']} trades, esperance {best['esperance']:+.3f} R, "
        f"reussite {best['reussite']:.1f} %, spread x{args.spread_x:g}. "
        "NON ARMEE : dry_run reste vrai. Verifier en simulation avant "
        "d'engager quoi que ce soit.")

    # Ancre a la racine du depot, comme BotConfig.load() : ecrire dans le
    # repertoire courant produirait un fichier que le chargeur ne trouverait
    # pas si le rejeu a ete lance d'ailleurs.
    from gold_bot.settings import RACINE
    chemin = os.path.join(RACINE, "robot.candidat.json")
    with open(chemin, "w", encoding="utf-8") as f:
        # `default=str` : un champ non serialisable ne doit pas faire perdre
        # le resultat d'un rejeu de dix minutes.
        json.dump(sections, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Configuration gagnante ecrite dans {chemin} (dry_run = true).")
    print(f"  Pour l'essayer sans engager d'argent :")
    print(f"     python3 run_dual_scalping.py --config {chemin}")


if __name__ == "__main__":
    raise SystemExit(main())
