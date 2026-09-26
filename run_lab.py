#!/usr/bin/env python3
"""Point d'entree du Strategy Lab. Aucun broker live n'est construit."""
from __future__ import annotations
import argparse, logging
from gold_bot.settings import BotConfig
from gold_bot.lab import StrategyLab

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="robot.demo2.json")
    p.add_argument("--once", action="store_true")
    p.add_argument("--pause", type=int, default=60)
    args = p.parse_args()
    cfg = BotConfig.load(args.config)
    # Garde-fou absolu: le laboratoire est paper-only, meme si on lui
    # donne par erreur un fichier de configuration live.
    cfg.engine.broker = "paper"
    cfg.engine.dry_run = True
    lab = StrategyLab(cfg)
    if args.once:
        lab.cycle()
    else:
        lab.loop(args.pause)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
