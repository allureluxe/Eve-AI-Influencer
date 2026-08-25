"""Utilitaires partages par les tests."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gold_bot.core import Candle, Side  # noqa: E402
from gold_bot.indicators import IndicatorSet  # noqa: E402


def trending_indicators(direction: int = 1, start: float = 2600.0, bars: int = 160,
                        step: float = 1.2, noise: float = 0.25) -> IndicatorSet:
    """Construit un jeu d'indicateurs sur une tendance nette et reguliere.

    Sert a placer le gestionnaire de position dans un contexte ou la
    dynamique est franchement favorable (ou defavorable si direction = -1).
    """
    ind = IndicatorSet()
    price = start
    for i in range(bars):
        o = price
        price += direction * step
        c = price
        hi = max(o, c) + noise
        lo = min(o, c) - noise
        ind.update(Candle(i * 300, o, hi, lo, c, 100 + i))
    return ind


def flat_indicators(start: float = 2600.0, bars: int = 160) -> IndicatorSet:
    """Marche sans direction : dynamique nulle, ATR stable."""
    ind = IndicatorSet()
    for i in range(bars):
        base = start + (1.0 if i % 2 else -1.0) * 0.6
        ind.update(Candle(i * 300, start, base + 1.0, base - 1.0, base, 100))
    return ind


def zigzag_indicators(direction: int = 1, start: float = 2600.0, legs: int = 26,
                      impulse: float = 6.0, pullback: float = 2.5,
                      seed: int = 17) -> IndicatorSet:
    """Tendance en escalier : impulsions puis replis, avec du bruit.

    Une droite parfaite n'a aucun swing (chaque bougie depasse la
    precedente) et une amplitude parfaitement reguliere fait tomber le
    percentile d'ATR a zero. Pour tester la strategie il faut une serie qui
    respire comme un marche reel : jambes de longueur variable, amplitude
    irreguliere, replis inegaux.
    """
    import random

    rng = random.Random(seed)
    ind = IndicatorSet()
    price = start
    ts = 0
    for _ in range(legs):
        for _ in range(rng.randint(3, 5)):                    # impulsion
            o = price
            price += direction * impulse * rng.uniform(0.5, 1.5)
            hi = max(o, price) + abs(rng.gauss(0, impulse * 0.25))
            lo = min(o, price) - abs(rng.gauss(0, impulse * 0.25))
            ind.update(Candle(ts, o, hi, lo, price, rng.uniform(80, 200)))
            ts += 300
        for _ in range(rng.randint(1, 3)):                    # repli
            o = price
            price -= direction * pullback * rng.uniform(0.5, 1.5)
            hi = max(o, price) + abs(rng.gauss(0, pullback * 0.3))
            lo = min(o, price) - abs(rng.gauss(0, pullback * 0.3))
            ind.update(Candle(ts, o, hi, lo, price, rng.uniform(50, 140)))
            ts += 300
    return ind


def pullback_setup_indicators(direction: int = 1, start: float = 2600.0,
                              seed: int = 3) -> IndicatorSet:
    """Construit un cas d'ecole : tendance etablie, repli sur l'EMA, bougie de reprise.

    C'est la configuration de reference de la strategie ("tendance_repli").
    La serie est batie pour que chaque condition soit reunie : tendance de
    fond marquee, volatilite ni morte ni extreme, repli qui ramene le prix
    au contact de l'EMA moyenne, puis avalement dans le sens de la tendance.
    """
    import random

    rng = random.Random(seed)
    ind = IndicatorSet()
    price = start
    ts = 0

    def push(open_, close_, wick=0.5, vol=120.0):
        nonlocal ts
        hi = max(open_, close_) + abs(rng.gauss(0, wick))
        lo = min(open_, close_) - abs(rng.gauss(0, wick))
        ind.update(Candle(ts, open_, hi, lo, close_, vol))
        ts += 300

    # 1. Phase de construction : volatilite variee, pour que le percentile
    #    d'ATR ait un historique realiste.
    for i in range(90):
        o = price
        amp = rng.uniform(0.8, 3.0)
        price += direction * rng.uniform(0.1, 1.0) + rng.gauss(0, 0.6)
        push(o, price, wick=amp * 0.4, vol=rng.uniform(80, 200))

    # 2. Impulsion nette : installe la tendance et ecarte le prix de l'EMA.
    for _ in range(18):
        o = price
        price += direction * rng.uniform(2.0, 3.5)
        push(o, price, wick=0.8, vol=rng.uniform(150, 260))

    # 3. Repli mesure : le prix revient au contact de l'EMA moyenne.
    #    Le repli doit etre assez profond pour detendre le RSI, sinon la
    #    strategie considere a juste titre que le marche n'a pas respire.
    for _ in range(14):
        o = price
        price -= direction * rng.uniform(1.4, 2.4)
        push(o, price, wick=0.6, vol=rng.uniform(60, 110))

    # 4. Bougie de reprise avalante, dans le sens de la tendance. Elle reste
    #    contenue : une bougie geante eloignerait deja le prix de la zone.
    last = ind.candles[-1]
    body = abs(last.open - last.close)
    o = price
    price += direction * (body * 1.4 + 0.5)
    if direction > 0:
        ind.update(Candle(ts, min(o, last.close) - 0.15, max(o, price) + 0.25,
                          min(o, price) - 0.3, price, 320))
    else:
        ind.update(Candle(ts, max(o, last.close) + 0.15, max(o, price) + 0.3,
                          min(o, price) - 0.25, price, 320))
    return ind
