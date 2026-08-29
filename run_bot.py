#!/usr/bin/env python3
"""Interface en ligne de commande du robot de trading.

    python3 run_bot.py check                 verifie l'installation et les acces
    (les options --config, --broker... s'ecrivent avant ou apres la commande)
    python3 run_bot.py scan                  un balayage unique, sans rien executer
    python3 run_bot.py analyse XAUUSD        analyse detaillee d'un instrument
    python3 run_bot.py backtest XAUUSD       rejeu historique
    python3 run_bot.py objectifs             etat du defi hebdomadaire
    python3 run_bot.py stats                 statistiques des trades realises
    python3 run_bot.py run                   lance le robot en continu (24h/24)

Options utiles :
    --broker paper|bitvavo   lieu d'execution (defaut : paper)
    --dry-run                analyse et journalise sans envoyer d'ordre
    --offline                donnees synthetiques (tests uniquement)
    --symbols XAUUSD,BTCUSD  restreint l'univers
    --config robot.json      fichier de configuration
    --verbose                detail complet des filtres
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.backtest import Backtester
from gold_bot.datasources import build_registry
from gold_bot.engine import TradingEngine, registre_pour
from gold_bot.macro import MacroEngine
from gold_bot.news import NewsFilter
from gold_bot.notifiers import Notifier
from gold_bot.objectives import ObjectiveTracker
from gold_bot.scanner import Scanner
from gold_bot.settings import BotConfig, charger_env
from gold_bot.state import TradeJournal
from gold_bot.strategy import Strategy
from gold_bot.trade_manager import TradeManager
from gold_bot.universe import Universe


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def build_config(args) -> BotConfig:
    # Le .env AVANT la configuration : l'unite systemd l'injecte pour le
    # service, mais une commande lancee a la main n'avait aucune cle. Ce
    # qui est deja defini n'est jamais ecrase — l'environnement du service
    # reste prioritaire.
    charger_env()
    cfg = BotConfig.load(args.config)
    if args.broker:
        cfg.engine.broker = args.broker
    if args.dry_run:
        cfg.engine.dry_run = True
    if args.offline:
        cfg.engine.offline = True
    if args.symbols:
        cfg.engine.symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.balance:
        cfg.engine.start_balance = args.balance
    if args.verbose:
        cfg.engine.verbose_scan = True
    return cfg


# ==========================================================================
def cmd_check(args) -> int:
    """Diagnostic complet : configuration, sources, calendrier, execution."""
    cfg = build_config(args)
    print("=" * 74)
    print("  VERIFICATION DE L'INSTALLATION")
    print("=" * 74)

    problems = cfg.validate()
    print(f"\n[Configuration] {'OK' if not problems else str(len(problems)) + ' probleme(s)'}")
    for p in problems:
        print(f"   - {p}")

    print(f"\n[Univers] {len(Universe())} instruments")
    universe = Universe()
    if cfg.engine.symbols:
        universe.enable_only(cfg.engine.symbols)
    ouverts = universe.tradable()
    print(f"   ouverts maintenant : {', '.join(i.symbol for i in ouverts) or 'aucun'}")

    print("\n[Sources de prix]")
    registry = registre_pour(cfg)
    for src in registry.status():
        mark = "actif " if src["configuree"] else "inactif"
        key = " (cle requise)" if src["cle_requise"] and not src["configuree"] else ""
        print(f"   {mark} {src['source']:<14}{key}")

    print("\n[Test de recuperation]")
    for inst in ouverts[:3]:
        try:
            candles = registry.candles(inst.symbol, inst.asset_class,
                                       cfg.strategy.entry_tf, 120)
            tick = registry.tick(inst.symbol, inst.asset_class)
            print(f"   OK  {inst.symbol:<8} {len(candles)} bougies, "
                  f"dernier prix {candles[-1].close:.5f}"
                  + (f", spread {tick.spread:.5f}" if tick else ""))
        except Exception as exc:
            print(f"   KO  {inst.symbol:<8} {str(exc)[:90]}")

    print("\n[Calendrier economique]")
    news = NewsFilter()
    n = news.refresh(force=True)
    print(f"   {n} evenements charges")
    for ev in news.next_events("metal", 3):
        print(f"   - {ev.when.strftime('%a %d/%m %H:%M')} UTC  {ev.title} ({ev.currency}, {ev.impact})")

    print("\n[Macro]")
    macro = MacroEngine(registry)
    try:
        snap = macro.refresh(force=True)
        bias = macro.bias("XAUUSD", "metal")
        print(f"   biais or : {bias.score:+.2f} ({bias.direction}), fiabilite {bias.confidence:.0%}")
        for d in bias.drivers[:4]:
            print(f"   - {d}")
    except Exception as exc:
        print(f"   indisponible : {str(exc)[:90]}")

    print("\n[Execution]")
    print(f"   broker configure : {cfg.engine.broker}"
          + (" (DRY-RUN)" if cfg.engine.dry_run else ""))
    if cfg.engine.broker == "bitvavo":
        from gold_bot.brokers import BitvavoBroker
        broker = BitvavoBroker()
        print(f"   mode Bitvavo : {getattr(broker, 'mode', 'inconnu')}")
        if broker.connect():
            acc = broker.account()
            print(f"   compte : {acc.equity:.2f} {acc.currency} "
                  f"(disponible {acc.margin_free:.2f})")
        else:
            print("   -> definir BITVAVO_API_KEY et BITVAVO_API_SECRET")

    print("\n[Alertes]")
    print(f"   canaux actifs : {', '.join(Notifier().active_channels())}")

    print("\n[Objectifs]")
    obj = ObjectiveTracker(cfg.objectives)
    st = obj.status()
    print(f"   palier {st['palier']} : {st['objectif_nominal']:.2f} nominal")
    if st["plafonne"]:
        print(f"   -> plafonne a {st['objectif']:.2f} tant que le capital est sous "
              f"{st['capital_requis']:.2f}")
    print("=" * 74)
    return 1 if problems else 0


def cmd_scan(args) -> int:
    """Un balayage complet, sans execution."""
    cfg = build_config(args)
    registry = registre_pour(cfg)
    universe = Universe()
    if cfg.engine.symbols:
        universe.enable_only(cfg.engine.symbols)
    strategy = Strategy(cfg.strategy, TradeManager(cfg.trade), MacroEngine(registry))
    scanner = Scanner(registry, universe, strategy, NewsFilter(), cfg.strategy.history)

    result = scanner.scan()
    for line in scanner.report(result, verbose=args.verbose):
        print(line)
    return 0


def cmd_analyse(args) -> int:
    """Analyse detaillee d'un seul instrument : tous les facteurs, un par un."""
    cfg = build_config(args)
    registry = registre_pour(cfg)
    universe = Universe()
    instrument = universe.get(args.symbol.upper())
    if instrument is None:
        print(f"instrument inconnu : {args.symbol}")
        print(f"disponibles : {', '.join(universe.symbols())}")
        return 2

    strategy = Strategy(cfg.strategy, TradeManager(cfg.trade), MacroEngine(registry))
    scanner = Scanner(registry, universe, strategy, NewsFilter(), cfg.strategy.history)
    ev = scanner.evaluate_symbol(instrument)

    print("=" * 74)
    print(f"  ANALYSE {instrument.symbol} ({instrument.asset_class})")
    print("=" * 74)
    print(f"\n{ev.explain()}\n")
    print("Filtres eliminatoires :")
    for gate in ev.gates:
        print(f"   [{'OK ' if gate.passed else 'NON'}] {gate.name:<22} {gate.detail}")
    if ev.components:
        print("\nScore de confluence :")
        for c in ev.components:
            bar = "#" * int(abs(c.value) * 40)
            print(f"   {c.name:<12} {c.value:+.3f} {bar:<12} {c.detail[:58]}")
        print(f"   {'TOTAL':<12} {ev.score:+.3f}  (seuil {ev.threshold:.3f})")
    if ev.side:
        print(f"\nNiveaux : entree {ev.entry} | SL {ev.stop_loss} | TP {ev.take_profit} "
              f"| ATR {ev.atr:.5f} | RR {ev.rr:.2f}")

    ctx = scanner.context(instrument.symbol)
    ind = ctx.indicators.get(cfg.strategy.entry_tf)
    if ind and ind.ready:
        print(f"\nIndicateurs {cfg.strategy.entry_tf} :")
        print(f"   RSI {ind.rsi.value:.1f} | ADX {ind.adx.value:.1f} | "
              f"ATR {ind.atr.value:.5f} (percentile {ind.atr_percentile():.2f})")
        print(f"   EMA {ind.ema_fast.value:.5f}/{ind.ema_mid.value:.5f}/{ind.ema_slow.value:.5f} | "
              f"supertrend {'haussier' if ind.supertrend.direction > 0 else 'baissier'}")
        print(f"   structure {ind.swings.structure()} | regime {ind.hurst.regime} | "
              f"squeeze {'oui' if ind.squeeze() else 'non'} | biais {ind.trend_bias()}")
    chart = ctx.chart(cfg.strategy.entry_tf, instrument.round_step)
    if chart:
        print(f"\nGraphique : {len(chart.levels)} niveaux, "
              f"{len(chart.divergences)} divergence(s), {len(chart.patterns)} figure(s), "
              f"{len(chart.fvgs)} FVG, {len(chart.order_blocks)} order block(s)")
        if chart.profile:
            print(f"   POC {chart.profile.poc:.5f} | zone de valeur "
                  f"{chart.profile.value_area_low:.5f} - {chart.profile.value_area_high:.5f}")
    print("=" * 74)
    return 0


def cmd_backtest(args) -> int:
    cfg = build_config(args)
    tester = Backtester(cfg)
    symbols = [s.strip().upper() for s in args.symbol.split(",")] if args.symbol else ["XAUUSD"]
    total = 0.0
    for sym in symbols:
        try:
            res = tester.run(sym, bars=args.bars, start_balance=cfg.engine.start_balance)
        except Exception as exc:
            print(f"{sym} : {exc}")
            continue
        stats = res.stats()
        print("=" * 74)
        print(f"  BACKTEST {sym} — {res.bars} bougies {cfg.strategy.entry_tf}, "
              f"capital initial {res.start_balance:.2f}")
        print("=" * 74)
        for k, v in stats.items():
            print(f"   {k:<22} {v}")
        total += stats.get("resultat", 0.0) or 0.0
        if res.trades and args.verbose:
            print("\n   Derniers trades :")
            for t in res.trades[-10:]:
                print(f"     {t.side.value} {t.entry_price} -> {t.exit_price} | "
                      f"{t.profit:+.2f} ({t.r_multiple:+.2f}R) | {t.tp_extensions} ext. | {t.reason}")
    if len(symbols) > 1:
        print(f"\n   RESULTAT CUMULE : {total:+.2f}")
    return 0


def cmd_objectifs(args) -> int:
    cfg = build_config(args)
    tracker = ObjectiveTracker(cfg.objectives)
    equity = args.balance or cfg.engine.start_balance
    st = tracker.status()
    print("=" * 74)
    print("  DEFI HEBDOMADAIRE")
    print("=" * 74)
    print(f"\n   Palier courant : {st['palier']}  (semaine {st['semaine']})")
    print(f"   Objectif nominal : {st['objectif_nominal']:.2f}")
    print(f"   Objectif retenu  : {st['objectif']:.2f}"
          + (f"   [plafonne : le capital doit atteindre {st['capital_requis']:.2f} "
             f"pour viser le nominal]" if st["plafonne"] else ""))
    print(f"   Realise          : {st['realise']:+.2f}  ({st['avancement']:.0%})")
    print(f"   Cadence attendue : {st['cadence_attendue']:.0%} — "
          f"{'en avance' if st['en_avance'] else 'en retard'}")
    mult, why = tracker.risk_multiplier()
    print(f"   Effet sur le risque : x{mult:.2f} — {why}")
    print(f"   Effet sur le seuil  : +{tracker.score_threshold_bonus():.2f}")
    print(f"\n   Prochains paliers (capital de reference {equity:.2f}) :")
    print(f"   {'palier':<8}{'nominal':>12}{'retenu':>12}{'capital requis':>18}")
    for row in tracker.ladder(equity, 8):
        print(f"   {row['palier']:<8}{row['objectif_nominal']:>12.2f}"
              f"{row['objectif_retenu']:>12.2f}{row['capital_requis']:>18.2f}")
    if tracker.state.history:
        print("\n   Historique :")
        for rec in tracker.state.history[-6:]:
            mark = "atteint" if rec["achieved"] else "manque "
            print(f"     {rec['week']}  palier {rec['level']}  "
                  f"{rec['realized']:+.2f}/{rec['target']:.2f}  {mark}")
    print("=" * 74)
    return 0


def cmd_stats(args) -> int:
    # Chaque lieu d'execution tient son propre journal (data/trades-<lieu>.jsonl).
    # Sans lire la configuration, la commande ouvrait le journal commun, vide,
    # et annoncait « aucun trade » alors que le robot en avait enregistre.
    cfg = build_config(args)
    journal = TradeJournal(instance=cfg.engine.broker)
    since = time.time() - args.days * 86400 if args.days else 0.0
    stats = journal.stats(since)
    print("=" * 74)
    print(f"  STATISTIQUES" + (f" — {args.days} derniers jours" if args.days else " — historique complet"))
    print("=" * 74)
    print(f"  journal : {journal.path}")
    if not stats.get("trades"):
        print("\n   Aucun trade enregistre.")
        return 0
    for k, v in stats.items():
        print(f"   {k:<30} {v}")

    # Lecture directe de la question « mon objectif est-il trop haut ? »
    portee = stats.get("objectif_median_atteint_R") or 0.0
    vise = cfg.trade.tp_r_multiple
    if stats.get("trades", 0) >= 5 and portee:
        print(f"\n   Objectif vise : {vise:.2f}R | median reellement atteint : {portee:.2f}R")
        if portee < vise * 0.75:
            print(f"   -> l'objectif est au-dela de ce que la moitie des trades "
                  f"atteint : {vise:.2f}R n'est servi que rarement.")
        elif stats.get("R_favorable_moyen_perdants", 0.0) < 0.3:
            print("   -> les perdants ne progressent presque jamais : le probleme "
                  "est a l'entree, pas a l'objectif.")
        else:
            print("   -> objectif coherent avec ce que le marche donne.")

    per_symbol = journal.by_symbol(since)
    if per_symbol:
        print("\n   Par instrument :")
        print(f"   {'symbole':<10}{'trades':>8}{'reussite':>11}{'profit':>12}{'R cumule':>11}")
        for sym, row in sorted(per_symbol.items(), key=lambda kv: -kv[1]["profit"]):
            print(f"   {sym:<10}{row['trades']:>8}{row['taux_reussite_pct']:>10.1f}%"
                  f"{row['profit']:>12.2f}{row['R']:>11.2f}")
    print("=" * 74)
    return 0


def cmd_run(args) -> int:
    """Lance le robot en continu."""
    cfg = build_config(args)
    try:
        engine = TradingEngine(cfg)
    except ValueError as exc:
        print(f"demarrage impossible : {exc}")
        return 2

    # Tout lieu d'execution qui n'est pas le simulateur engage de l'argent.
    # Ecrite en listant les plateformes, cette condition avait laisse passer
    # Bitvavo — la seule reellement en service : le robot s'armait sans
    # jamais afficher l'avertissement qu'elle existe pour donner.
    if cfg.engine.broker != "paper" and not cfg.engine.dry_run:
        nom = cfg.engine.broker.capitalize()
        print("\n" + "!" * 74)
        print(f"  EXECUTION REELLE : le robot va passer des ordres seul sur {nom}.")
        print("  Coupe-circuits actifs : "
              f"perte journaliere {cfg.risk.daily_loss_limit_pct} %, "
              f"hebdomadaire {cfg.risk.weekly_loss_limit_pct} %, "
              f"drawdown max {cfg.risk.max_drawdown_pct} %.")
        print("  Arret propre : Ctrl+C (les positions restent protegees par leur stop).")
        print("!" * 74 + "\n")

    engine.run()
    return 0


def cmd_status(args) -> int:
    cfg = build_config(args)
    try:
        engine = TradingEngine(cfg)
        engine.start()
        print(json.dumps(engine.status(), indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"etat indisponible : {exc}")
        return 2
    return 0


# ==========================================================================
# Valeurs par defaut des options communes. Elles sont declarees avec
# argparse.SUPPRESS pour pouvoir etre acceptees AVANT comme APRES la
# commande : sans cela, "run_bot.py check --config x.json" echouait, ce qui
# est pourtant la facon la plus naturelle de l'ecrire.
DEFAUTS_COMMUNS = {
    "config": "", "broker": None, "dry_run": False, "offline": False,
    "symbols": "", "balance": 0.0, "verbose": False,
}


def options_communes() -> argparse.ArgumentParser:
    """Options acceptees a n'importe quelle position de la ligne de commande."""
    commun = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    commun.add_argument("--config", help="fichier de configuration JSON")
    commun.add_argument("--broker", choices=["paper", "bitvavo"],
                        help="lieu d'execution")
    commun.add_argument("--dry-run", action="store_true", help="analyser sans envoyer d'ordre")
    commun.add_argument("--offline", action="store_true", help="donnees synthetiques (tests)")
    commun.add_argument("--symbols", help="liste d'instruments, separes par des virgules")
    commun.add_argument("--balance", type=float, help="capital de reference")
    commun.add_argument("--verbose", action="store_true", help="detail complet")
    return commun


def main() -> int:
    commun = options_communes()
    parser = argparse.ArgumentParser(
        description="Robot de trading autonome multi-actifs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__, parents=[commun])

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("check", help="verifier l'installation et les acces", parents=[commun])
    sub.add_parser("scan", help="un balayage unique de l'univers", parents=[commun])
    p = sub.add_parser("analyse", help="analyse detaillee d'un instrument", parents=[commun])
    p.add_argument("symbol")
    p = sub.add_parser("backtest", help="rejeu historique", parents=[commun])
    p.add_argument("symbol", nargs="?", default="XAUUSD")
    p.add_argument("--bars", type=int, default=1500)
    sub.add_parser("objectifs", help="etat du defi hebdomadaire", parents=[commun])
    p = sub.add_parser("stats", help="statistiques des trades", parents=[commun])
    p.add_argument("--days", type=int, default=0)
    sub.add_parser("run", help="lancer le robot en continu", parents=[commun])
    sub.add_parser("status", help="etat courant du robot", parents=[commun])

    args = parser.parse_args()
    for nom, defaut in DEFAUTS_COMMUNS.items():
        if not hasattr(args, nom):
            setattr(args, nom, defaut)
    setup_logging(args.verbose)

    handlers = {
        "check": cmd_check, "scan": cmd_scan, "analyse": cmd_analyse,
        "backtest": cmd_backtest, "objectifs": cmd_objectifs,
        "stats": cmd_stats, "run": cmd_run, "status": cmd_status,
    }
    if not args.command:
        parser.print_help()
        return 0
    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print("\ninterrompu")
        return 130


if __name__ == "__main__":
    sys.exit(main())
