#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os

from gold_bot.settings import BotConfig, charger_env
from gold_bot.dual_scalping_engine import DualScalpingEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    charger_env()
    cfg = BotConfig.load(args.config)
    if cfg.engine.broker == "ibkr":
        os.environ.setdefault("IBKR_TRADING_LIVE", "1")
        os.environ.setdefault("IBKR_HOST", "127.0.0.1")
        os.environ.setdefault("IBKR_PORT", "4001")
        os.environ.setdefault("IBKR_CLIENT_ID", "27")
        os.environ.setdefault("IBKR_ALLOW_SHORT", "1")
    engine = DualScalpingEngine(cfg)
    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
