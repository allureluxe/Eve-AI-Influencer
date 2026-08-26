"""Durcissement de l'adaptateur Pionex USDT-M Futures.

Le broker historique reste la base de compatibilite. Cette couche corrige
les points d'integration qui doivent etre strictement alignes sur la
specification Futures actuelle de Pionex : bookTicker, compte a marge,
confirmation des ordres et validation de la position effectivement ouverte.
"""
from __future__ import annotations

import time
from typing import Any

from .base import AccountInfo, BrokerError
from .pionex_futures import PionexFuturesBroker


class HardenedPionexFuturesBroker(PionexFuturesBroker):
    """Implementation Pionex Futures utilisee par le service autonome."""

    def _book(self, symbol: str) -> tuple[float, float]:
        data = self._public("/api/v1/market/bookTicker", params={"symbol": symbol})
        rows = data.get("data", {}).get("tickers", [])
        if not rows:
            raise BrokerError(f"Pionex aucun bid/ask pour {symbol}")
        row = rows[0]
        try:
            bid = float(row["bidPrice"])
            ask = float(row["askPrice"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BrokerError(f"Pionex bookTicker invalide pour {symbol}: {row}") from exc
        if bid <= 0 or ask <= 0 or ask < bid:
            raise BrokerError(f"Pionex bid/ask incoherent pour {symbol}: bid={bid} ask={ask}")
        return bid, ask

    def _refresh_account(self) -> None:
        data = self._private("GET", "/uapi/v1/account/detail")
        detail = data.get("data", {})
        balances = detail.get("balances", []) or []
        row = next(
            (r for r in balances if str(r.get("coin", "")).upper() == self.config.quote_asset),
            None,
        )
        if row is None:
            raise BrokerError(
                f"Pionex Futures : aucun solde {self.config.quote_asset} dans account/detail"
            )

        assets = float(row.get("assets", row.get("free", 0)) or 0)
        free = float(row.get("free", row.get("available", 0)) or 0)
        available = float(row.get("available", free) or free)
        frozen = float(row.get("frozen", 0) or 0)
        unrealized = float(row.get("unrealizedPnL", 0) or 0)
        initial_margin = float(row.get("totalInitialMargin", 0) or 0)

        equity = assets + unrealized
        if equity < 0:
            raise BrokerError(f"Pionex Futures equity negative: {equity}")

        self._account = AccountInfo(
            equity=equity,
            balance=assets,
            currency=self.config.quote_asset,
            margin_used=initial_margin if initial_margin > 0 else frozen,
            margin_free=available if available >= 0 else free,
            leverage=self.config.leverage,
        )

    def _wait_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {}
        deadline = time.time() + self.config.order_timeout_seconds
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self._private(
                "GET",
                "/uapi/v1/trade/order",
                params={"symbol": symbol, "orderId": order_id},
            ).get("data", {})
            status = str(last.get("status", "")).upper()

            if status in {"CANCELED", "CANCELLED", "REJECTED", "FAILED"}:
                raise BrokerError(
                    f"Pionex ordre {order_id} refuse/annule ({status}): {last}"
                )
            if status in {"FILLED", "CLOSED"}:
                return last
            time.sleep(self.config.poll_order_seconds)

        raise BrokerError(
            f"Pionex ordre {order_id} non confirme apres "
            f"{self.config.order_timeout_seconds:.1f}s: {last}"
        )

    def open_position(self, instrument, side, lots: float, stop_loss: float,
                      take_profit: float, comment: str = ""):
        pos = super().open_position(
            instrument, side, lots, stop_loss, take_profit, comment
        )
        if self.config.dry_run:
            return pos

        actual = [
            p for p in self.positions()
            if p.symbol == instrument.symbol and p.side is side
        ]
        if not actual:
            self._positions.pop(pos.id, None)
            raise BrokerError(
                f"Pionex ordre {pos.broker_ref} confirme mais aucune position "
                f"{instrument.symbol} {side.value} n'est visible"
            )

        exchange_pos = max(actual, key=lambda p: p.volume)
        pos.volume = exchange_pos.volume
        pos.entry_price = exchange_pos.entry_price
        self._positions[pos.id] = pos
        return pos


__all__ = ["HardenedPionexFuturesBroker"]
