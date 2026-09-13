#!/usr/bin/env python3
"""Redige le point de marche du matin. A lancer a 9h30, heure de Paris.

    30 9 * * *  cd /home/ubuntu/Eve-AI-Influencer && .venv/bin/python note_du_matin.py

La note part EN BROUILLON. Elle n'apparait pas dans l'application tant
que `valider_note.py` n'a pas ete lance.
"""

from __future__ import annotations

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def rassembler():
    """Les chiffres du matin, depuis les memes sources que le robot."""
    from gold_bot.economic_calendar import AgendaEconomique
    from gold_bot.market_note import Photo, lire_dominance, lire_fear_greed

    photo = Photo()
    photo.fear_greed, photo.fear_greed_texte = lire_fear_greed()
    photo.dominance_btc = lire_dominance()

    # Prix et moyennes : le fournisseur de bougies du robot, pour que la
    # note et les decisions lisent exactement les memes donnees.
    try:
        from gold_bot.datasources import get_provider
        prov = get_provider()
        for cle, symbole in (("btc", "BTCEUR"), ("eth", "ETHEUR")):
            bougies = prov.candles(symbole, "D1", 60)
            if not bougies or len(bougies) < 51:
                continue
            clotures = [b.close for b in bougies]
            prix = clotures[-1]
            setattr(photo, f"{cle}_prix", prix)
            setattr(photo, f"{cle}_var_7j",
                    (prix - clotures[-8]) / clotures[-8] * 100.0)
            ma50 = sum(clotures[-50:]) / 50.0
            setattr(photo, f"{cle}_vs_ma50", (prix - ma50) / ma50 * 100.0)
            if cle == "btc":
                amplitudes = [b.high - b.low for b in bougies[-14:]]
                photo.volatilite_pct = (sum(amplitudes) / 14.0) / prix * 100.0
    except Exception as exc:                                # noqa: BLE001
        logging.warning("prix indisponibles : %s", exc)

    try:
        photo.evenements = AgendaEconomique.depuis_env().evenements(jours=1)
    except Exception as exc:                                # noqa: BLE001
        logging.warning("agenda indisponible : %s", exc)

    return photo


def main() -> int:
    parseur = argparse.ArgumentParser(description=__doc__)
    parseur.add_argument("--sec", action="store_true",
                         help="affiche la note sans rien ecrire en base")
    args = parseur.parse_args()

    from gold_bot.market_note import NoteRefusee, RedacteurDeNote

    photo = rassembler()
    redacteur = RedacteurDeNote.depuis_env()

    try:
        titre, corps = redacteur.rediger(photo)
    except NoteRefusee as exc:
        # RIEN N'EST PUBLIE. Mieux vaut pas de note qu'une mauvaise note.
        print(f"Aucune note ce matin : {exc}", file=sys.stderr)
        return 1

    print(f"\n  {titre}\n")
    for para in corps.split("\n\n"):
        print(f"  {para}\n")
    print(f"  tendance {photo.trend_score()}  |  "
          f"agitation {photo.volatility_score()}  |  "
          f"peur/avidite {photo.fear_greed}  |  "
          f"part du bitcoin {photo.dominance_btc} %\n")

    if args.sec:
        print("  (mode sec : rien n'a ete ecrit)")
        return 0

    if redacteur.deposer(titre, corps, photo):
        print("  Note deposee EN BROUILLON. "
              "Lance valider_note.py pour la publier.")
        return 0
    print("  Note non deposee (base injoignable ou non configuree).",
          file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
