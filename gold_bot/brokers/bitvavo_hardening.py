"""Correctifs de compatibilite et de securite Bitvavo."""
from __future__ import annotations

import logging
from decimal import Decimal, ROUND_DOWN
from typing import Any

logger = logging.getLogger(__name__)
_TICKS: dict[str, Decimal] = {}
_EXIT_TYPES = {"stopLoss", "stopLossLimit", "takeProfit", "takeProfitLimit"}


def _tick_floor(self, prix: float, original):
    if prix <= 0:
        return prix
    tick = _TICKS.get(self.market)
    if tick is None or tick <= 0:
        return original(self, prix)
    value = Decimal(str(prix))
    units = (value / tick).to_integral_value(rounding=ROUND_DOWN)
    return float(units * tick)


def _open_exit_orders(broker: Any, symbol: str) -> list[dict]:
    if broker.config.dry_run:
        return []
    try:
        rows = broker._appel("GET", "/ordersOpen", params={"market": broker.symbol_for(symbol)})
    except Exception as exc:  # noqa: BLE001
        logger.warning("ordres de sortie illisibles sur %s : %s", symbol, str(exc)[:120])
        return []
    result = []
    for row in rows if isinstance(rows, list) else []:
        if str(row.get("side", "")).lower() != "sell":
            continue
        if str(row.get("orderType", "")) not in _EXIT_TYPES:
            continue
        if int(row.get("operatorId", broker.config.operator_id) or 0) != broker.config.operator_id:
            continue
        if row.get("orderId"):
            result.append(row)
    return result


def _open_stop_orders(broker: Any, symbol: str) -> list[dict]:
    return [r for r in _open_exit_orders(broker, symbol)
            if str(r.get("orderType", "")) in {"stopLoss", "stopLossLimit"}]


def _open_tp_orders(broker: Any, symbol: str) -> list[dict]:
    return [r for r in _open_exit_orders(broker, symbol)
            if str(r.get("orderType", "")) in {"takeProfit", "takeProfitLimit"}]


def _cancel_exact(broker: Any, symbol: str, order_id: str) -> None:
    broker._appel("DELETE", "/order", params={
        "market": broker.symbol_for(symbol),
        "orderId": order_id,
        "operatorId": broker.config.operator_id,
    })


def _annuler_stop(self: Any, symbol: str) -> None:
    """Annule TP et SL du bot, jamais les ordres d'un autre operatorId."""
    if self.config.dry_run:
        self._stops.pop(symbol, None)
        self._stop_pose.pop(symbol, None)
        getattr(self, "_take_profits", {}).pop(symbol, None)
        getattr(self, "_take_profit_pose", {}).pop(symbol, None)
        return

    ids: list[str] = []
    for known in (self._stops.get(symbol), getattr(self, "_take_profits", {}).get(symbol)):
        if known and known not in ids:
            ids.append(known)
    for row in _open_exit_orders(self, symbol):
        oid = str(row.get("orderId", ""))
        if oid and oid not in ids:
            ids.append(oid)
    for oid in ids:
        try:
            _cancel_exact(self, symbol, oid)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ordre de sortie %s non annule sur %s : %s", oid, symbol, str(exc)[:120])
    self._stops.pop(symbol, None)
    self._stop_pose.pop(symbol, None)
    getattr(self, "_take_profits", {}).pop(symbol, None)
    getattr(self, "_take_profit_pose", {}).pop(symbol, None)


def _recover_stop(self: Any, symbol: str) -> None:
    """Reconnecte TP et SL reels au suivi local apres redemarrage."""
    rows = _open_exit_orders(self, symbol)
    stops = [r for r in rows if str(r.get("orderType", "")) in {"stopLoss", "stopLossLimit"}]
    tps = [r for r in rows if str(r.get("orderType", "")) in {"takeProfit", "takeProfitLimit"}]
    if stops:
        row = max(stops, key=lambda r: int(r.get("created", 0) or 0))
        self._stops[symbol] = str(row["orderId"])
        try:
            trigger = float(row.get("triggerAmount") or row.get("triggerPrice") or 0)
        except (TypeError, ValueError):
            trigger = 0.0
        if trigger > 0:
            self._stop_pose[symbol] = trigger
    if tps:
        row = max(tps, key=lambda r: int(r.get("created", 0) or 0))
        if not hasattr(self, "_take_profits"):
            self._take_profits = {}
        if not hasattr(self, "_take_profit_pose"):
            self._take_profit_pose = {}
        self._take_profits[symbol] = str(row["orderId"])
        try:
            trigger = float(row.get("triggerAmount") or row.get("triggerPrice") or 0)
        except (TypeError, ValueError):
            trigger = 0.0
        if trigger > 0:
            self._take_profit_pose[symbol] = trigger


def _raise_broker(message: str):
    from .base import BrokerError
    return BrokerError(message)


def formater(valeur: float, decimales: int = 12) -> str:
    texte = f"{valeur:.{max(0, decimales)}f}"
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte or "0"


def _poser_take_profit(self: Any, position: Any) -> None:
    """Depose un vrai TP market sur Bitvavo au niveau demande."""
    if self.config.dry_run:
        return
    code = self.symbol_for(position.symbol)
    regle = self.regle(position.symbol)
    quantite = regle.arrondir_quantite(position.volume)
    trigger = regle.arrondir_prix(position.take_profit)
    prix_courant = self._prix(code)
    if quantite <= 0:
        raise _raise_broker("take-profit impossible: quantite nulle")
    if regle.min_amount and quantite < regle.min_amount:
        raise _raise_broker(f"take-profit sous le minimum de quantite sur {code}")
    if trigger <= 0:
        raise _raise_broker(f"take-profit invalide sur {code}")
    if prix_courant is not None and prix_courant >= trigger:
        raise _raise_broker(f"take-profit deja atteint sur {code} (prix {prix_courant}, TP {trigger})")

    response = self._appel("POST", "/order", corps={
        "market": code,
        "side": "sell",
        "orderType": "takeProfit",
        "operatorId": self.config.operator_id,
        "amount": formater(quantite, regle.amount_decimals),
        "triggerType": "price",
        "triggerReference": "lastTrade",
        "triggerAmount": formater(trigger),
    })
    order_id = str(response.get("orderId", ""))
    if not order_id:
        raise _raise_broker(f"Bitvavo TP sans orderId sur {code}")
    if not hasattr(self, "_take_profits"):
        self._take_profits = {}
    if not hasattr(self, "_take_profit_pose"):
        self._take_profit_pose = {}
    self._take_profits[position.symbol] = order_id
    self._take_profit_pose[position.symbol] = trigger
    logger.info("TP REEL depose sur Bitvavo : %s @ %s, ordre %s", code, formater(quantite), formater(trigger), order_id)


def _ventes_depuis(self: Any, code: str, depuis: float):
    """Executions de vente du BOT uniquement, jamais celles d'un autre trader."""
    try:
        lignes = self._appel("GET", "/trades", params={"market": code, "limit": 100})
    except Exception as exc:  # noqa: BLE001
        logger.warning("executions %s illisibles : %s", code, str(exc)[:120])
        return 0.0, 0.0, 0.0
    quantite = valeur = frais = 0.0
    for ligne in lignes if isinstance(lignes, list) else []:
        if str(ligne.get("side", "")).lower() != "sell":
            continue
        operator = ligne.get("operatorId")
        if operator is not None:
            try:
                if int(operator) != self.config.operator_id:
                    continue
            except (TypeError, ValueError):
                continue
        try:
            instant = float(ligne.get("timestamp", 0) or 0) / 1000.0
            q = float(ligne.get("amount", 0) or 0)
            prix = float(ligne.get("price", 0) or 0)
        except (TypeError, ValueError):
            continue
        if q <= 0 or prix <= 0 or instant < depuis:
            continue
        quantite += q
        valeur += q * prix
        try:
            frais += abs(float(ligne.get("fee", 0) or 0))
        except (TypeError, ValueError):
            pass
    return (valeur / quantite if quantite else 0.0), quantite, frais


def harden_bitvavo(BitvavoBroker: Any, RegleMarche: Any) -> None:
    """Installe les garde-fous, TP exchange et SL exchange sur Bitvavo."""
    original_appel = BitvavoBroker._appel
    original_reprendre = BitvavoBroker.reprendre
    original_arrondir_prix = RegleMarche.arrondir_prix
    original_poser_stop = BitvavoBroker._poser_stop

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
            if not hasattr(self, "_take_profits"):
                self._take_profits = {}
            if not hasattr(self, "_take_profit_pose"):
                self._take_profit_pose = {}
            _recover_stop(self, position.symbol)
            exits = _open_exit_orders(self, position.symbol)
            has_stop = any(str(r.get("orderType", "")) in {"stopLoss", "stopLossLimit"} for r in exits)
            has_tp = any(str(r.get("orderType", "")) in {"takeProfit", "takeProfitLimit"} for r in exits)
            if not self.config.dry_run and (not has_stop or not has_tp):
                logger.error("PROTECTION INCOMPLETE %s: SL=%s TP=%s", position.symbol, has_stop, has_tp)
        return ok

    def arrondir_prix(self, prix: float) -> float:
        return _tick_floor(self, prix, original_arrondir_prix)

    def poser_stop(self, position):
        """Garde le SL natif puis depose le TP exchange. Sinon on ferme."""
        original_poser_stop(self, position)
        try:
            _poser_take_profit(self, position)
        except Exception as exc:  # noqa: BLE001
            logger.error("TP NON POSE sur %s: %s", position.symbol, str(exc)[:250])
            _annuler_stop(self, position.symbol)
            if position.id in self._positions:
                try:
                    self.close_position(position.id, reason="TP exchange impossible a poser")
                except Exception as close_exc:  # noqa: BLE001
                    logger.critical("SECURITE: fermeture de %s impossible apres echec TP: %s", position.symbol, close_exc)
            raise

    def take_profit_ok(self, symbol: str) -> bool:
        if self.config.dry_run:
            return True
        return bool(_open_tp_orders(self, symbol))

    def protection_ok(self, symbol: str) -> bool:
        if self.config.dry_run:
            return True
        rows = _open_exit_orders(self, symbol)
        has_stop = any(str(r.get("orderType", "")) in {"stopLoss", "stopLossLimit"} for r in rows)
        has_tp = any(str(r.get("orderType", "")) in {"takeProfit", "takeProfitLimit"} for r in rows)
        return has_stop and has_tp

    BitvavoBroker._appel = appel
    BitvavoBroker._annuler_stop = _annuler_stop
    BitvavoBroker._ventes_depuis = _ventes_depuis
    BitvavoBroker.reprendre = reprendre
    BitvavoBroker._poser_stop = poser_stop
    BitvavoBroker.take_profit_ok = take_profit_ok
    BitvavoBroker.protection_ok = protection_ok
    RegleMarche.arrondir_prix = arrondir_prix
