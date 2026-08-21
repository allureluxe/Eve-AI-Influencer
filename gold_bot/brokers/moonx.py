"""Execution sur MoonX.

Le robot passe ses ordres seul : analyse -> decision -> ordre envoye, sans
validation manuelle. Ce module est le seul point de contact avec la
plateforme.

Deux modes d'execution, selon ce qui est disponible sur le compte :

  1. MODE REST (`MOONX_API_URL` + `MOONX_API_KEY`) : le robot appelle
     directement l'API. C'est le mode a privilegier, entierement autonome.

  2. MODE PONT (`MOONX_BRIDGE_FILE`) : le robot ecrit ses ordres dans un
     fichier de file d'attente au format JSON Lines, qu'un executeur
     externe consomme (par exemple une session connectee au connecteur MCP
     MoonX). Utile quand l'acces se fait par le connecteur plutot que par
     une cle API.

Les routes et les noms de champs sont entierement parametrables par
variables d'environnement : l'API de MoonX peut evoluer ou differer de la
convention retenue ici sans qu'il faille toucher au code.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from ..core import ClosedTrade, Position, Side, Tick
from ..datasources.base import DEFAULT_TIMEOUT, ProviderError, http_get
from ..universe import Instrument
from .base import AccountInfo, Broker, BrokerError, new_position_id

logger = logging.getLogger(__name__)


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@dataclass(slots=True)
class MoonXConfig:
    """Configuration de l'acces MoonX (tout est surchargeable)."""

    base_url: str = ""
    api_key: str = ""
    api_secret: str = ""
    account_id: str = ""

    # Routes
    account_path: str = "/api/v1/account"
    positions_path: str = "/api/v1/positions"
    order_path: str = "/api/v1/order"
    modify_path: str = "/api/v1/position/modify"
    close_path: str = "/api/v1/position/close"

    # Noms de champs attendus dans les reponses
    equity_field: str = "equity"
    balance_field: str = "balance"
    currency_field: str = "currency"

    # Comportement
    leverage: int = 20
    timeout: float = DEFAULT_TIMEOUT
    max_retries: int = 2
    dry_run: bool = False              # journalise sans envoyer
    bridge_file: str = ""              # mode pont (file d'attente d'ordres)

    @classmethod
    def from_env(cls) -> "MoonXConfig":
        return cls(
            base_url=_env("MOONX_API_URL").rstrip("/"),
            api_key=_env("MOONX_API_KEY"),
            api_secret=_env("MOONX_API_SECRET"),
            account_id=_env("MOONX_ACCOUNT_ID"),
            account_path=_env("MOONX_ACCOUNT_PATH", "/api/v1/account"),
            positions_path=_env("MOONX_POSITIONS_PATH", "/api/v1/positions"),
            order_path=_env("MOONX_ORDER_PATH", "/api/v1/order"),
            modify_path=_env("MOONX_MODIFY_PATH", "/api/v1/position/modify"),
            close_path=_env("MOONX_CLOSE_PATH", "/api/v1/position/close"),
            equity_field=_env("MOONX_EQUITY_FIELD", "equity"),
            balance_field=_env("MOONX_BALANCE_FIELD", "balance"),
            currency_field=_env("MOONX_CURRENCY_FIELD", "currency"),
            leverage=int(_env("MOONX_LEVERAGE", "20") or 20),
            dry_run=_env("MOONX_DRY_RUN", "").lower() in ("1", "true", "yes"),
            bridge_file=_env("MOONX_BRIDGE_FILE", ""),
        )


def http_json(url: str, method: str = "POST", payload: Optional[dict] = None,
              headers: Optional[dict[str, str]] = None, timeout: float = DEFAULT_TIMEOUT) -> Any:
    """Appel HTTP avec corps JSON (POST/PUT/DELETE)."""
    body = json.dumps(payload or {}).encode("utf-8")
    hdrs = {"Content-Type": "application/json", "Accept": "application/json",
            "User-Agent": "gold-bot/1.0"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else {}


class MoonXBroker(Broker):
    """Execution automatique des ordres sur MoonX."""

    name = "moonx"
    is_live = True

    def __init__(self, config: Optional[MoonXConfig] = None,
                 instruments: Optional[dict[str, Instrument]] = None) -> None:
        self.config = config or MoonXConfig.from_env()
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = instruments or {}
        self._closed: list[ClosedTrade] = []
        self._account = AccountInfo(0.0, 0.0)
        self._last_error = ""
        self._last_sync = 0.0

    # ---------------------------------------------------------------
    @property
    def mode(self) -> str:
        if self.config.dry_run:
            return "simulation (dry-run)"
        if self.config.base_url and self.config.api_key:
            return "API REST"
        if self.config.bridge_file:
            return "pont fichier"
        return "non configure"

    def _headers(self) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.config.api_key}"}
        if self.config.api_secret:
            h["X-API-SECRET"] = self.config.api_secret
        if self.config.account_id:
            h["X-ACCOUNT-ID"] = self.config.account_id
        return h

    def _url(self, path: str) -> str:
        return f"{self.config.base_url}{path}"

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def symbol_for(self, symbol: str) -> str:
        """Code du symbole cote MoonX (surchargeable par instrument)."""
        return _env(f"MOONX_SYMBOL_{symbol.upper()}", symbol.upper())

    # ---------------------------------------------------------------
    def connect(self) -> bool:
        cfg = self.config
        if cfg.dry_run:
            logger.warning("MoonX en mode simulation : les ordres sont journalises, pas envoyes")
            self._account = AccountInfo(float(_env("MOONX_DRYRUN_EQUITY", "1000") or 1000),
                                        float(_env("MOONX_DRYRUN_EQUITY", "1000") or 1000),
                                        _env("MOONX_CURRENCY", "EUR"))
            return True
        if cfg.bridge_file and not (cfg.base_url and cfg.api_key):
            os.makedirs(os.path.dirname(cfg.bridge_file) or ".", exist_ok=True)
            logger.info("MoonX en mode pont : ordres ecrits dans %s", cfg.bridge_file)
            return True
        if not cfg.base_url or not cfg.api_key:
            self._last_error = ("MOONX_API_URL et MOONX_API_KEY sont requis "
                                "(ou MOONX_BRIDGE_FILE pour le mode pont)")
            logger.error("connexion MoonX impossible : %s", self._last_error)
            return False
        try:
            self.sync()
            logger.info("MoonX connecte : capital %.2f %s, %d position(s) ouverte(s)",
                        self._account.equity, self._account.currency, len(self._positions))
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("connexion MoonX echouee : %s", str(exc)[:200])
            return False

    def healthy(self) -> bool:
        return not self._last_error

    # ---------------------------------------------------------------
    def sync(self) -> None:
        """Recupere l'etat reel du compte et des positions.

        L'etat du broker fait foi : si une position a ete fermee cote
        plateforme (stop touche, intervention manuelle), le robot doit le
        voir immediatement.
        """
        cfg = self.config
        if cfg.dry_run or not (cfg.base_url and cfg.api_key):
            return
        try:
            data = http_get(self._url(cfg.account_path), headers=self._headers(),
                            timeout=cfg.timeout, retries=cfg.max_retries)
            payload = data.get("data", data) if isinstance(data, dict) else {}
            self._account = AccountInfo(
                equity=float(payload.get(cfg.equity_field, payload.get("equity", 0)) or 0),
                balance=float(payload.get(cfg.balance_field, payload.get("balance", 0)) or 0),
                currency=str(payload.get(cfg.currency_field, "EUR")),
                margin_used=float(payload.get("marginUsed", payload.get("margin_used", 0)) or 0),
                margin_free=float(payload.get("marginFree", payload.get("margin_free", 0)) or 0),
                leverage=float(payload.get("leverage", cfg.leverage) or cfg.leverage),
            )
            self._sync_positions()
            self._last_error = ""
            self._last_sync = time.time()
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise BrokerError(f"synchronisation MoonX impossible : {exc}") from exc

    def _sync_positions(self) -> None:
        cfg = self.config
        data = http_get(self._url(cfg.positions_path), headers=self._headers(),
                        timeout=cfg.timeout, retries=cfg.max_retries)
        rows = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            return
        seen: set[str] = set()
        for row in rows:
            pid = str(row.get("id") or row.get("positionId") or row.get("ticket") or "")
            if not pid:
                continue
            seen.add(pid)
            existing = self._positions.get(pid)
            side = Side.BUY if str(row.get("side", row.get("type", "buy"))).lower().startswith("b") else Side.SELL
            entry = float(row.get("entryPrice") or row.get("openPrice") or row.get("price") or 0)
            volume = float(row.get("volume") or row.get("size") or row.get("quantity") or 0)
            sl = float(row.get("stopLoss") or row.get("sl") or 0)
            tp = float(row.get("takeProfit") or row.get("tp") or 0)
            if existing:
                # On conserve l'etat de gestion local (extensions, break-even),
                # mais les niveaux reels du broker font autorite.
                existing.volume, existing.stop_loss, existing.take_profit = volume, sl or existing.stop_loss, tp or existing.take_profit
            else:
                opened = float(row.get("openTime") or row.get("createdAt") or time.time())
                self._positions[pid] = Position(
                    id=pid, symbol=str(row.get("symbol", "")).upper(), side=side, volume=volume,
                    entry_price=entry, stop_loss=sl, take_profit=tp,
                    opened_at=opened / 1000.0 if opened > 1e11 else opened,
                    broker_ref=pid)
        # Positions disparues cote plateforme : elles ont ete cloturees.
        for pid in list(self._positions):
            if pid not in seen:
                logger.info("position %s fermee cote MoonX", pid)
                self._positions.pop(pid, None)

    # ---------------------------------------------------------------
    def account(self) -> AccountInfo:
        return self._account

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    # ---------------------------------------------------------------
    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        """Envoie un ordre au marche avec SL et TP attaches.

        Le stop-loss est transmis DANS l'ordre d'ouverture : si la connexion
        tombe juste apres, la position reste protegee cote plateforme.
        """
        if lots <= 0:
            raise BrokerError("volume nul")
        if not stop_loss:
            raise BrokerError("ouverture refusee : stop-loss obligatoire")

        payload = {
            "symbol": self.symbol_for(instrument.symbol),
            "side": side.value.lower(),
            "type": "market",
            "quantity": lots,
            "volume": lots,
            "stopLoss": round(stop_loss, instrument.digits),
            "takeProfit": round(take_profit, instrument.digits),
            "leverage": self.config.leverage,
            "comment": comment or "gold-bot",
        }
        if self.config.account_id:
            payload["accountId"] = self.config.account_id

        response = self._send("open", self.config.order_path, payload)
        pid = str((response or {}).get("id")
                  or (response or {}).get("positionId")
                  or (response or {}).get("orderId")
                  or new_position_id())
        fill = float((response or {}).get("price")
                     or (response or {}).get("fillPrice") or 0) or 0.0

        pos = Position(
            id=pid, symbol=instrument.symbol, side=side, volume=lots,
            entry_price=fill or round(stop_loss + side.sign * abs(take_profit - stop_loss) / 3, instrument.digits),
            stop_loss=round(stop_loss, instrument.digits),
            take_profit=round(take_profit, instrument.digits),
            opened_at=time.time(), broker_ref=pid, comment=comment,
        )
        self._positions[pid] = pos
        self._instruments[instrument.symbol] = instrument
        logger.info("ORDRE ENVOYE [%s] %s %s %.4f lots SL %.5f TP %.5f -> id %s",
                    self.mode, side.value, instrument.symbol, lots, pos.stop_loss, pos.take_profit, pid)
        return pos

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        pos = self._positions.get(position_id)
        if pos is None:
            return False
        inst = self._instruments.get(pos.symbol)
        digits = inst.digits if inst else 5
        payload: dict[str, Any] = {"id": position_id, "positionId": position_id,
                                   "symbol": self.symbol_for(pos.symbol)}
        if stop_loss is not None:
            payload["stopLoss"] = round(stop_loss, digits)
        if take_profit is not None:
            payload["takeProfit"] = round(take_profit, digits)

        self._send("modify", self.config.modify_path, payload)
        if stop_loss is not None:
            pos.stop_loss = round(stop_loss, digits)
        if take_profit is not None:
            pos.take_profit = round(take_profit, digits)
        return True

    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        pos = self._positions.get(position_id)
        if pos is None:
            return None
        vol = min(volume or pos.volume, pos.volume)
        is_partial = vol < pos.volume - 1e-9
        payload = {"id": position_id, "positionId": position_id,
                   "symbol": self.symbol_for(pos.symbol), "quantity": vol, "volume": vol,
                   "reason": reason or "gold-bot"}
        response = self._send("close", self.config.close_path, payload)

        inst = self._instruments.get(pos.symbol)
        exit_price = float((response or {}).get("price")
                           or (response or {}).get("closePrice") or 0) or pos.take_profit
        profit = float((response or {}).get("profit") or 0)
        if not profit and inst:
            profit = pos.side.sign * (exit_price - pos.entry_price) * inst.value_per_price_unit(vol)

        trade = ClosedTrade(
            position_id=pos.id, symbol=pos.symbol, side=pos.side, volume=vol,
            entry_price=pos.entry_price, exit_price=exit_price,
            opened_at=pos.opened_at, closed_at=time.time(),
            profit=round(profit, 2), r_multiple=round(pos.r_multiple(exit_price), 3),
            reason=reason, tp_extensions=pos.tp_extensions,
            max_favorable_r=round(pos.r_multiple(pos.max_favorable), 3),
            partial=is_partial,
        )
        self._closed.append(trade)
        pos.volume = round(pos.volume - vol, 8)
        if pos.volume <= 1e-9:
            self._positions.pop(position_id, None)
        logger.info("CLOTURE [%s] %s %s %.4f lots -> %+.2f | %s",
                    self.mode, pos.side.value, pos.symbol, vol, profit, reason)
        return trade

    # ---------------------------------------------------------------
    def _send(self, action: str, path: str, payload: dict) -> Optional[dict]:
        """Transmet une instruction, selon le mode d'execution actif."""
        cfg = self.config
        record = {"ts": time.time(), "action": action, "path": path, "payload": payload}

        if cfg.dry_run:
            logger.warning("[DRY-RUN] %s %s", action, json.dumps(payload, ensure_ascii=False))
            self._append_bridge(record) if cfg.bridge_file else None
            return {}

        if cfg.base_url and cfg.api_key:
            last: Optional[Exception] = None
            for attempt in range(cfg.max_retries + 1):
                try:
                    data = http_json(self._url(path), "POST", payload,
                                     headers=self._headers(), timeout=cfg.timeout)
                    if isinstance(data, dict):
                        if data.get("code") not in (None, 0, 200, "0", "OK", "success"):
                            raise BrokerError(f"MoonX a refuse l'ordre : {data.get('msg') or data}")
                        return data.get("data", data)
                    return {}
                except Exception as exc:  # noqa: BLE001
                    last = exc
                    if attempt < cfg.max_retries:
                        time.sleep(1.5 * (attempt + 1))
            self._last_error = str(last)
            raise BrokerError(f"echec de l'instruction '{action}' sur MoonX : {last}")

        if cfg.bridge_file:
            self._append_bridge(record)
            return {}

        raise BrokerError("MoonX non configure : ni API REST, ni pont fichier")

    def _append_bridge(self, record: dict) -> None:
        """Ecrit l'ordre dans la file d'attente du pont (JSON Lines)."""
        path = self.config.bridge_file
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("ordre depose dans le pont : %s %s", record["action"], path)

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed)
