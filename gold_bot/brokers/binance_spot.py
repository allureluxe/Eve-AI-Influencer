"""Execution sur Binance Spot.

Choisi parce que les Futures sont fermes aux particuliers en France. Deux
consequences structurelles, qu'il vaut mieux connaitre que subir :

1. ON NE PEUT QU'ACHETER. Pas de vente a decouvert. Le robot ignore donc
   ses signaux de vente et ne travaille que dans les phases de hausse.

2. LES FRAIS CHANGENT L'ECHELLE DE TEMPS. Binance preleve 0,1 % a l'achat
   et 0,1 % a la vente. Rapporte au risque d'un trade :

       cout / risque = frais aller-retour / (distance du stop en % du prix)

   Sur un stop de 0,13 % (typique en M1), cela fait 159 % du risque : le
   trade est perdant avant meme d'avoir commence. Pour tenir sous 15 %, il
   faut un stop d'au moins 1,3 % du prix — soit une unite de temps H1 ou
   superieure, et un ou quelques trades par jour au lieu de vingt.

   Ce n'est pas un reglage a forcer : c'est de l'arithmetique.

Le stop et l'objectif sont poses sur la plateforme sous forme d'ordre OCO
(l'un annule l'autre) : si le robot s'arrete, la position reste bornee des
deux cotes.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from ..core import ClosedTrade, Position, Side, Tick
from ..datasources.base import http_get
from ..universe import Instrument
from .base import AccountInfo, Broker, BrokerError
from .binance import SYMBOLES, BinanceConfig, RegleSymbole

logger = logging.getLogger(__name__)

REEL = "https://api.binance.com"
TESTNET = "https://testnet.binance.vision"

# Frais standards. Avec BNB actif sur le compte, ils tombent a 0,075 %.
FRAIS_PAR_SENS = 0.001


@dataclass(slots=True)
class SpotConfig(BinanceConfig):
    """Configuration du spot. Herite des champs communs."""

    fee_rate: float = FRAIS_PAR_SENS
    quote_asset: str = "USDT"

    @classmethod
    def from_env(cls) -> "SpotConfig":
        base = BinanceConfig.from_env()
        return cls(
            api_key=base.api_key, api_secret=base.api_secret,
            testnet=base.testnet, leverage=1, margin_type="NONE",
            recv_window=base.recv_window, timeout=base.timeout,
            dry_run=base.dry_run,
            stop_move_threshold_r=base.stop_move_threshold_r,
            fee_rate=float(os.getenv("BINANCE_FEE_RATE", str(FRAIS_PAR_SENS)) or FRAIS_PAR_SENS),
            quote_asset=os.getenv("BINANCE_QUOTE_ASSET", "USDT"),
        )


class BinanceSpotBroker(Broker):
    """Achat au comptant sur Binance, avec stop et objectif deposes en OCO."""

    name = "binance_spot"
    is_live = True
    supports_short = False        # le spot ne permet pas la vente a decouvert

    def __init__(self, config: Optional[SpotConfig] = None) -> None:
        self.config = config or SpotConfig.from_env()
        self.base = TESTNET if self.config.testnet else REEL
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = {}
        self._closed: list[ClosedTrade] = []
        self._regles: dict[str, RegleSymbole] = {}
        self._account = AccountInfo(0.0, 0.0, "USDT")
        self._soldes: dict[str, float] = {}
        self._oco: dict[str, int] = {}
        self._last_error = ""

    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        if self.config.dry_run:
            return "simulation (dry-run)"
        return "testnet (argent fictif)" if self.config.testnet else "REEL"

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def symbol_for(self, symbol: str) -> str:
        code = SYMBOLES.get(symbol.upper())
        if not code:
            raise BrokerError(f"{symbol} n'est pas disponible sur Binance Spot")
        return code

    def supports(self, symbol: str) -> bool:
        return symbol.upper() in SYMBOLES

    def regle(self, symbol: str) -> RegleSymbole:
        code = self.symbol_for(symbol)
        return self._regles.get(code, RegleSymbole(symbol=code))

    # --- signature et appels : partages avec le module futures ---
    def _signer(self, params: dict[str, Any]) -> str:
        from .binance import BinanceBroker
        return BinanceBroker._signer(self, params)   # meme algorithme HMAC

    def _appel(self, methode: str, chemin: str, params: Optional[dict] = None,
               signe: bool = True) -> Any:
        from .binance import BinanceBroker
        return BinanceBroker._appel(self, methode, chemin, params, signe)

    # ------------------------------------------------------------------
    def connect(self) -> bool:
        cfg = self.config
        if cfg.dry_run and not (cfg.api_key and cfg.api_secret):
            logger.warning("Binance Spot en simulation sans cle : solde fictif")
            solde = float(os.getenv("BINANCE_DRYRUN_EQUITY", "50") or 50)
            self._account = AccountInfo(solde, solde, cfg.quote_asset)
            return True
        if not (cfg.api_key and cfg.api_secret):
            self._last_error = "BINANCE_API_KEY et BINANCE_API_SECRET absents"
            logger.error("connexion Binance Spot impossible : %s", self._last_error)
            return False
        try:
            self._charger_regles()
            self.sync()
            if cfg.dry_run:
                logger.warning("Binance Spot en simulation : lecture reelle, "
                               "aucun ordre ne sera envoye")
            logger.info("Binance Spot connecte [%s] : %.2f %s",
                        self.mode, self._account.equity, cfg.quote_asset)
            if not cfg.testnet and not cfg.dry_run:
                logger.warning("MODE REEL : les ordres engagent de l'argent veritable")
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("connexion Binance Spot echouee : %s", str(exc)[:250])
            return False

    def healthy(self) -> bool:
        return not self._last_error

    # ------------------------------------------------------------------
    def _charger_regles(self) -> None:
        """Contraintes reelles de la plateforme, lues et non devinees."""
        data = http_get(f"{self.base}/api/v3/exchangeInfo", timeout=self.config.timeout)
        attendus = set(SYMBOLES.values())
        for ligne in data.get("symbols", []):
            code = ligne.get("symbol")
            if code not in attendus or ligne.get("status") != "TRADING":
                continue
            regle = RegleSymbole(symbol=code,
                                 quantity_precision=int(ligne.get("baseAssetPrecision", 8)),
                                 price_precision=int(ligne.get("quoteAssetPrecision", 8)))
            for filtre in ligne.get("filters", []):
                t = filtre.get("filterType")
                if t == "LOT_SIZE":
                    regle.step_size = float(filtre.get("stepSize", regle.step_size))
                    regle.min_qty = float(filtre.get("minQty", regle.min_qty))
                elif t == "PRICE_FILTER":
                    regle.tick_size = float(filtre.get("tickSize", regle.tick_size))
                elif t in ("NOTIONAL", "MIN_NOTIONAL"):
                    regle.min_notional = float(filtre.get("minNotional", regle.min_notional))
            self._regles[code] = regle
        logger.info("regles spot chargees pour %d symbole(s)", len(self._regles))

    def apply_market_rules(self, universe) -> list[str]:
        modifies: list[str] = []
        for inst in universe:
            code = SYMBOLES.get(inst.symbol.upper())
            regle = self._regles.get(code) if code else None
            if regle is None:
                continue
            if abs(inst.min_lot - regle.min_qty) > 1e-12 or abs(inst.lot_step - regle.step_size) > 1e-12:
                modifies.append(f"{inst.symbol} lot min {inst.min_lot} -> {regle.min_qty}")
                inst.min_lot = regle.min_qty
                inst.lot_step = regle.step_size
        for ligne in modifies:
            logger.info("contrainte alignee sur Binance Spot : %s", ligne)
        return modifies

    # ------------------------------------------------------------------
    def sync(self) -> None:
        """Lit les soldes et reconstitue la valeur du compte en USDT.

        En spot il n'existe pas de notion de « position » cote plateforme :
        on detient des actifs. Le capital total est donc le solde en USDT
        plus la valeur de marche de ce qui est detenu.
        """
        compte = self._appel("GET", "/api/v3/account")
        self._soldes = {}
        for actif in compte.get("balances", []):
            libre = float(actif.get("free", 0) or 0)
            bloque = float(actif.get("locked", 0) or 0)
            if libre + bloque > 0:
                self._soldes[actif["asset"]] = libre + bloque

        quote = self.config.quote_asset
        disponible = float(next((a.get("free", 0) for a in compte.get("balances", [])
                                 if a.get("asset") == quote), 0) or 0)
        total = self._soldes.get(quote, 0.0)

        for actif, quantite in self._soldes.items():
            if actif == quote:
                continue
            code = f"{actif}{quote}"
            if code not in self._regles:
                continue
            prix = self._prix(code)
            if prix:
                total += quantite * prix

        self._account = AccountInfo(equity=total, balance=total, currency=quote,
                                    margin_used=max(0.0, total - disponible),
                                    margin_free=disponible, leverage=1.0)
        self._last_error = ""

    def _prix(self, code: str) -> Optional[float]:
        try:
            data = http_get(f"{self.base}/api/v3/ticker/price",
                            params={"symbol": code}, timeout=self.config.timeout)
            return float(data["price"])
        except Exception:  # noqa: BLE001
            return None

    def account(self) -> AccountInfo:
        return self._account

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    # ------------------------------------------------------------------
    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if side is not Side.BUY:
            raise BrokerError(
                "le spot ne permet que l'achat : la vente a decouvert est impossible")
        if not stop_loss:
            raise BrokerError("ouverture refusee : stop-loss obligatoire")

        code = self.symbol_for(instrument.symbol)
        regle = self.regle(instrument.symbol)
        quantite = regle.arrondir_quantite(lots)
        if quantite < regle.min_qty:
            raise BrokerError(f"quantite {quantite} sous le minimum {regle.min_qty} sur {code}")

        reference = self._prix(code) or (stop_loss + take_profit) / 2.0
        notionnel = quantite * reference
        if notionnel < regle.min_notional:
            raise BrokerError(
                f"notionnel {notionnel:.2f} {self.config.quote_asset} sous le minimum "
                f"{regle.min_notional} sur {code}")

        if self.config.dry_run:
            logger.warning("[DRY-RUN] achat %s %.8f, SL %.6f TP %.6f",
                           code, quantite, stop_loss, take_profit)
            reponse = {"fills": [], "executedQty": quantite, "cummulativeQuoteQty": notionnel}
        else:
            reponse = self._appel("POST", "/api/v3/order", {
                "symbol": code, "side": "BUY", "type": "MARKET",
                "quantity": quantite, "newOrderRespType": "FULL",
            })

        rempli = self._prix_moyen(reponse) or reference
        obtenu = float(reponse.get("executedQty", quantite) or quantite)

        position = Position(
            id=instrument.symbol, symbol=instrument.symbol, side=Side.BUY,
            volume=obtenu, entry_price=regle.arrondir_prix(rempli),
            stop_loss=regle.arrondir_prix(stop_loss),
            take_profit=regle.arrondir_prix(take_profit),
            opened_at=time.time(), broker_ref=str(reponse.get("orderId", "")), comment=comment)
        self._positions[instrument.symbol] = position
        self._instruments[instrument.symbol] = instrument

        self._poser_oco(position)
        logger.info("ACHAT [%s] %s %.8f @ %.6f | SL %.6f TP %.6f",
                    self.mode, code, obtenu, position.entry_price,
                    position.stop_loss, position.take_profit)
        return position

    @staticmethod
    def _prix_moyen(reponse: dict) -> Optional[float]:
        """Prix moyen reellement obtenu, calcule sur les executions."""
        fills = reponse.get("fills") or []
        if fills:
            total_q = sum(float(f["qty"]) for f in fills)
            total_v = sum(float(f["qty"]) * float(f["price"]) for f in fills)
            if total_q > 0:
                return total_v / total_q
        q = float(reponse.get("executedQty", 0) or 0)
        v = float(reponse.get("cummulativeQuoteQty", 0) or 0)
        return v / q if q > 0 else None

    # ------------------------------------------------------------------
    def _poser_oco(self, position: Position) -> None:
        """Depose stop et objectif en un seul ordre OCO : l'un annule l'autre."""
        if self.config.dry_run:
            return
        code = self.symbol_for(position.symbol)
        regle = self.regle(position.symbol)
        # Le stop est un stop-limit : on place la limite legerement en dessous
        # du declenchement pour qu'elle parte meme si le prix glisse.
        limite_stop = regle.arrondir_prix(position.stop_loss * 0.998)
        try:
            reponse = self._appel("POST", "/api/v3/order/oco", {
                "symbol": code, "side": "SELL",
                "quantity": regle.arrondir_quantite(position.volume),
                "price": regle.arrondir_prix(position.take_profit),
                "stopPrice": regle.arrondir_prix(position.stop_loss),
                "stopLimitPrice": limite_stop,
                "stopLimitTimeInForce": "GTC",
            })
            self._oco[position.symbol] = int(reponse.get("orderListId", 0))
        except BrokerError as exc:
            logger.error("OCO non pose sur %s : %s", code, str(exc)[:200])
            logger.error("fermeture immediate : une position sans stop est inacceptable")
            self.close_position(position.id, reason="stop impossible a poser")
            raise

    def _annuler_oco(self, symbol: str) -> None:
        if self.config.dry_run:
            return
        try:
            self._appel("DELETE", "/api/v3/openOrders",
                        {"symbol": self.symbol_for(symbol)})
        except BrokerError as exc:
            logger.warning("annulation des ordres sur %s : %s", symbol, str(exc)[:120])
        self._oco.pop(symbol, None)

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        position = self._positions.get(position_id)
        if position is None:
            return False
        regle = self.regle(position.symbol)
        seuil = position.initial_risk * self.config.stop_move_threshold_r if position.initial_risk else 0.0

        bouge = False
        if stop_loss is not None and abs(stop_loss - position.stop_loss) > seuil:
            position.stop_loss = regle.arrondir_prix(stop_loss)
            bouge = True
        elif stop_loss is not None:
            position.stop_loss = regle.arrondir_prix(stop_loss)
        if take_profit is not None and abs(take_profit - position.take_profit) > seuil:
            position.take_profit = regle.arrondir_prix(take_profit)
            bouge = True
        elif take_profit is not None:
            position.take_profit = regle.arrondir_prix(take_profit)

        if not bouge:
            return True
        self._annuler_oco(position.symbol)
        try:
            self._poser_oco(position)
        except BrokerError:
            return False
        return True

    # ------------------------------------------------------------------
    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        position = self._positions.get(position_id)
        if position is None:
            return None
        code = self.symbol_for(position.symbol)
        regle = self.regle(position.symbol)
        quantite = regle.arrondir_quantite(min(volume or position.volume, position.volume))
        if quantite <= 0:
            return None
        partielle = quantite < position.volume - 1e-12

        self._annuler_oco(position.symbol)

        if self.config.dry_run:
            logger.warning("[DRY-RUN] vente %s %.8f (%s)", code, quantite, reason)
            reponse = {"fills": [], "executedQty": quantite,
                       "cummulativeQuoteQty": quantite * (self._prix(code) or position.entry_price)}
        else:
            reponse = self._appel("POST", "/api/v3/order", {
                "symbol": code, "side": "SELL", "type": "MARKET",
                "quantity": quantite, "newOrderRespType": "FULL",
            })

        sortie = self._prix_moyen(reponse) or position.entry_price
        brut = (sortie - position.entry_price) * quantite
        frais = (position.entry_price + sortie) * quantite * self.config.fee_rate
        profit = brut - frais

        trade = ClosedTrade(
            position_id=position.id, symbol=position.symbol, side=Side.BUY,
            volume=quantite, entry_price=position.entry_price,
            exit_price=regle.arrondir_prix(sortie),
            opened_at=position.opened_at, closed_at=time.time(),
            profit=round(profit, 6), r_multiple=round(position.r_multiple(sortie), 3),
            reason=reason, tp_extensions=position.tp_extensions,
            max_favorable_r=round(position.r_multiple(position.max_favorable), 3),
            partial=partielle)
        self._closed.append(trade)

        position.volume = round(position.volume - quantite, 12)
        if position.volume <= 1e-12:
            self._positions.pop(position_id, None)
        else:
            self._poser_oco(position)

        logger.info("VENTE [%s] %s %.8f -> %+.4f %s (frais %.4f) | %s",
                    self.mode, code, quantite, profit, self.config.quote_asset, frais, reason)
        return trade

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed)

    # ------------------------------------------------------------------
    def tick(self, symbol: str) -> Optional[Tick]:
        try:
            data = http_get(f"{self.base}/api/v3/ticker/bookTicker",
                            params={"symbol": self.symbol_for(symbol)},
                            timeout=self.config.timeout)
            return Tick(time.time(), float(data["bidPrice"]), float(data["askPrice"]))
        except Exception:  # noqa: BLE001
            return None
