"""Guards for Bitvavo-only operation."""
from __future__ import annotations

ALLOWED_BROKER = "bitvavo"
QUOTE_ASSET = "EUR"


def validate_broker(name: str) -> None:
    if name.lower() != ALLOWED_BROKER:
        raise ValueError(f"Broker interdit: {name}. Bitvavo uniquement.")
