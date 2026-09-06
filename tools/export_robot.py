#!/usr/bin/env python3
"""Export du journal du robot vers le récit d'Eve.

À poser sur le serveur où tourne le robot, et à lancer une fois par jour.
Il lit `data/trades.jsonl` (le journal que le robot tient déjà) et écrit
`data/trading/journal.json` — le seul fichier qu'Eve consulte pour parler
chiffres.

    python3 tools/export_robot.py                       # écrit le fichier
    python3 tools/export_robot.py --push                # écrit puis pousse
    python3 tools/export_robot.py --trades /chemin.jsonl --capital 100

Cron conseillé, tous les soirs à 23 h :

    0 23 * * * cd /chemin/du/robot && python3 tools/export_robot.py --push

Le script est autonome : aucune dépendance, aucun import du projet Eve.
Il peut donc vivre sur le serveur du robot sans rien y installer.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

CAPITAL_DEFAUT = 100.0


def lire_trades(chemin: Path) -> list[dict]:
    """Une ligne JSON par trade fermé. Les lignes cassées sont ignorées."""
    if not chemin.exists():
        return []
    trades: list[dict] = []
    for numero, ligne in enumerate(chemin.read_text(encoding="utf-8").splitlines(), 1):
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            brut = json.loads(ligne)
            if brut.get("partial"):        # une prise partielle n'est pas un trade
                continue
            trades.append({"closed_at": float(brut["closed_at"]),
                           "profit": float(brut["profit"])})
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            print(f"  ligne {numero} illisible, ignorée", file=sys.stderr)
    trades.sort(key=lambda t: t["closed_at"])
    return trades


def construire_journal(trades: list[dict], capital: float) -> dict:
    """Un solde par jour de trading, plus les étapes franchies.

    Le récit d'Eve se verrouille sur ces étapes : tant qu'elles ne sont pas
    ici, l'épisode correspondant ne peut pas être publié.
    """
    aujourdhui = datetime.now(timezone.utc).date().isoformat()
    solde = capital
    par_jour: dict[str, float] = {}
    for trade in trades:
        jour = datetime.fromtimestamp(trade["closed_at"], tz=timezone.utc).date().isoformat()
        if jour > aujourdhui:              # le récit ne devance jamais le réel
            continue
        solde = round(solde + trade["profit"], 2)
        par_jour[jour] = solde

    jours = sorted(par_jour)
    if not jours:
        return {"capital_depart_eur": capital, "entrees": []}

    entrees = [{"date": jours[0], "etape": "cent_euros", "solde_eur": capital,
                "note": "Compte réel ouvert."}]
    entrees += [{"date": jour, "etape": "", "solde_eur": par_jour[jour], "note": ""}
                for jour in jours]

    if len(jours) >= 5:                    # une semaine de données réelles
        entrees[-1]["etape"] = "premiere_semaine"
        entrees[-1]["note"] = f"{len(trades)} trades depuis l'ouverture."

    return {"capital_depart_eur": capital, "entrees": entrees}


def pousser(fichier: Path, racine: Path) -> bool:
    """Commit et push du seul fichier de journal."""
    try:
        relatif = str(fichier.relative_to(racine))
        subprocess.run(["git", "add", relatif], cwd=racine, check=True,
                       capture_output=True, timeout=60)
        deja = subprocess.run(["git", "diff", "--cached", "--quiet"],
                              cwd=racine, capture_output=True, timeout=60)
        if deja.returncode == 0:
            print("Aucun changement à pousser.")
            return True
        horodatage = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        subprocess.run(["git", "commit", "-m", f"Journal du robot au {horodatage}"],
                       cwd=racine, check=True, capture_output=True, timeout=60)
        subprocess.run(["git", "push"], cwd=racine, check=True,
                       capture_output=True, timeout=180)
        print("Journal poussé.")
        return True
    except subprocess.CalledProcessError as exc:
        sortie = (exc.stderr or b"").decode(errors="replace")[:300]
        print(f"Push impossible : {sortie}", file=sys.stderr)
        return False


def main(argv: list[str] | None = None) -> int:
    racine = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--trades", type=Path, default=racine / "data" / "trades.jsonl",
                        help="journal du robot (défaut : data/trades.jsonl)")
    parser.add_argument("--sortie", type=Path,
                        default=racine / "data" / "trading" / "journal.json")
    parser.add_argument("--capital", type=float, default=CAPITAL_DEFAUT,
                        help="capital de départ en euros")
    parser.add_argument("--push", action="store_true", help="commit et push le résultat")
    args = parser.parse_args(argv)

    trades = lire_trades(args.trades)
    if not trades:
        print(f"Aucun trade dans {args.trades}. Rien à exporter.")
        return 1

    journal = construire_journal(trades, args.capital)
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    args.sortie.write_text(json.dumps(journal, ensure_ascii=False, indent=2),
                           encoding="utf-8")

    soldes = [e["solde_eur"] for e in journal["entrees"] if e["solde_eur"] is not None]
    solde, bas = soldes[-1], min(soldes)
    variation = (solde - args.capital) / args.capital * 100 if args.capital else 0.0
    print(f"{len(trades)} trades → {args.sortie}")
    print(f"  solde     {solde:.2f} €   ({variation:+.1f} %)")
    print(f"  plus bas  {bas:.2f} €")

    if args.push:
        return 0 if pousser(args.sortie, racine) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
