"""Runtime scalping commun pour Bitvavo Spot et IBKR.

Le moteur de base ne prenait que `result.best`. Cette couche conserve tous les
coupe-circuits du TradingEngine mais peut executer plusieurs opportunites
independantes dans le meme cycle tant que le budget de risque et le nombre de
positions le permettent.
"""
from __future__ import annotations

import logging
import math
import os

from .core import Side
from .engine import TradingEngine
from .scalping_engine import ContinuousScalpingMixin
from .universe import Instrument
from .brokers import (BitvavoConfig, BitvavoMarginBroker, BrokerError,
                      IBKRBroker)
from .brokers.ibkr_hardened import HardenedIBKRBroker

logger = logging.getLogger(__name__)


class MultiEntryScalpingMixin(ContinuousScalpingMixin):
    """Execute plusieurs signaux valides, sans depasser le budget de risque."""

    # Un spread trop large est une propriete de LIQUIDITE, pas une humeur
    # du moment : il tient des heures. Re-telecharger l'historique complet
    # d'un instrument pour lui opposer le meme refus a chaque cycle gaspille
    # le quota de la plateforme et allonge le scan.
    SOMMEIL_SPREAD_SECONDES = 1800.0

    def _endormir_les_spreads_trop_larges(self, result) -> None:
        """Met de cote les instruments refuses au spread.

        Mesure en production : 61 instruments sur 70 refuses au spread, et
        un scan de 26,7 secondes pour une cadence reglee a 10. Les 61 sont
        re-interroges a chaque tour pour un refus previsible.

        Le sommeil est court (30 min) et non definitif : le spread
        s'elargit sur annonce et se resserre ensuite, et un instrument
        ecarte pour de bon appauvrirait l'univers sans qu'on s'en rende
        compte.
        """
        endormis = []
        for ev in result.evaluations:
            if ev.valid:
                continue
            rates = [g.name for g in ev.failed_gates()]
            # Uniquement quand le spread est le SEUL motif : un instrument
            # refuse aussi ailleurs peut redevenir valide sans que sa
            # liquidite ait change.
            if rates == ["spread"]:
                self.scanner.sleep_symbol(
                    ev.symbol, self.SOMMEIL_SPREAD_SECONDES,
                    "spread trop large pour l'unite de temps")
                endormis.append(ev.symbol)
        if endormis:
            logger.info("%d instrument(s) mis de cote %.0f min sur le spread : %s",
                        len(endormis), self.SOMMEIL_SPREAD_SECONDES / 60,
                        ", ".join(endormis[:8])
                        + (f", … (+{len(endormis) - 8})" if len(endormis) > 8 else ""))

    def _look_for_entry(self) -> None:
        positions = self.broker.positions()
        allowed, why = self.risk.can_trade(positions)
        if not allowed:
            logger.debug("pas de recherche : %s", why)
            return
        stop, stop_why = self.objectives.should_stop_trading()
        if stop:
            logger.info("recherche suspendue : %s", stop_why)
            return

        bonus = self.objectives.score_threshold_bonus()
        held = {p.symbol for p in positions}
        sens = None if getattr(self.broker, "supports_short", True) else {Side.BUY}

        def exposure_ok(inst):
            current = self.broker.positions()
            # Pas de hedging/pyramiding automatique dans cette couche : on
            # veut multiplier les opportunites, pas multiplier le risque sur
            # le meme actif.
            return self.risk.check_exposure(inst, Side.BUY, current, self.universe.get)

        result = self.scanner.scan(score_bonus=bonus, exclude=held,
                                   allow=exposure_ok, allowed_sides=sens)
        self._endormir_les_spreads_trop_larges(result)
        valid = sorted(result.valid_ones(), key=lambda e: (e.score, e.rr), reverse=True)
        logger.info("%s", result.summary())
        if self.config.engine.verbose_scan:
            for line in self.scanner.report(result, verbose=True)[1:]:
                logger.info("%s", line)

        max_new = max(1, self.capital_tier()["positions_simultanees"])
        opened = 0
        for ev in valid:
            if opened >= max_new:
                break
            current = self.broker.positions()
            allowed, why = self.risk.can_trade(current)
            if not allowed:
                logger.info("recherche multi-entrees arretee : %s", why)
                break
            if ev.symbol in {p.symbol for p in current}:
                continue
            before = len(current)
            self._execute(ev)
            after = len(self.broker.positions())
            if after > before:
                opened += 1
        if opened:
            logger.info("scalping multi-entrees : %d nouvelle(s) position(s)", opened)


class DualScalpingEngine(MultiEntryScalpingMixin, TradingEngine):
    """Moteur commun, avec selection du broker Bitvavo ou IBKR."""

    def _broker_bitvavo_margin(self):
        """Bitvavo avec vente a decouvert.

        Le compte au comptant ne sait qu'acheter : une alerte de vente
        parfaitement valide y est jetee avant meme d'etre evaluee, ce qui
        supprime la moitie des occasions dans un marche qui baisse. Bitvavo
        ouvre desormais la vente a decouvert sur une quinzaine d'actifs.

        Le levier reste celui de la configuration — 1x par defaut. Vendre a
        decouvert a 1x n'est PAS du levier au sens ou l'entendait la decision
        de l'operateur : le notionnel ne depasse pas le capital, donc rien
        n'est multiplie. Seul le sens change. Un levier superieur a 1
        reintroduirait la multiplication des pertes, et la configuration
        seule peut le decider.
        """
        bv = BitvavoConfig.from_env()
        if self.config.engine.dry_run:
            bv.dry_run = True
        plafond = float(self.config.risk.max_leverage)
        os.environ.setdefault("BITVAVO_MARGIN_ENABLED", "1")
        # Le broker lit son plafond dans l'environnement ; la configuration
        # de risque reste souveraine et ne peut pas etre contredite par un
        # defaut a 10x.
        os.environ["BITVAVO_MARGIN_LEVERAGE"] = f"{max(1.0, plafond):.4f}"

        broker = BitvavoMarginBroker(bv)
        if not broker.connect():
            raise BrokerError(
                "compte Bitvavo avec vente a decouvert indisponible : "
                + (getattr(broker, "_last_error", "") or "raison inconnue")
                + ". La vente a decouvert doit etre activee sur le compte "
                  "Bitvavo (elle demande une acceptation des conditions de "
                  "marge). A defaut, repasser engine.broker a \"bitvavo\" : "
                  "le robot n'achetera plus que a la hausse.")
        self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker

    def _build_broker(self):
        if self.config.engine.broker == "bitvavo_margin":
            return self._broker_bitvavo_margin()
        if self.config.engine.broker != "ibkr":
            return super()._build_broker()

        # Les instruments IBKR peuvent etre declares par IBKR_SYMBOLS et
        # detailles dans IBKR_CONTRACTS. On les ajoute au meme univers afin
        # que le scanner existant puisse les analyser.
        symbols = [s.strip().upper() for s in os.getenv("IBKR_SYMBOLS", "").split(",") if s.strip()]
        for sym in symbols:
            if self.universe.get(sym):
                continue
            spec = IBKRBroker._load_specs().get(sym, {})
            sec_type = str(spec.get("secType", "STK")).upper()
            asset_class = "forex" if sec_type == "CASH" else "index"
            quote = str(spec.get("currency", self.config.engine.currency)).upper()
            self.universe.add(Instrument(
                symbol=sym, asset_class=asset_class, digits=int(spec.get("digits", 5 if asset_class == "forex" else 2)),
                contract_size=float(spec.get("contract_size", 1.0)), min_lot=float(spec.get("min_lot", 0.001)),
                lot_step=float(spec.get("lot_step", 0.001)), max_lot=float(spec.get("max_lot", 1000000.0)),
                round_step=0.0, typical_spread=0.0, max_spread=math.inf,
                sessions=(), weekend=False, priority=float(spec.get("priority", 1.0)),
                quote_currency=quote, correlation_group=str(spec.get("correlation_group", f"ibkr_{sym}")),
            ))

        # Broker DURCI, pas le broker nu : c'est lui qui porte la
        # reconnexion automatique au Gateway et le port 4001 (reel) au lieu
        # de 4002 (papier). Le moteur tourne des jours d'affilee ; un Gateway
        # qui se deconnecte la nuit doit se rattraper tout seul.
        broker = HardenedIBKRBroker()
        if self.config.engine.dry_run:
            broker.live_enabled = False

        # Le tri de l'univers ne lit que la table des contrats declares : il
        # ne demande rien au Gateway et peut donc se faire hors connexion.
        self._filtrer_univers_sur_le_broker(broker)

        # `register_instrument` interroge le Gateway (reqContractDetails).
        # L'appeler ici, AVANT que `start()` n'appelle `broker.connect()`,
        # produisait un « IBKR non connecte » par instrument, avale par le
        # try/except du broker : cinq avertissements au demarrage et zero
        # contrat en cache. On repousse donc l'enregistrement juste apres la
        # connexion reussie.
        connect_nu = broker.connect
        univers = self.universe

        def connect_puis_enregistrer() -> bool:
            ok = connect_nu()
            if ok:
                for inst in univers:
                    broker.register_instrument(inst)
            return ok

        broker.connect = connect_puis_enregistrer
        return broker
