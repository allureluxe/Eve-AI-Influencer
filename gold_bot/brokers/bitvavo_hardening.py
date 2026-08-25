"""Correctifs de compatibilite Bitvavo appliques au broker."""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Any

logger = logging.getLogger(__name__)
_TICKS: dict[str, Decimal] = {}


def _tick_floor(self, prix: float, original):
    """Arrondit au tickSize reel, sinon conserve l'ancien arrondi."""
    if prix <= 0:
        return prix
    tick = _TICKS.get(self.market)
    if tick is None or tick <= 0:
        return original(self, prix)
    value = Decimal(str(prix))
    units = (value / tick).to_integral_value(rounding=ROUND_DOWN)
    return float(units * tick)


def _open_stop_orders(broker: Any, symbol: str) -> list[dict]:
    """Retourne uniquement les stops du bot sur un marche."""
    if broker.config.dry_run:
        return []
    try:
        rows = broker._appel("GET", "/ordersOpen",
                             params={"market": broker.symbol_for(symbol)})
    except Exception as exc:  # noqa: BLE001
        logger.warning("stops ouverts illisibles sur %s : %s", symbol, str(exc)[:120])
        return []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if str(row.get("side", "")).lower() != "sell":
            continue
        if str(row.get("orderType", "")) not in {"stopLoss", "stopLossLimit"}:
            continue
        if int(row.get("operatorId", broker.config.operator_id) or 0) != broker.config.operator_id:
            continue
        if row.get("orderId"):
            result.append(row)
    return result


def _cancel_exact_stop(broker: Any, symbol: str, order_id: str) -> None:
    """Annule un seul ordre, identifie par son orderId."""
    broker._appel("DELETE", "/order", params={
        "market": broker.symbol_for(symbol),
        "orderId": order_id,
        "operatorId": broker.config.operator_id,
    })


def _annuler_stop(self: Any, symbol: str) -> None:
    """Annule uniquement les stops appartenant au bot."""
    if self.config.dry_run:
        self._stops.pop(symbol, None)
        self._stop_pose.pop(symbol, None)
        return

    ids: list[str] = []
    known = self._stops.get(symbol)
    if known:
        ids.append(known)
    for row in _open_stop_orders(self, symbol):
        oid = str(row.get("orderId", ""))
        if oid and oid not in ids:
            ids.append(oid)

    for oid in ids:
        try:
            _cancel_exact_stop(self, symbol, oid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("stop %s non annule sur %s : %s", oid, symbol, str(exc)[:120])

    self._stops.pop(symbol, None)
    self._stop_pose.pop(symbol, None)


def _recover_stop(self: Any, symbol: str) -> None:
    """Reconnecte le stop reel au suivi local apres un redemarrage."""
    rows = _open_stop_orders(self, symbol)
    if not rows:
        return
    row = max(rows, key=lambda r: int(r.get("created", 0) or 0))
    self._stops[symbol] = str(row["orderId"])
    try:
        trigger = float(row.get("triggerAmount") or row.get("triggerPrice") or 0)
    except (TypeError, ValueError):
        trigger = 0.0
    if trigger > 0:
        self._stop_pose[symbol] = trigger


def harden_bitvavo(BitvavoBroker: Any, RegleMarche: Any) -> None:
    """Installe les garde-fous sur les classes Bitvavo importees."""
    original_appel = BitvavoBroker._appel
    original_reprendre = BitvavoBroker.reprendre
    original_arrondir_prix = RegleMarche.arrondir_prix

    def appel(self, methode: str, chemin: str, params=None, corps=None, signe=True):
        response = original_appel(self, methode, chemin, params=params, corps=corps, signe=signe)
        if methode == "GET" and chemin == "/markets" and isinstance(response, list):
            for row in response:
                market = row.get("market")
                tick = row.get("tickSize")
                if market and tick:
                    try:
                        _TICKS[str(market)] = Decimal(str(tick))
                    except Exception:  # noqa: BLE001
                        continue
                if market in self._regles:
                    quantity_decimals = row.get("quantityDecimals")
                    if quantity_decimals is not None:
                        try:
                            self._regles[str(market)].amount_decimals = int(quantity_decimals)
                        except (TypeError, ValueError):
                            pass
        return response

    def reprendre(self, position):
        ok = original_reprendre(self, position)
        if ok:
            _recover_stop(self, position.symbol)
        return ok

    def arrondir_prix(self, prix: float) -> float:
        return _tick_floor(self, prix, original_arrondir_prix)

    BitvavoBroker._appel = appel
    BitvavoBroker._annuler_stop = _annuler_stop
    BitvavoBroker.reprendre = reprendre
    RegleMarche.arrondir_prix = arrondir_prix
