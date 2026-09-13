#!/usr/bin/env python3
"""Relit les notes en brouillon et publie celles que tu valides.

    .venv/bin/python valider_note.py

Rien n'est jamais publie automatiquement : un texte genere par une
machine, affiche dans une application financiere, doit passer par un
humain. C'est le seul filet.
"""

from __future__ import annotations

import os
import sys


def _client():
    from gold_bot.signal_publisher import SupabaseREST
    url = os.getenv("SUPABASE_URL", "").strip()
    cle = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
    if not (url and cle):
        print("SUPABASE_URL et SUPABASE_SERVICE_KEY doivent etre dans .env",
              file=sys.stderr)
        raise SystemExit(2)
    return SupabaseREST(url, cle)


def main() -> int:
    from gold_bot.signal_publisher import SupabaseIndisponible

    client = _client()
    try:
        brouillons = client._appel(
            "GET", "market_notes?published_at=is.null"
                   "&order=created_at.desc&limit=10")
    except SupabaseIndisponible as exc:
        print(f"Base injoignable : {exc}", file=sys.stderr)
        return 1

    if not brouillons:
        print("Aucun brouillon en attente.")
        return 0

    for note in brouillons:
        print("\n" + "=" * 68)
        print(f"  {note['headline']}\n")
        for para in (note.get("body_fr") or "").split("\n\n"):
            print(f"  {para}\n")
        print(f"  tendance {note.get('trend_score')}  |  "
              f"agitation {note.get('volatility_score')}  |  "
              f"peur/avidite {note.get('fear_greed')}  |  "
              f"part du bitcoin {note.get('btc_dominance')} %")
        print("=" * 68)

        reponse = input("  Publier ? [o]ui / [n]on / [s]upprimer / [q]uitter : ")
        choix = reponse.strip().lower()[:1]
        if choix == "q":
            break
        if choix == "o":
            client.modifier("market_notes", f"id=eq.{note['id']}",
                            {"published_at": "now()"})
            print("  Publiee.")
        elif choix == "s":
            client._appel("DELETE", f"market_notes?id=eq.{note['id']}")
            print("  Supprimee.")
        else:
            print("  Laissee en brouillon.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
