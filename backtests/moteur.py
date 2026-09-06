#!/usr/bin/env python3
"""Harnais de rejeu portefeuille — Turtle et variantes.

ECRIT A PART, ET C'EST VOULU. Le `Backtester` du robot execute au cours
de CLOTURE de la bougie qui produit le signal. Ici on veut la regle
stricte demandee : signal calcule en t, execute a l'OUVERTURE de t+1.
Reutiliser le moteur live aurait aussi impose toute sa pile de filtres,
qu'on ne cherche pas a mesurer.

Ce harnais simule UN portefeuille commun a toutes les paires — pas 70
rejeux independants qu'on additionnerait. La difference est majeure : le
capital est partage, les places sont limitees, et un trade refuse faute
de place est un trade qui n'existe pas. Additionner des rejeux separes
gonfle mecaniquement le resultat.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

from donnees import Bougie

# --- Couts reels Bitvavo -------------------------------------------------
# Taker 0,25 % par cote (palier de base, < 100 kEUR/mois). Le spread des
# alts en EUR tourne autour de 0,10 % ; on le compte comme un glissement
# subi a l'entree ET a la sortie, jamais en notre faveur.
COMMISSION = 0.0025
SPREAD = 0.0010


@dataclass
class Position:
    paire: str
    entree: float
    lots: float
    stop: float
    ouvert_le: float
    plus_haut: float
    risque_initial: float          # en EUR, la distance au stop x lots


@dataclass
class Trade:
    paire: str
    ouvert_le: float
    ferme_le: float
    entree: float
    sortie: float
    lots: float
    pnl: float                     # net de frais
    frais: float
    motif: str

    @property
    def jours(self) -> float:
        return (self.ferme_le - self.ouvert_le) / 86400


@dataclass
class Reglages:
    """Parametres FIGES. Aucune optimisation, aucun grid search."""
    capital: float = 1000.0
    risque_pct: float = 0.006          # 0,6 % — palier « preuve » du robot
    max_positions: int = 6
    risque_total_max: float = 0.035    # 3,5 %
    canal_entree: tuple[int, ...] = (20,)
    vote_minimum: int = 1              # 2 = majorite sur 3 horizons
    atr_periode: int = 14
    stop_atr: float = 1.6
    trail_atr: float = 2.2
    trail_depart_r: float = 1.1
    stop_temporel_jours: int = 12
    # Filtres de la variante C
    filtre_momentum: bool = False      # top tiers du momentum 90 j
    filtre_liquidite: bool = False     # au-dessus de la mediane de volume
    # Filtre de la variante B
    filtre_regime_btc: bool = False    # BTC au-dessus de sa MM200
    # Robustesse
    multiplicateur_couts: float = 1.0


def atr(serie: list[Bougie], i: int, n: int) -> float:
    """ATR de Wilder simplifie sur les n bougies precedant i (i exclu)."""
    if i < n + 1:
        return 0.0
    trs = []
    for k in range(i - n, i):
        h, b, pc = serie[k].high, serie[k].low, serie[k - 1].close
        trs.append(max(h - b, abs(h - pc), abs(b - pc)))
    return sum(trs) / len(trs)


def rejouer(donnees: dict[str, list[Bougie]], r: Reglages) -> dict:
    """Simule le portefeuille jour par jour sur l'ensemble des paires."""
    comm = COMMISSION * r.multiplicateur_couts
    spread = SPREAD * r.multiplicateur_couts

    # Calendrier commun : toutes les journees ou au moins une paire cote.
    jours = sorted({b.ts for s in donnees.values() for b in s})
    index = {p: {b.ts: i for i, b in enumerate(s)} for p, s in donnees.items()}

    capital = r.capital
    ouvertes: dict[str, Position] = {}
    trades: list[Trade] = []
    courbe: list[tuple[float, float]] = []
    jours_exposes = 0
    frais_total = 0.0

    for t in jours:
        # ---- 1. Gestion des positions ouvertes, a l'OUVERTURE du jour ----
        for paire in list(ouvertes):
            pos = ouvertes[paire]
            i = index[paire].get(t)
            if i is None:
                continue
            b = donnees[paire][i]

            sortie = motif = None
            # Le stop est teste sur le plus-bas du jour : s'il est touche,
            # on sort AU STOP, pas au plus bas — mais jamais mieux.
            if b.low <= pos.stop:
                sortie, motif = pos.stop, "stop"
            elif (t - pos.ouvert_le) / 86400 >= r.stop_temporel_jours and \
                    b.close <= pos.entree:
                sortie, motif = b.close, "stop temporel"

            if sortie is not None:
                px = sortie * (1 - spread)
                brut = (px - pos.entree) * pos.lots
                f = (pos.entree + px) * pos.lots * comm
                capital += brut - f
                frais_total += f
                trades.append(Trade(paire, pos.ouvert_le, t, pos.entree, px,
                                    pos.lots, brut - f, f, motif))
                del ouvertes[paire]
                continue

            # Stop suiveur : il ne descend jamais.
            pos.plus_haut = max(pos.plus_haut, b.high)
            a = atr(donnees[paire], i, r.atr_periode)
            if a > 0 and pos.risque_initial > 0:
                gain_r = (pos.plus_haut - pos.entree) * pos.lots / pos.risque_initial
                if gain_r >= r.trail_depart_r:
                    suiveur = pos.plus_haut - r.trail_atr * a
                    pos.stop = max(pos.stop, suiveur)

        if ouvertes:
            jours_exposes += 1

        # ---- 2. Regime de marche (variante B) ----
        regime_ok = True
        if r.filtre_regime_btc:
            btc = donnees.get("BTC")
            i = index.get("BTC", {}).get(t) if btc else None
            if i is None or i < 200:
                regime_ok = False
            else:
                mm200 = sum(x.close for x in btc[i - 200:i]) / 200
                regime_ok = btc[i - 1].close > mm200

        # ---- 3. Univers eligible (variante C) ----
        eligibles = list(donnees)
        if r.filtre_momentum or r.filtre_liquidite:
            scores, volumes = {}, {}
            for p, s in donnees.items():
                i = index[p].get(t)
                if i is None or i < 91:
                    continue
                if s[i - 91].close > 0:
                    scores[p] = s[i - 1].close / s[i - 91].close - 1
                volumes[p] = sum(x.close * x.volume for x in s[max(0, i - 30):i]) / 30
            if r.filtre_liquidite and volumes:
                med = sorted(volumes.values())[len(volumes) // 2]
                scores = {p: v for p, v in scores.items()
                          if volumes.get(p, 0) >= med}
            if r.filtre_momentum and scores:
                classe = sorted(scores, key=lambda p: -scores[p])
                scores = {p: scores[p] for p in classe[:max(1, len(classe) // 3)]}
            eligibles = list(scores)

        # ---- 4. Recherche d'entrees, executees a l'OUVERTURE de t+1 ----
        if regime_ok and len(ouvertes) < r.max_positions:
            risque_engage = sum(p.risque_initial for p in ouvertes.values())
            candidats = []
            for paire in eligibles:
                if paire in ouvertes:
                    continue
                i = index[paire].get(t)
                besoin = max(r.canal_entree) + 1
                if i is None or i < besoin or i + 1 >= len(donnees[paire]):
                    continue
                s = donnees[paire]
                # SIGNAL EN t : la cloture de t depasse-t-elle le canal ?
                # Le canal exclut la bougie t elle-meme (pas de look-ahead).
                votes = sum(1 for n in r.canal_entree
                            if s[i].close > max(x.high for x in s[i - n:i]))
                if votes >= r.vote_minimum:
                    candidats.append((paire, i))

            for paire, i in candidats:
                if len(ouvertes) >= r.max_positions:
                    break
                s = donnees[paire]
                a = atr(s, i, r.atr_periode)
                if a <= 0:
                    continue
                # EXECUTION EN t+1 A L'OUVERTURE, glissement subi.
                px = s[i + 1].open * (1 + spread)
                stop = px - r.stop_atr * a
                distance = px - stop
                if distance <= 0:
                    continue
                risque_eur = capital * r.risque_pct
                if risque_engage + risque_eur > capital * r.risque_total_max:
                    continue
                lots = risque_eur / distance
                notionnel = lots * px
                if notionnel < 5.0:                    # ticket minimum Bitvavo
                    continue
                dispo = capital - sum(p.lots * p.entree for p in ouvertes.values())
                if notionnel > dispo:
                    lots = dispo / px
                    notionnel = lots * px
                    if notionnel < 5.0:
                        continue
                ouvertes[paire] = Position(paire, px, lots, stop, s[i + 1].ts,
                                           s[i + 1].high,
                                           (px - stop) * lots)
                risque_engage += (px - stop) * lots

        # ---- 5. Valeur du portefeuille ----
        valeur = capital
        for paire, pos in ouvertes.items():
            i = index[paire].get(t)
            if i is not None:
                valeur += (donnees[paire][i].close - pos.entree) * pos.lots
        courbe.append((t, valeur))

    # Cloture de ce qui reste, au dernier cours connu.
    for paire, pos in list(ouvertes.items()):
        b = donnees[paire][-1]
        px = b.close * (1 - spread)
        brut = (px - pos.entree) * pos.lots
        f = (pos.entree + px) * pos.lots * comm
        capital += brut - f
        frais_total += f
        trades.append(Trade(paire, pos.ouvert_le, b.ts, pos.entree, px,
                            pos.lots, brut - f, f, "fin de periode"))

    return {"trades": trades, "courbe": courbe, "frais": frais_total,
            "jours_exposes": jours_exposes, "jours_total": len(jours),
            "capital_final": courbe[-1][1] if courbe else r.capital,
            "reglages": r}


# ---------------------------------------------------------------------
# Metriques
# ---------------------------------------------------------------------
def metriques(res: dict, depuis: float = 0.0, jusqu_a: float = 9e18) -> dict:
    courbe = [(t, v) for t, v in res["courbe"] if depuis <= t <= jusqu_a]
    trades = [x for x in res["trades"] if depuis <= x.ferme_le <= jusqu_a]
    if len(courbe) < 2:
        return {"trades": 0}

    v0, v1 = courbe[0][1], courbe[-1][1]
    annees = (courbe[-1][0] - courbe[0][0]) / 86400 / 365.25
    rendement = v1 / v0 - 1 if v0 else 0.0
    cagr = ((v1 / v0) ** (1 / annees) - 1) if v0 > 0 and annees > 0 and v1 > 0 else 0.0

    quotidiens = [courbe[i][1] / courbe[i - 1][1] - 1
                  for i in range(1, len(courbe)) if courbe[i - 1][1] > 0]
    if len(quotidiens) > 1:
        moy = sum(quotidiens) / len(quotidiens)
        ec = math.sqrt(sum((x - moy) ** 2 for x in quotidiens) / (len(quotidiens) - 1))
        sharpe = (moy / ec * math.sqrt(365)) if ec > 0 else 0.0
    else:
        sharpe = 0.0

    pic = dd = 0.0
    for _, v in courbe:
        pic = max(pic, v)
        if pic > 0:
            dd = max(dd, (pic - v) / pic)

    gagnants = [x for x in trades if x.pnl > 0]
    return {
        "rendement_pct": rendement * 100,
        "cagr_pct": cagr * 100,
        "sharpe": sharpe,
        "max_dd_pct": dd * 100,
        "trades": len(trades),
        "reussite_pct": 100 * len(gagnants) / len(trades) if trades else 0.0,
        "pnl_moyen": sum(x.pnl for x in trades) / len(trades) if trades else 0.0,
        "expose_pct": 100 * res["jours_exposes"] / max(1, res["jours_total"]),
        "frais": sum(x.frais for x in trades),
        "capital_final": v1,
    }


def buy_hold(donnees: dict[str, list[Bougie]], paire: str = "BTC",
             capital: float = 1000.0, mult_couts: float = 1.0) -> dict:
    """Reference : acheter et garder, frais d'entree et de sortie inclus."""
    s = donnees[paire]
    comm, spread = COMMISSION * mult_couts, SPREAD * mult_couts
    entree = s[0].close * (1 + spread)
    lots = capital * (1 - comm) / entree
    courbe = [(b.ts, lots * b.close) for b in s]
    frais = capital * comm + lots * s[-1].close * comm
    return {"trades": [], "courbe": courbe, "frais": frais,
            "jours_exposes": len(s), "jours_total": len(s),
            "capital_final": courbe[-1][1], "reglages": None}
