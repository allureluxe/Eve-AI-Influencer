#!/usr/bin/env python3
"""Lance le moteur de scalping multi-entrees.

Usage:
  python3 run_dual_scalping.py --config robot.bitvavo.json
  python3 run_dual_scalping.py --config robot.ibkr.json
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.dual_scalping_engine import DualScalpingEngine
from gold_bot.settings import BotConfig


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-24s %(message)s",
        datefmt="%H:%M:%S",
    )
    cfg = BotConfig.load(args.config)
    if args.dry_run:
        cfg.engine.dry_run = True
    problems = cfg.validate()
    if problems:
        for pmsg in problems:
            logging.error("configuration : %s", pmsg)
        return 2
    engine = DualScalpingEngine(cfg)
    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
