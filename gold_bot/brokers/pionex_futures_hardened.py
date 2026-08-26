"""Durcissement de l'adaptateur Pionex USDT-M Futures.

La couche hardened garde le broker Futures comme source de compatibilite,
mais confirme les ordres par l'etat reel des positions plutot que par
l'endpoint GET /trade/order. Cela evite les faux refus HTTP 404 observes
sur certaines reponses de l'API Futures apres un ordre market asynchrone.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

from .base import AccountInfo, BrokerError
from .pionex_futures import PionexFuturesBroker


class HardenedPionexFuturesBroker(PionexFuturesBroker):
    """Implementation Pionex Futures utilisee par le service autonome."""

    def __init__(self, config=None) -> None:
        super().__init__(config)
        self._pending_market_orders: dict[str, dict[str, Any]] = {}

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

    def _position_volume(self, symbol: str, position_side: str) -> float:
        """Return the exchange position size for one symbol/side."""
        self._sync_exchange_positions()
        total = 0.0
        for pos in self._positions.values():
            if self.pionex_symbol(pos.symbol) != symbol:
                continue
            exchange_side = "LONG" if pos.side.value == "BUY" else "SHORT"
            if exchange_side == position_side:
                total += max(0.0, float(pos.volume))
        return total

    def _confirm_position_delta(
        self,
        symbol: str,
        position_side: str,
        before: float,
        requested: float,
        opening: bool,
    ) -> float:
        """Confirm the actual position change without querying an order id."""
        if self.config.dry_run:
            return requested
        deadline = time.time() + self.config.order_timeout_seconds
        last = before
        while time.time() < deadline:
            try:
                last = self._position_volume(symbol, position_side)
            except Exception:
                time.sleep(self.config.poll_order_seconds)
                continue

            delta = last - before if opening else before - last
            if delta > 0:
                return delta
            time.sleep(self.config.poll_order_seconds)

        raise BrokerError(
            f"Pionex position non confirmee: {symbol} {position_side}, "
            f"avant={before:.8f}, apres={last:.8f}, demande={requested:.8f}"
        )

    def _order(
        self,
        symbol: str,
        side,
        size: float,
        position_side,
        client_id: str,
        reduce_only: bool = False,
    ) -> str:
        position_side_code = "LONG" if position_side.value == "BUY" else "SHORT"
        opening = side.value == position_side.value
        before = self._position_volume(symbol, position_side_code) if not self.config.dry_run else 0.0

        try:
            order_id = super()._order(
                symbol, side, size, position_side, client_id, reduce_only
            )
        except BrokerError as exc:
            # A POST can be reported as HTTP 404 by the Futures gateway even
            # when the matching market order has already reached the account.
            # Never retry blindly: first inspect the real position delta.
            if self.config.dry_run or "HTTP 404" not in str(exc):
                raise
            try:
                delta = self._confirm_position_delta(
                    symbol, position_side_code, before, size, opening
                )
            except Exception:
                raise exc
            recovered_id = f"RECOVERED-{uuid.uuid4().hex[:16]}"
            self._pending_market_orders[recovered_id] = {
                "filled": delta,
                "symbol": symbol,
                "position_side": position_side_code,
                "before": before,
                "opening": opening,
            }
            return recovered_id

        self._pending_market_orders[order_id] = {
            "filled": size,
            "symbol": symbol,
            "position_side": position_side_code,
            "before": before,
            "opening": opening,
        }
        return order_id

    def _wait_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {}
        pending = self._pending_market_orders.pop(order_id, None)
        if pending is None:
            raise BrokerError(f"Pionex ordre inconnu dans le suivi local: {order_id}")

        delta = self._confirm_position_delta(
            symbol,
            pending["position_side"],
            float(pending["before"]),
            float(pending["filled"]),
            bool(pending["opening"]),
        )
        return {"orderId": order_id, "status": "FILLED", "filledSize": str(delta)}

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
