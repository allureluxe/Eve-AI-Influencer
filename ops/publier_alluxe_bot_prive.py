#!/usr/bin/env python3
"""Publie les statistiques privees (40 trades, objectifs) pour Alluxe Bot.

Meme principe que `publier_etat_public.py`, pour une table distincte et
reservee aux comptes admin (voir la migration
`20260915220000_alluxe_bot_prive.sql`). Lance par cron toutes les 15 min
-- ces chiffres bougent moins vite que le capital.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from gold_bot.croissance import PALIERS, palier_courant  # noqa: E402
from gold_bot.settings import BotConfig  # noqa: E402
from gold_bot.state import TradeJournal  # noqa: E402
from gold_bot.version_strategie import depuis_quand  # noqa: E402

OBJECTIFS_EUR = (3000.0, 10000.0, 50000.0)


def _capital_actuel() -> float:
    """Lit le capital deja publie par publier_etat_public.py -- evite un
    second appel a Bitvavo pour la meme donnee."""
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    requete = urllib.request.Request(
        f"{url}/rest/v1/etat_public?id=eq.robot&select=capital_eur",
        headers={"apikey": cle, "Authorization": f"Bearer {cle}"})
    with urllib.request.urlopen(requete, timeout=15) as r:
        lignes = json.loads(r.read())
    if not lignes:
        raise RuntimeError("etat_public vide -- publier_etat_public.py doit tourner d'abord")
    return float(lignes[0]["capital_eur"])


def _stats_40(cfg: BotConfig) -> dict:
    journal = TradeJournal(instance=cfg.engine.broker)
    journal.load()
    depuis = depuis_quand(cfg, lecture_seule=True)
    stats = journal.stats(since=depuis)
    trades = stats.get("trades", 0)
    esperance_nette = stats.get("esperance_R_nette") or 0.0
    capital = _capital_actuel()
    palier = palier_courant(trades, esperance_nette, capital)
    return {
        "trades": trades,
        "taux_reussite_pct": stats.get("taux_reussite_pct"),
        "esperance_R_nette": stats.get("esperance_R_nette"),
        "facteur_profit": stats.get("facteur_profit"),
        "palier": palier.nom,
    }, capital


def _objectifs(capital: float) -> dict:
    return {
        str(int(cible)): {
            "atteint": capital >= cible,
            "pct": round(min(capital / cible * 100.0, 100.0), 1),
        }
        for cible in OBJECTIFS_EUR
    }


# LA DESCRIPTION DE LA METHODE VIT DANS `gold_bot/methode.py`.
#
# Elle etait ici, et le robot lui-meme ne pouvait donc pas publier sa
# propre methode -- or deux comptes de simulation tournent desormais en
# parallele, et chacun doit dire ce qu'il fait. La recopier aurait donne
# deux descriptions a tenir d'accord, c'est-a-dire exactement la faute
# qui avait fait mentir cette phrase pendant une semaine.
from gold_bot.methode import phrase_methode as _methode  # noqa: E402


def _publier(stats_40: dict, objectifs: dict, methode: str) -> None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        print("SUPABASE_URL ou SUPABASE_SERVICE_KEY absent, rien publie")
        return
    corps = json.dumps({
        "id": "robot", "stats_40": stats_40, "objectifs": objectifs,
        "methode": methode,
    }).encode()
    requete = urllib.request.Request(
        f"{url}/rest/v1/alluxe_bot_prive",
        method="POST", data=corps,
        headers={
            "apikey": cle, "Authorization": f"Bearer {cle}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        })
    try:
        with urllib.request.urlopen(requete, timeout=15):
            pass
        print(f"publie : {stats_40['trades']}/40 trades, palier {stats_40['palier']}")
    except urllib.error.HTTPError as exc:
        print(f"echec HTTP {exc.code} : {exc.read()[:300]}")


def main() -> int:
    cfg = BotConfig.load(os.getenv("GB_CONFIG", "robot.bitvavo.json"))
    stats_40, capital = _stats_40(cfg)
    _publier(stats_40, _objectifs(capital), _methode(cfg))
    return 0


if __name__ == "__main__":
    sys.exit(main())
