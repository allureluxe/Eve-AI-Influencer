"""IBKR adapter hardened for a long-running VPS bot."""
from __future__ import annotations

import logging
import os
import time

from .ibkr import IBKRBroker

logger = logging.getLogger(__name__)


class HardenedIBKRBroker(IBKRBroker):
    """IBKR broker with live Gateway defaults and automatic reconnect."""

    def __init__(self) -> None:
        super().__init__()
        # IB Gateway: 4001 live, 4002 paper. Keep an explicit env override.
        if "IBKR_PORT" not in os.environ:
            self.port = 4001
        self._reconnecting = False

    def _reconnect(self) -> bool:
        if self._reconnecting:
            return False
        self._reconnecting = True
        try:
            for attempt in range(1, 6):
                try:
                    if self.ib is not None:
                        try:
                            self.ib.disconnect()
                        except Exception:
                            pass
                    self.ib = None
                    logger.warning("IBKR: reconnexion Gateway %s/%s sur %s:%s",
                                   attempt, 5, self.host, self.port)
                    super().connect()
                    logger.info("IBKR: connexion Gateway retablie")
                    return True
                except Exception as exc:
                    logger.warning("IBKR: reconnexion %s echouee: %s", attempt, str(exc)[:180])
                    time.sleep(min(2.0 * attempt, 10.0))
            return False
        finally:
            self._reconnecting = False

    def sync(self) -> None:
        if self.ib is None or not self.ib.isConnected():
            if not self._reconnect():
                raise RuntimeError("IBKR Gateway non connecte apres 5 tentatives")
        try:
            return super().sync()
        except Exception as exc:
            logger.warning("IBKR: synchronisation echouee (%s), reconnexion...", str(exc)[:180])
            if self._reconnect():
                return super().sync()
            raise

    def connect(self) -> bool:
        # The base adapter uses 4002 as its historical default; live Gateway is 4001.
        if "IBKR_PORT" not in os.environ:
            self.port = 4001
        return super().connect()

    def healthy(self) -> bool:
        return bool(self.ib and self.ib.isConnected())
