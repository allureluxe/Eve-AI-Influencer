#!/usr/bin/env python3
"""Courbes d'equite superposees, echelle logarithmique.

Le log est indispensable ici : le benchmark fait x20 pendant que les
variantes stagnent. En echelle lineaire elles seraient toutes ecrasees
sur la meme ligne plate et le graphique ne dirait rien.
"""
from __future__ import annotations

import datetime as dt
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402

RACINE = os.path.dirname(os.path.abspath(__file__))

COULEURS = {
    "A_BASELINE": ("#111111", 2.4, "-"),
    "B_REGIME": ("#1f77b4", 1.4, "-"),
    "C_UNIVERS": ("#2ca02c", 1.4, "-"),
    "D_SIGNAL": ("#ff7f0e", 1.4, "-"),
    "E_COMBO": ("#9467bd", 1.4, "-"),
    "BENCHMARK_BTC": ("#d62728", 1.8, "--"),
}


def main() -> int:
    with open(os.path.join(RACINE, "resultats.json")) as f:
        r = json.load(f)
    coupe = r["bornes"]["coupe"]

    fig, ax = plt.subplots(figsize=(13, 7))
    for nom, points in r["courbes"].items():
        if not points:
            continue
        c, lw, ls = COULEURS.get(nom, ("#888", 1.0, "-"))
        xs = [dt.datetime.fromtimestamp(t) for t, _ in points]
        ys = [v for _, v in points]
        ax.plot(xs, ys, label=nom, color=c, linewidth=lw, linestyle=ls)

    ax.axvline(dt.datetime.fromtimestamp(coupe), color="#666",
               linestyle=":", linewidth=1.2)
    ax.text(dt.datetime.fromtimestamp(coupe), ax.get_ylim()[1] * 0.9,
            "  debut hors echantillon", fontsize=9, color="#666")

    ax.set_yscale("log")
    ax.set_ylabel("capital (EUR, echelle log) — depart 1000")
    ax.set_title("Turtle et variantes contre achat-conservation du bitcoin\n"
                 "70 paires EUR Bitvavo, frais reels, execution a l'ouverture t+1",
                 fontsize=11)
    ax.grid(True, which="both", alpha=0.25)
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(RACINE, "equity.png"), dpi=130)
    print("-> equity.png")

    # Second graphique : sans le benchmark, pour voir les variantes entre elles.
    fig2, ax2 = plt.subplots(figsize=(13, 6))
    for nom, points in r["courbes"].items():
        if nom == "BENCHMARK_BTC" or not points:
            continue
        c, lw, ls = COULEURS.get(nom, ("#888", 1.0, "-"))
        xs = [dt.datetime.fromtimestamp(t) for t, _ in points]
        ax2.plot(xs, [v for _, v in points], label=nom, color=c,
                 linewidth=lw, linestyle=ls)
    ax2.axvline(dt.datetime.fromtimestamp(coupe), color="#666",
                linestyle=":", linewidth=1.2)
    ax2.axhline(1000, color="#aaa", linewidth=0.8)
    ax2.set_ylabel("capital (EUR) — depart 1000")
    ax2.set_title("Les variantes entre elles (benchmark retire pour l'echelle)",
                  fontsize=11)
    ax2.grid(True, alpha=0.25)
    ax2.legend(loc="upper left", fontsize=9)
    fig2.tight_layout()
    fig2.savefig(os.path.join(RACINE, "equity_variantes.png"), dpi=130)
    print("-> equity_variantes.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
