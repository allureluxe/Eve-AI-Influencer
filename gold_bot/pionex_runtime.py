"""Runtime guards for live Pionex Futures execution.

Keeps optional/broken notification and market-data integrations from
interfering with execution, and synchronises the broker configuration with
the actual Futures account mode using a read-only API call.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def prepare_live_environment() -> None:
    """Disable known optional integrations unless explicitly enabled.

    MoonX is not required for Pionex execution.  A stale MoonX credential
    must never generate repeated 401s or become a source-selection failure.
    Set MOONX_ENABLED=1 only when its credentials are known-good.
    """
    if os.getenv("MOONX_ENABLED", "0").strip().lower() not in {"1", "true", "yes", "oui"}:
        os.environ.pop("MOONX_API_KEY", None)
        os.environ.pop("MOONX_API_URL", None)


def sync_position_mode(broker) -> str:
    """Read the real Pionex Futures position mode and align the broker.

    This is strictly read-only.  No position mode change is sent to Pionex.
    """
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
