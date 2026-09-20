"""Rejeu de PORTEFEUILLE : tous les instruments sur UN SEUL compte.

POURQUOI CE FICHIER EXISTE
==========================

`Backtester.run` ouvre un compte neuf par instrument. `comparer.py`
l'appelle en boucle et ADDITIONNE les profits :

    for sym in symboles:
        res = Backtester(cfg).run(sym, start_balance=args.capital)
        profit += res.end_balance - res.start_balance

Chaque crypto y recoit donc le capital ENTIER et le budget de risque
ENTIER, sans jamais croiser les autres. Mesurer 70 paires ainsi revient
a supposer 70 comptes separes — pas un robot qui arbitre entre elles.

Ce n'est pas un detail de presentation. Mesure le 19 septembre sur la
demo en service : 21 positions ouvertes, 165,07 EUR de risque engage
pour un plafond de 165,00 EUR (5 % de 3 300). Le budget est plein au
centime, et le journal du robot repete « risque total deja engage
(5,00 %) » a chaque cycle. Consequence : AUCUNE position ne depasse
l'etage 1 de la pyramide, alors que la mesure qui a justifie le
pyramidage illimite donnait +39,47 EUR par trade a 7 etages et plus, et
-1,62 EUR par trade a un seul etage.

Autrement dit, le robot ne peut structurellement produire que la
categorie perdante. Le rejeu par instrument ne pouvait pas le voir : il
n'a jamais fait se concurrencer deux cryptos pour le meme euro.

CE QUE CE MODULE NE FAIT PAS
============================

Il ne remplace pas `comparer.py`. Un rejeu par instrument reste le bon
outil pour comparer deux jeux de reglages a nombre de trades egal, sans
que la concurrence entre paires brouille le signal. Celui-ci repond a
une autre question : « que donne ce reglage sur UN compte ? »
"""
from __future__ import annotations

import heapq
import logging
from dataclasses import dataclass, field
from typing import Optional

from .backtest import BacktestResult, Backtester, Prepare
from .brokers.paper import PaperBroker, PaperConfig
from .core import ClosedTrade
from .datasources import DataRegistry
from .risk import RiskManager
from .settings import BotConfig

logger = logging.getLogger(__name__)


@dataclass
class ResultatPortefeuille:
    start_balance: float = 0.0
    end_balance: float = 0.0
    par_instrument: dict[str, BacktestResult] = field(default_factory=dict)
    courbe: list[tuple[float, float]] = field(default_factory=list)
    ecartes: dict[str, str] = field(default_factory=dict)

    @property
    def trades(self) -> list[ClosedTrade]:
        out: list[ClosedTrade] = []
        for r in self.par_instrument.values():
            out.extend(r.trades)
        out.sort(key=lambda t: getattr(t, "closed_at", 0.0) or 0.0)
        return out

    def stats(self) -> dict:
        reels = [t for t in self.trades if not t.partial]
        if not reels:
            return {"trades": 0, "instruments": len(self.par_instrument),
                    "resultat": round(self.end_balance - self.start_balance, 2)}
        gagnants = [t for t in reels if t.profit > 0]
        pic, creux, eq = self.start_balance, 0.0, self.start_balance
        for ts, e in self.courbe:
            pic = max(pic, e)
            creux = max(creux, pic - e)
        par_etage = self.resultat_par_etage()
        return {
            "instruments": len(self.par_instrument),
            "trades": len(reels),
            "taux_reussite_pct": round(len(gagnants) / len(reels) * 100, 1),
            "resultat": round(self.end_balance - self.start_balance, 2),
            "rendement_pct": round(
                (self.end_balance / self.start_balance - 1) * 100, 2)
            if self.start_balance else 0.0,
            "esperance_R": round(
                sum(t.r_multiple for t in reels) / len(reels), 3),
            "drawdown_max_pct": round(creux / self.start_balance * 100, 2)
            if self.start_balance else 0.0,
            "par_etage": par_etage,
        }

    def resultat_par_etage(self) -> dict[int, dict]:
        """Combien rapporte une position selon le nombre d'etages atteints.

        C'est LA lecture qui a justifie le pyramidage illimite les 9 et
        12 septembre. La refaire ici dit si le robot peut encore
        atteindre les etages qui payent, une fois le budget partage.
        """
        out: dict[int, dict] = {}
        for t in self.trades:
            if t.partial:
                continue
            e = int(getattr(t, "etages", 1) or 1)
            d = out.setdefault(e, {"trades": 0, "gagnants": 0, "profit": 0.0})
            d["trades"] += 1
            d["gagnants"] += 1 if t.profit > 0 else 0
            d["profit"] += t.profit
        for e, d in out.items():
            d["profit"] = round(d["profit"], 2)
            d["par_trade"] = round(d["profit"] / d["trades"], 2) if d["trades"] else 0.0
        return dict(sorted(out.items()))


class BacktestPortefeuille:
    """Rejoue plusieurs instruments qui se PARTAGENT un compte."""

    def __init__(self, config: Optional[BotConfig] = None,
                 registry: Optional[DataRegistry] = None,
                 autorise_vente: Optional[bool] = None) -> None:
        self.rejeu = Backtester(config, registry=registry,
                                autorise_vente=autorise_vente)
        self.config = self.rejeu.config

    def run(self, symbols: list[str], bars: int = 1500,
            start_balance: float = 1000.0,
            decalage: int = 0) -> ResultatPortefeuille:
        """`decalage` : reculer de N bougies pour mesurer HORS ECHANTILLON.

        Un reglage choisi sur une periode y parait toujours bon. La seule
        facon de savoir s'il vaut quelque chose est de le rejouer sur une
        periode qu'il n'a jamais vue.
        """
        cfg = self.config
        broker = PaperBroker(PaperConfig(
            start_balance=start_balance, currency=cfg.engine.currency,
            commission_pct=cfg.risk.commission_pct))
        broker.connect()
        risk = RiskManager(cfg.risk)

        resultat = ResultatPortefeuille(start_balance=start_balance)
        prets: list[Prepare] = []
        for sym in symbols:
            try:
                prets.append(self.rejeu.preparer(
                    sym, bars, start_balance, broker=broker, risk=risk,
                    decalage=decalage))
            except Exception as exc:  # noqa: BLE001
                resultat.ecartes[sym.upper()] = str(exc)[:80]
                logger.info("ecarte du portefeuille : %s (%s)", sym,
                            str(exc)[:80])

        # LE DEFILEMENT EST CHRONOLOGIQUE, TOUS INSTRUMENTS CONFONDUS.
        #
        # Un tas ordonne par horodatage : on avance toujours celui qui est
        # le plus en retard. Sans cela, BTC vivrait son historique entier
        # avant qu'ADA ne commence — ils ne se disputeraient jamais le
        # meme euro, et on aurait refait, en plus lent, le rejeu par
        # instrument qu'on cherche precisement a depasser.
        #
        # L'index sert a departager deux bougies du meme horodatage. Il
        # rend l'ordre DETERMINISTE, ce qui compte : a budget sature,
        # l'instrument servi en premier prend la place, donc un ordre
        # instable rendrait la mesure irreproductible.
        tas: list[tuple[float, int, Prepare]] = []
        for i, p in enumerate(prets):
            ts = next(p.parcours, None)
            if ts is not None:
                heapq.heappush(tas, (ts, i, p))

        dernier_ts = 0.0
        while tas:
            ts, i, p = heapq.heappop(tas)
            try:
                suivant = next(p.parcours)
            except StopIteration:
                continue
            heapq.heappush(tas, (suivant, i, p))
            if ts > dernier_ts:
                dernier_ts = ts
                resultat.courbe.append((ts, round(broker.account().equity, 2)))

        for pos in list(broker.positions()):
            t = broker.close_position(pos.id, None, "fin de periode de test")
            if t:
                for p in prets:
                    if p.instrument.symbol == t.symbol:
                        p.resultat.trades.append(t)
                        break

        for p in prets:
            p.resultat.end_balance = broker.account().balance
            resultat.par_instrument[p.instrument.symbol] = p.resultat
        resultat.end_balance = broker.account().balance
        resultat.courbe.append((dernier_ts, round(resultat.end_balance, 2)))
        return resultat
