"""Execution sur Binance Futures USDT-M.

Pourquoi les futures et non le spot : le spot ne permet que d'acheter. La
moitie des signaux du robot — les ventes — serait perdue. Les futures
autorisent les deux sens et acceptent surtout des ordres stop et objectif
DEPOSES SUR LA PLATEFORME : si le robot s'arrete, si le serveur redemarre
ou si le reseau tombe, la position reste protegee.

Le levier est volontairement bas par defaut (3x) : il ne sert pas a
amplifier le risque — celui-ci reste borne par le stop et par le
gestionnaire de risque — mais a permettre au lot minimum de tenir sur un
petit compte.

Points d'attention traites ici :

  - Binance ne sait pas MODIFIER un ordre stop : il faut l'annuler et le
    reposer. Comme le robot deplace son stop en permanence (trailing), on
    ne repose l'ordre que si le niveau a bouge de facon significative,
    sinon on saturerait les quotas pour rien.
  - Les tailles de lot, les pas de prix et le notionnel minimum sont lus
    sur la plateforme (`exchangeInfo`) et non devines.
  - Le testnet est pris en charge : meme API, argent fictif. C'est la
    seule facon de valider une integration sans rien risquer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

from ..core import ClosedTrade, Position, Side, Tick
from ..datasources.base import DEFAULT_TIMEOUT, http_get
from ..universe import Instrument
from .base import AccountInfo, Broker, BrokerError

logger = logging.getLogger(__name__)

REEL = "https://fapi.binance.com"
TESTNET = "https://testnet.binancefuture.com"

# Correspondance entre les symboles du robot et ceux de Binance.
SYMBOLES = {
    "BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT", "SOLUSD": "SOLUSDT",
    "XRPUSD": "XRPUSDT", "DOGEUSD": "DOGEUSDT", "ADAUSD": "ADAUSDT",
    "BNBUSD": "BNBUSDT", "AVAXUSD": "AVAXUSDT", "LINKUSD": "LINKUSDT",
    "LTCUSD": "LTCUSDT", "PAXGUSD": "PAXGUSDT",
}


@dataclass(slots=True)
class BinanceConfig:
    api_key: str = ""
    api_secret: str = ""
    testnet: bool = True          # par defaut on ne risque rien
    # Le levier n'est PAS un reglage de risque : le risque reste borne par le
    # stop et par le gestionnaire. Il sert uniquement a ce que la marge
    # immobilisee laisse de la place sur un petit compte. A 50 USDT, une
    # position BTC au lot minimum represente ~270 USDT de notionnel : sans
    # levier suffisant, Binance refuserait l'ordre faute de marge.
    leverage: int = 10
    margin_type: str = "ISOLATED"  # une position ne peut pas entrainer les autres
    recv_window: int = 5000
    timeout: float = DEFAULT_TIMEOUT
    dry_run: bool = False
    # Seuil de deplacement du stop en dessous duquel on ne repose pas
    # l'ordre sur la plateforme, en fraction du risque initial.
    stop_move_threshold_r: float = 0.08

    @classmethod
    def from_env(cls) -> "BinanceConfig":
        return cls(
            api_key=os.getenv("BINANCE_API_KEY", ""),
            api_secret=os.getenv("BINANCE_API_SECRET", ""),
            testnet=os.getenv("BINANCE_TESTNET", "1").lower() in ("1", "true", "yes", "oui"),
            leverage=int(os.getenv("BINANCE_LEVERAGE", "10") or 10),
            margin_type=os.getenv("BINANCE_MARGIN_TYPE", "ISOLATED").upper(),
            dry_run=os.getenv("BINANCE_DRY_RUN", "").lower() in ("1", "true", "yes", "oui"),
        )


@dataclass(slots=True)
class RegleSymbole:
    """Contraintes reelles de la plateforme pour un symbole."""

    symbol: str
    step_size: float = 0.001      # pas de quantite
    tick_size: float = 0.01       # pas de prix
    min_qty: float = 0.001
    min_notional: float = 5.0
    quantity_precision: int = 3
    price_precision: int = 2

    def arrondir_quantite(self, quantite: float) -> float:
        """Arrondi VERS LE BAS au pas de la plateforme.

        Vers le bas et jamais vers le haut : un arrondi genereux ferait
        depasser le risque prevu a chaque ordre.
        """
        if self.step_size <= 0:
            return round(quantite, self.quantity_precision)
        pas = int(quantite / self.step_size + 1e-9)
        return round(pas * self.step_size, self.quantity_precision)

    def arrondir_prix(self, prix: float) -> float:
        if self.tick_size <= 0:
            return round(prix, self.price_precision)
        pas = round(prix / self.tick_size)
        return round(pas * self.tick_size, self.price_precision)


class BinanceBroker(Broker):
    """Passage d'ordres automatique sur Binance Futures."""

    name = "binance"
    is_live = True

    def __init__(self, config: Optional[BinanceConfig] = None) -> None:
        self.config = config or BinanceConfig.from_env()
        self.base = TESTNET if self.config.testnet else REEL
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = {}
        self._closed: list[ClosedTrade] = []
        self._regles: dict[str, RegleSymbole] = {}
        self._account = AccountInfo(0.0, 0.0, "USDT")
        self._ordres_protection: dict[str, dict[str, int]] = {}
        self._last_error = ""
        self._leverage_pret: set[str] = set()

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
            raise BrokerError(f"{symbol} n'existe pas sur Binance Futures")
        return code

    def supports(self, symbol: str) -> bool:
        return symbol.upper() in SYMBOLES

    # ------------------------------------------------------------------
    # Communication signee
    # ------------------------------------------------------------------
    def _signer(self, params: dict[str, Any]) -> str:
        params["timestamp"] = int(time.time() * 1000)
        params["recvWindow"] = self.config.recv_window
        requete = urllib.parse.urlencode(params)
        signature = hmac.new(self.config.api_secret.encode(),
                             requete.encode(), hashlib.sha256).hexdigest()
        return f"{requete}&signature={signature}"

    def _appel(self, methode: str, chemin: str, params: Optional[dict] = None,
              signe: bool = True) -> Any:
        params = dict(params or {})
        if signe:
            if not (self.config.api_key and self.config.api_secret):
                raise BrokerError("BINANCE_API_KEY et BINANCE_API_SECRET sont requis")
            corps = self._signer(params)
        else:
            corps = urllib.parse.urlencode(params)

        url = f"{self.base}{chemin}"
        entetes = {"X-MBX-APIKEY": self.config.api_key,
                   "Content-Type": "application/x-www-form-urlencoded"}

        if methode == "GET":
            requete = urllib.request.Request(f"{url}?{corps}", headers=entetes, method="GET")
        else:
            requete = urllib.request.Request(url, data=corps.encode(),
                                             headers=entetes, method=methode)
        try:
            with urllib.request.urlopen(requete, timeout=self.config.timeout) as reponse:
                brut = reponse.read().decode("utf-8", errors="replace")
            self._last_error = ""
            return json.loads(brut) if brut.strip() else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            self._last_error = detail
            raise BrokerError(f"Binance a refuse ({exc.code}) : {detail}") from exc
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise BrokerError(f"Binance injoignable : {exc}") from exc

    # ------------------------------------------------------------------
    def connect(self) -> bool:
        cfg = self.config
        if cfg.dry_run:
            logger.warning("Binance en simulation : les ordres sont journalises, pas envoyes")
            self._account = AccountInfo(float(os.getenv("BINANCE_DRYRUN_EQUITY", "50") or 50),
                                        float(os.getenv("BINANCE_DRYRUN_EQUITY", "50") or 50),
                                        "USDT")
            return True
        if not (cfg.api_key and cfg.api_secret):
            self._last_error = "BINANCE_API_KEY et BINANCE_API_SECRET absents"
            logger.error("connexion Binance impossible : %s", self._last_error)
            return False
        try:
            self._charger_regles()
            self.sync()
            logger.info("Binance connecte [%s] : %.2f USDT, %d position(s)",
                        self.mode, self._account.equity, len(self._positions))
            if not cfg.testnet:
                logger.warning("MODE REEL : les ordres engagent de l'argent veritable")
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("connexion Binance echouee : %s", str(exc)[:250])
            return False

    def healthy(self) -> bool:
        return not self._last_error

    # ------------------------------------------------------------------
    def _charger_regles(self) -> None:
        """Lit les contraintes reelles de la plateforme, plutot que de les deviner."""
        data = http_get(f"{self.base}/fapi/v1/exchangeInfo", timeout=self.config.timeout)
        for ligne in data.get("symbols", []):
            code = ligne.get("symbol")
            if code not in SYMBOLES.values():
                continue
            regle = RegleSymbole(symbol=code,
                                 quantity_precision=int(ligne.get("quantityPrecision", 3)),
                                 price_precision=int(ligne.get("pricePrecision", 2)))
            for filtre in ligne.get("filters", []):
                t = filtre.get("filterType")
                if t == "LOT_SIZE":
                    regle.step_size = float(filtre.get("stepSize", regle.step_size))
                    regle.min_qty = float(filtre.get("minQty", regle.min_qty))
                elif t == "PRICE_FILTER":
                    regle.tick_size = float(filtre.get("tickSize", regle.tick_size))
                elif t in ("MIN_NOTIONAL", "NOTIONAL"):
                    regle.min_notional = float(filtre.get("notional",
                                               filtre.get("minNotional", regle.min_notional)))
            self._regles[code] = regle
        logger.info("regles de marche chargees pour %d symbole(s)", len(self._regles))

    def regle(self, symbol: str) -> RegleSymbole:
        code = self.symbol_for(symbol)
        return self._regles.get(code, RegleSymbole(symbol=code))

    def apply_market_rules(self, universe) -> list[str]:
        """Aligne l'univers du robot sur les contraintes reelles de la plateforme.

        Les tailles de lot declarees par defaut dans le robot sont des ordres
        de grandeur ; celles de Binance font foi. Sans cette synchronisation,
        le robot peut calculer une quantite que la plateforme refusera — par
        exemple 0,4 SOL alors que le pas minimal est de 1.
        """
        modifies: list[str] = []
        for inst in universe:
            code = SYMBOLES.get(inst.symbol.upper())
            regle = self._regles.get(code) if code else None
            if regle is None:
                continue
            if abs(inst.min_lot - regle.min_qty) > 1e-12 or abs(inst.lot_step - regle.step_size) > 1e-12:
                modifies.append(f"{inst.symbol} lot min {inst.min_lot} -> {regle.min_qty}, "
                                f"pas {inst.lot_step} -> {regle.step_size}")
                inst.min_lot = regle.min_qty
                inst.lot_step = regle.step_size
            inst.digits = regle.price_precision
        for ligne in modifies:
            logger.info("contrainte alignee sur Binance : %s", ligne)
        return modifies

    def _preparer_symbole(self, code: str) -> None:
        """Fixe le levier et le type de marge, une seule fois par symbole."""
        if code in self._leverage_pret or self.config.dry_run:
            return
        try:
            self._appel("POST", "/fapi/v1/leverage",
                        {"symbol": code, "leverage": self.config.leverage})
        except BrokerError as exc:
            logger.warning("levier non applique sur %s : %s", code, str(exc)[:120])
        try:
            self._appel("POST", "/fapi/v1/marginType",
                        {"symbol": code, "marginType": self.config.margin_type})
        except BrokerError as exc:
            # Binance renvoie une erreur si le mode est deja celui demande.
            if "-4046" not in str(exc):
                logger.warning("type de marge non applique sur %s : %s", code, str(exc)[:120])
        self._leverage_pret.add(code)

    # ------------------------------------------------------------------
    def sync(self) -> None:
        if self.config.dry_run:
            return
        compte = self._appel("GET", "/fapi/v2/account")
        for actif in compte.get("assets", []):
            if actif.get("asset") == "USDT":
                self._account = AccountInfo(
                    equity=float(actif.get("marginBalance", 0) or 0),
                    balance=float(actif.get("walletBalance", 0) or 0),
                    currency="USDT",
                    margin_used=float(actif.get("initialMargin", 0) or 0),
                    margin_free=float(actif.get("availableBalance", 0) or 0),
                    leverage=float(self.config.leverage),
                )
                break
        self._sync_positions(compte)

    def _sync_positions(self, compte: Optional[dict] = None) -> None:
        lignes = (compte or {}).get("positions")
        if lignes is None:
            lignes = self._appel("GET", "/fapi/v2/positionRisk")

        inverse = {v: k for k, v in SYMBOLES.items()}
        vus: set[str] = set()
        for ligne in lignes:
            code = ligne.get("symbol")
            quantite = float(ligne.get("positionAmt", 0) or 0)
            if code not in inverse or abs(quantite) < 1e-12:
                continue
            symbole = inverse[code]
            vus.add(symbole)
            entree = float(ligne.get("entryPrice", 0) or 0)
            sens = Side.BUY if quantite > 0 else Side.SELL
            existante = self._positions.get(symbole)
            if existante:
                existante.volume = abs(quantite)
                existante.entry_price = entree or existante.entry_price
            else:
                # Position ouverte hors du robot, ou reprise apres redemarrage :
                # on l'adopte, le gestionnaire lui redonnera un stop.
                self._positions[symbole] = Position(
                    id=symbole, symbol=symbole, side=sens, volume=abs(quantite),
                    entry_price=entree, stop_loss=0.0, take_profit=0.0,
                    opened_at=time.time(), broker_ref=code)
                logger.info("position adoptee sur %s : %s %.6f", symbole, sens.value, abs(quantite))

        for symbole in list(self._positions):
            if symbole not in vus:
                logger.info("position %s fermee cote Binance", symbole)
                self._positions.pop(symbole, None)
                self._ordres_protection.pop(symbole, None)

    def account(self) -> AccountInfo:
        return self._account

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    # ------------------------------------------------------------------
    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if not stop_loss:
            raise BrokerError("ouverture refusee : stop-loss obligatoire")
        code = self.symbol_for(instrument.symbol)
        regle = self.regle(instrument.symbol)

        quantite = regle.arrondir_quantite(lots)
        if quantite < regle.min_qty:
            raise BrokerError(f"quantite {quantite} sous le minimum {regle.min_qty} sur {code}")

        reference = (stop_loss + take_profit) / 2.0 or stop_loss
        notionnel = quantite * reference
        if notionnel < regle.min_notional:
            raise BrokerError(
                f"notionnel {notionnel:.2f} USDT sous le minimum {regle.min_notional} sur {code} : "
                f"il faudrait au moins {regle.min_notional / reference:.6f} unite(s)")

        self._preparer_symbole(code)

        if self.config.dry_run:
            logger.warning("[DRY-RUN] entree %s %s %.6f, SL %.4f TP %.4f",
                           side.value, code, quantite, stop_loss, take_profit)
            reponse = {"avgPrice": reference, "orderId": int(time.time())}
        else:
            reponse = self._appel("POST", "/fapi/v1/order", {
                "symbol": code,
                "side": "BUY" if side is Side.BUY else "SELL",
                "type": "MARKET",
                "quantity": quantite,
                "newOrderRespType": "RESULT",
            })

        rempli = float(reponse.get("avgPrice") or reponse.get("price") or 0) or reference
        position = Position(
            id=instrument.symbol, symbol=instrument.symbol, side=side, volume=quantite,
            entry_price=regle.arrondir_prix(rempli),
            stop_loss=regle.arrondir_prix(stop_loss),
            take_profit=regle.arrondir_prix(take_profit),
            opened_at=time.time(), broker_ref=str(reponse.get("orderId", "")), comment=comment)
        self._positions[instrument.symbol] = position
        self._instruments[instrument.symbol] = instrument

        # Le filet de securite est pose immediatement : si le robot meurt
        # dans la seconde qui suit, la position reste bornee.
        self._poser_protection(position)
        logger.info("ORDRE ENVOYE [%s] %s %s %.6f @ %.4f | SL %.4f TP %.4f",
                    self.mode, side.value, code, quantite,
                    position.entry_price, position.stop_loss, position.take_profit)
        return position

    # ------------------------------------------------------------------
    def _poser_protection(self, position: Position) -> None:
        """Depose le stop et l'objectif SUR LA PLATEFORME."""
        if self.config.dry_run:
            return
        code = self.symbol_for(position.symbol)
        regle = self.regle(position.symbol)
        sens_sortie = "SELL" if position.side is Side.BUY else "BUY"
        ids: dict[str, int] = {}

        for type_ordre, prix, cle in (("STOP_MARKET", position.stop_loss, "stop"),
                                      ("TAKE_PROFIT_MARKET", position.take_profit, "objectif")):
            if not prix:
                continue
            try:
                reponse = self._appel("POST", "/fapi/v1/order", {
                    "symbol": code, "side": sens_sortie, "type": type_ordre,
                    "stopPrice": regle.arrondir_prix(prix),
                    "closePosition": "true", "workingType": "MARK_PRICE",
                    "priceProtect": "true",
                })
                ids[cle] = int(reponse.get("orderId", 0))
            except BrokerError as exc:
                logger.error("protection %s non posee sur %s : %s", cle, code, str(exc)[:160])
                if cle == "stop":
                    # Une position sans stop cote plateforme est inacceptable :
                    # on prefere la fermer immediatement.
                    logger.error("fermeture immediate de %s faute de stop", code)
                    self.close_position(position.id, reason="stop impossible a poser")
                    raise
        self._ordres_protection[position.symbol] = ids

    def _annuler_protection(self, symbol: str) -> None:
        if self.config.dry_run:
            return
        code = self.symbol_for(symbol)
        try:
            self._appel("DELETE", "/fapi/v1/allOpenOrders", {"symbol": code})
        except BrokerError as exc:
            logger.warning("annulation des ordres sur %s : %s", code, str(exc)[:120])
        self._ordres_protection.pop(symbol, None)

    # ------------------------------------------------------------------
    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        """Deplace le stop et/ou l'objectif.

        Binance ne sait pas modifier un ordre stop : il faut l'annuler et le
        reposer. Comme le robot deplace son stop a chaque bougie, on ne
        repose l'ordre que si le niveau a reellement bouge — sinon on
        saturerait le quota d'API pour des variations invisibles.
        """
        position = self._positions.get(position_id)
        if position is None:
            return False
        regle = self.regle(position.symbol)

        seuil = position.initial_risk * self.config.stop_move_threshold_r if position.initial_risk else 0.0
        bouge = False
        if stop_loss is not None and abs(stop_loss - position.stop_loss) > seuil:
            position.stop_loss = regle.arrondir_prix(stop_loss)
            bouge = True
        if take_profit is not None and abs(take_profit - position.take_profit) > seuil:
            position.take_profit = regle.arrondir_prix(take_profit)
            bouge = True

        if not bouge:
            # Le niveau local est quand meme mis a jour : c'est lui qui sert
            # au raisonnement du gestionnaire de position.
            if stop_loss is not None:
                position.stop_loss = regle.arrondir_prix(stop_loss)
            if take_profit is not None:
                position.take_profit = regle.arrondir_prix(take_profit)
            return True

        self._annuler_protection(position.symbol)
        try:
            self._poser_protection(position)
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

        self._annuler_protection(position.symbol)

        if self.config.dry_run:
            logger.warning("[DRY-RUN] sortie %s %.6f (%s)", code, quantite, reason)
            reponse = {"avgPrice": position.take_profit or position.entry_price}
        else:
            reponse = self._appel("POST", "/fapi/v1/order", {
                "symbol": code,
                "side": "SELL" if position.side is Side.BUY else "BUY",
                "type": "MARKET", "quantity": quantite,
                "reduceOnly": "true", "newOrderRespType": "RESULT",
            })

        sortie = float(reponse.get("avgPrice") or 0) or position.entry_price
        profit = position.side.sign * (sortie - position.entry_price) * quantite

        trade = ClosedTrade(
            position_id=position.id, symbol=position.symbol, side=position.side,
            volume=quantite, entry_price=position.entry_price,
            exit_price=regle.arrondir_prix(sortie),
            opened_at=position.opened_at, closed_at=time.time(),
            profit=round(profit, 4), r_multiple=round(position.r_multiple(sortie), 3),
            reason=reason, tp_extensions=position.tp_extensions,
            max_favorable_r=round(position.r_multiple(position.max_favorable), 3),
            partial=partielle)
        self._closed.append(trade)

        position.volume = round(position.volume - quantite, 12)
        if position.volume <= 1e-12:
            self._positions.pop(position_id, None)
        else:
            self._poser_protection(position)   # le reste doit rester protege

        logger.info("CLOTURE [%s] %s %s %.6f -> %+.4f USDT | %s",
                    self.mode, position.side.value, code, quantite, profit, reason)
        return trade

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed)

    # ------------------------------------------------------------------
    def tick(self, symbol: str) -> Optional[Tick]:
        """Meilleure limite achat/vente, utile au dimensionnement."""
        try:
            data = http_get(f"{self.base}/fapi/v1/ticker/bookTicker",
                            params={"symbol": self.symbol_for(symbol)},
                            timeout=self.config.timeout)
            return Tick(time.time(), float(data["bidPrice"]), float(data["askPrice"]))
        except Exception:  # noqa: BLE001
            return None
