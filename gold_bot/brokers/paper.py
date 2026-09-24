"""Simulateur d'execution (paper trading et backtest).

Reproduit ce qui compte vraiment pour la fidelite d'un test :
  - on paie le spread a l'entree ET a la sortie,
  - le stop et l'objectif sont evalues sur la meche de la bougie, pas sur
    la cloture (sinon les resultats sont artificiellement bons),
  - un slippage optionnel degrade les executions,
  - la commission est prelevee sur le notionnel.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from ..core import Candle, ClosedTrade, Position, Side, Tick
from ..universe import Instrument
from .base import AccountInfo, Broker, BrokerError, new_position_id

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PaperConfig:
    start_balance: float = 1000.0
    currency: str = "EUR"
    commission_per_lot: float = 0.0      # commission fixe par lot
    commission_pct: float = 0.0025       # 0.25 % taker Bitvavo par cote
    slippage_atr: float = 0.05           # slippage en fraction d'ATR
    leverage: float = 1.0


class PaperBroker(Broker):
    """Compte simule, avec la meme interface que l'execution reelle."""

    name = "paper"
    is_live = False

    def __init__(self, config: Optional[PaperConfig] = None) -> None:
        self.config = config or PaperConfig()
        self.balance = self.config.start_balance
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = {}
        self._closed: list[ClosedTrade] = []
        self._prices: dict[str, Tick] = {}
        self._atr: dict[str, float] = {}

    # ---------------------------------------------------------------
    def connect(self) -> bool:
        logger.info("simulateur pret : %.2f %s", self.balance, self.config.currency)
        return True

    def set_price(self, symbol: str, tick: Tick, atr: float = 0.0) -> None:
        """Injecte la cotation courante (le simulateur n'a pas de flux propre)."""
        self._prices[symbol] = tick
        if atr > 0:
            self._atr[symbol] = atr

    def floating_pnl(self) -> float:
        total = 0.0
        for pos in self._positions.values():
            tick = self._prices.get(pos.symbol)
            inst = self._instruments.get(pos.symbol)
            if not tick or not inst:
                continue
            price = tick.exit_price_for(pos.side)
            total += pos.side.sign * (price - pos.entry_price) * inst.value_per_price_unit(pos.volume)
        return total

    def account(self) -> AccountInfo:
        floating = self.floating_pnl()
        equity = self.balance + floating
        margin = sum(
            pos.entry_price * self._instruments[pos.symbol].contract_size * pos.volume / self.config.leverage
            for pos in self._positions.values() if pos.symbol in self._instruments
        )
        return AccountInfo(equity=equity, balance=self.balance, currency=self.config.currency,
                           margin_used=margin, margin_free=max(0.0, equity - margin),
                           leverage=self.config.leverage)

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def reprendre(self, position: Position) -> bool:
        """Redeclare une position memorisee apres un redemarrage.

        Sans ceci (l'implementation par defaut de `Broker.reprendre` rend
        toujours False), une simulation qui redemarre abandonne
        silencieusement toute position ouverte -- ni trailing, ni
        break-even, ni cloture ne lui arrivent plus jamais, exactement le
        piege deja rencontre avec le vrai courtier Bitvavo sur un
        instrument absent du catalogue statique. Trouve le 18 sept. en
        redemarrant `robot-demo.service` pour deployer un correctif : 10
        positions simulees abandonnees d'un coup.

        Le solde reste approximatif apres reprise (les frais deja payes
        sur ces positions ne sont pas retranches, `self.balance` repart de
        `start_balance` a chaque demarrage) -- acceptable pour un capital
        purement virtuel, l'ecart se limite a quelques centimes de frais.
        """
        self._positions[position.id] = position
        return True

    # ---------------------------------------------------------------
    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        tick = self._prices.get(instrument.symbol)
        if tick is None:
            raise BrokerError(f"aucune cotation pour {instrument.symbol}")
        if lots <= 0:
            raise BrokerError("volume nul")
        if not stop_loss:
            raise BrokerError("ouverture refusee : stop-loss obligatoire")

        slip = self.config.slippage_atr * self._atr.get(instrument.symbol, 0.0)
        price = tick.price_for(side) + side.sign * slip

        acc = self.account()
        notional = price * instrument.contract_size * lots
        if notional / self.config.leverage > acc.margin_free:
            raise BrokerError(f"marge insuffisante ({notional / self.config.leverage:.2f} requis, "
                              f"{acc.margin_free:.2f} disponible)")

        cost = self.config.commission_per_lot * lots + notional * self.config.commission_pct
        self.balance -= cost

        pos = Position(
            id=new_position_id(), symbol=instrument.symbol, side=side, volume=lots,
            entry_price=round(price, instrument.digits),
            stop_loss=round(stop_loss, instrument.digits),
            take_profit=round(take_profit, instrument.digits),
            opened_at=tick.ts or time.time(), comment=comment,
        )

        # UN SECOND ACHAT SUR LE MEME ACTIF EST UN ETAGE, PAS UNE 2e LIGNE.
        #
        # Au comptant, Bitvavo ne connait qu'un AVOIR par actif, jamais
        # deux lignes : le vrai courtier fusionne donc (voir
        # `bitvavo.py`, « le modele juste au comptant »). Le simulateur,
        # lui, empilait des positions independantes.
        #
        # Ce n'etait pas un detail d'affichage. Constate le 19 septembre
        # sur la demo : AVAX, NEO et OP portaient chacun DEUX lignes,
        # la seconde achetee plus cher — du pyramidage manuel du livre —
        # et toutes affichaient « etage 1 ». Trois consequences :
        #
        #   - l'application montrait « etage 1 » partout, et l'operateur
        #     a demande pourquoi aucune position ne pyramidait ;
        #   - la mesure « combien rapporte une position selon ses
        #     etages » — celle qui a justifie le pyramidage illimite —
        #     ne pouvait rendre QUE des etages 1, dans le rejeu comme en
        #     demo. Elle etait donc inexploitable ;
        #   - surtout, deux lignes = DEUX stops independants, quand le
        #     vrai robot n'en a qu'un, pose sous la derniere unite et
        #     couvrant tout l'avoir. La demo ne mesurait pas le risque
        #     que le compte reel porterait.
        #
        # La demo doit vivre ce que le reel vivra, sur le mecanisme dont
        # CLAUDE.md dit qu'il fait tout le benefice.
        existante = next((p for p in self._positions.values()
                          if p.symbol == instrument.symbol and p.side is side),
                         None)
        if existante is not None:
            return self._fusionner(existante, pos, instrument)

        self._positions[pos.id] = pos
        self._instruments[instrument.symbol] = instrument
        logger.info("[SIMU] ouverture %s %s %.4f lots @ %.5f SL %.5f TP %.5f (frais %.2f)",
                    side.value, instrument.symbol, lots, pos.entry_price,
                    pos.stop_loss, pos.take_profit, cost)
        return pos

    def _fusionner(self, existante: Position, ajout: Position,
                   instrument: Instrument) -> Position:
        """Ajoute un etage a une pyramide : meme calcul que le vrai courtier.

        Toute divergence avec `bitvavo._fusionner` ferait mesurer a la
        demo une autre mecanique que celle du compte reel — c'est
        precisement ce que ce simulateur est cense eviter.
        """
        total = existante.volume + ajout.volume
        moyenne = ((existante.entry_price * existante.volume
                    + ajout.entry_price * ajout.volume) / total
                   if total > 0 else existante.entry_price)
        # Le stop ne DESCEND jamais : un etage pose plus haut remonte la
        # protection de tout l'avoir, jamais l'inverse.
        nouveau_stop = max(ajout.stop_loss, existante.stop_loss) \
            if existante.side is Side.BUY \
            else min(ajout.stop_loss, existante.stop_loss)
        existante.volume = round(total, 10)
        existante.entry_price = round(moyenne, instrument.digits)
        existante.stop_loss = round(nouveau_stop, instrument.digits)
        existante.take_profit = ajout.take_profit
        existante.etages += 1
        # Le prix de CETTE unite, pas la moyenne : c'est lui qui sert de
        # reference au prochain espacement.
        existante.derniere_entree = ajout.entry_price
        # LE R DOIT SUIVRE LA POSITION, SINON TOUTES LES REGLES MENTENT :
        # point mort a 0,7 R, suiveur a 1,1 R, stop temporel sous 0,4 R.
        existante.initial_risk = abs(existante.entry_price - existante.stop_loss)
        # LE RISQUE ENGAGE S'ACCUMULE, IL NE SE RECALCULE PAS.
        #
        # La ligne au-dessus est volontaire : le R courant doit suivre la
        # position pour que le point mort, le suiveur et le stop temporel
        # restent justes. Mais elle rend `initial_risk` inutilisable pour
        # MESURER : un etage ne s'ajoute qu'une fois le stop au-dessus du
        # prix moyen, donc la distance s'effondre et le R explose (RUNE,
        # 25 sept. : R = 46 pour 95 EUR).
        #
        # Ici on ajoute ce que CE etage a mis en jeu, au moment ou il le
        # met en jeu. La somme reste le vrai denominateur de la
        # performance, quoi qu'il advienne du stop ensuite.
        existante.risque_eur_engage += abs(
            ajout.volume * (ajout.entry_price - ajout.stop_loss))
        existante.breakeven_done = False
        self._instruments[instrument.symbol] = instrument
        logger.info("[SIMU] etage %d sur %s : %.4f lots @ %.5f "
                    "-> moyenne %.5f, stop %.5f",
                    existante.etages, existante.symbol, ajout.volume,
                    ajout.entry_price, existante.entry_price,
                    existante.stop_loss)
        return existante

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        pos = self._positions.get(position_id)
        if pos is None:
            return False
        if stop_loss is not None:
            pos.stop_loss = stop_loss
        if take_profit is not None:
            pos.take_profit = take_profit
        return True

    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        pos = self._positions.get(position_id)
        if pos is None:
            return None
        inst = self._instruments.get(pos.symbol)
        tick = self._prices.get(pos.symbol)
        if inst is None or tick is None:
            raise BrokerError(f"cotation manquante pour cloturer {pos.symbol}")

        slip = self.config.slippage_atr * self._atr.get(pos.symbol, 0.0)
        price = tick.exit_price_for(pos.side) - pos.side.sign * slip
        return self._settle(pos, price, volume, reason, tick.ts or time.time())

    # ---------------------------------------------------------------
    def _settle(self, pos: Position, price: float, volume: Optional[float],
                reason: str, ts: float) -> ClosedTrade:
        inst = self._instruments[pos.symbol]
        vol = min(volume or pos.volume, pos.volume)
        is_partial = vol < pos.volume - 1e-9
        profit = pos.side.sign * (price - pos.entry_price) * inst.value_per_price_unit(vol)
        cost = (self.config.commission_per_lot * vol
                + price * inst.contract_size * vol * self.config.commission_pct)
        profit -= cost
        self.balance += profit

        trade = ClosedTrade(
            position_id=pos.id, symbol=pos.symbol, side=pos.side, volume=vol,
            entry_price=pos.entry_price, exit_price=round(price, inst.digits),
            opened_at=pos.opened_at, closed_at=ts, profit=round(profit, 2),
            r_multiple=round(pos.r_multiple(price), 3), reason=reason,
            tp_extensions=pos.tp_extensions,
            max_favorable_r=round(pos.r_multiple(pos.max_favorable), 3),
            partial=is_partial,
            etages=int(getattr(pos, "etages", 1) or 1),
            # Une sortie PARTIELLE n'engage qu'une part du risque :
            # on n'attribue a ce trade que la fraction du risque qui
            # correspond au volume sorti, sinon la somme des parts
            # depasserait le risque reellement pris.
            risque_eur=round(
                getattr(pos, "risque_eur_engage", 0.0)
                * (vol / pos.volume if pos.volume > 0 else 1.0), 6),
        )
        self._closed.append(trade)

        pos.volume = round(pos.volume - vol, 8)
        if pos.volume <= 1e-9:
            self._positions.pop(pos.id, None)
            logger.info("[SIMU] cloture %s %s @ %.5f -> %+.2f %s (%.2fR) | %s",
                        pos.side.value, pos.symbol, price, profit,
                        self.config.currency, trade.r_multiple, reason)
        else:
            logger.info("[SIMU] cloture partielle %s %.4f lots @ %.5f -> %+.2f %s | %s",
                        pos.symbol, vol, price, profit, self.config.currency, reason)
        return trade

    # ---------------------------------------------------------------
    def process_candle(self, symbol: str, candle: Candle) -> list[ClosedTrade]:
        """Fait vivre les positions sur une bougie (backtest).

        On teste le stop AVANT l'objectif : c'est l'hypothese prudente quand
        la bougie touche les deux, elle evite de surestimer les resultats.
        """
        out: list[ClosedTrade] = []
        for pos in list(self._positions.values()):
            if pos.symbol != symbol:
                continue
            inst = self._instruments.get(symbol)
            if inst is None:
                continue
            if pos.side is Side.BUY:
                pos.track(candle.high)
                if candle.low <= pos.stop_loss:
                    out.append(self._settle(pos, pos.stop_loss, None, "stop-loss touche", candle.ts))
                    continue
                if candle.high >= pos.take_profit:
                    out.append(self._settle(pos, pos.take_profit, None, "objectif atteint", candle.ts))
            else:
                pos.track(candle.low)
                if candle.high >= pos.stop_loss:
                    out.append(self._settle(pos, pos.stop_loss, None, "stop-loss touche", candle.ts))
                    continue
                if candle.low <= pos.take_profit:
                    out.append(self._settle(pos, pos.take_profit, None, "objectif atteint", candle.ts))
        return out

    def check_tick(self, symbol: str, tick: Tick) -> list[ClosedTrade]:
        """Verifie SL/TP sur une cotation (mode temps reel simule)."""
        self._prices[symbol] = tick
        out: list[ClosedTrade] = []
        for pos in list(self._positions.values()):
            if pos.symbol != symbol:
                continue
            price = tick.exit_price_for(pos.side)
            pos.track(price)
            if pos.hit_stop(price):
                out.append(self._settle(pos, pos.stop_loss, None, "stop-loss touche", tick.ts))
            elif pos.hit_target(price):
                out.append(self._settle(pos, pos.take_profit, None, "objectif atteint", tick.ts))
        return out

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed)

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument
