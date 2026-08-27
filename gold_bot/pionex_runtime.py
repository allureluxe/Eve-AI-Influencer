"""Runtime guards for live Pionex Futures execution."""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def prepare_live_environment() -> None:
    """Keep optional integrations from interfering with live execution.

    MoonX and Telegram are opt-in here. Pionex execution does not depend on
    either service, so stale credentials cannot spam the trading journal.
    Set MOONX_ENABLED=1 / TELEGRAM_ENABLED=1 only after the credentials have
    been verified.
    """
    if os.getenv("MOONX_ENABLED", "0").strip().lower() not in {"1", "true", "yes", "oui"}:
        os.environ.pop("MOONX_API_KEY", None)
        os.environ.pop("MOONX_API_URL", None)
    if os.getenv("TELEGRAM_ENABLED", "0").strip().lower() not in {"1", "true", "yes", "oui"}:
        os.environ.pop("TELEGRAM_BOT_TOKEN", None)
        os.environ.pop("TELEGRAM_CHAT_ID", None)


def sync_position_mode(broker) -> str:
    """Read the actual Pionex Futures position mode; never change it."""
    try:
        data = broker._private("GET", "/uapi/v1/account/positionMode")
        mode = str(data.get("data", {}).get("positionMode", "")).upper()
        if mode in {"BUYSELL", "OPENCLOSE"}:
            broker.config.position_mode = mode
            logger.info("Pionex position mode detecte : %s", mode)
            return mode
    except Exception as exc:  # noqa: BLE001
        logger.warning("Pionex position mode non detecte : %s", str(exc)[:180])
    return broker.config.position_mode
