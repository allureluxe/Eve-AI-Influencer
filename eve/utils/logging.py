"""Journalisation lisible en console."""
from __future__ import annotations

import logging

from eve.config import settings

_CONFIGURED = False


def setup(level: str | None = None) -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logging.basicConfig(
        level=getattr(logging, (level or settings.log_level).upper(), logging.INFO),
        format="%(asctime)s │ %(levelname)-7s │ %(name)-28s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    _CONFIGURED = True
