#!/usr/bin/env python3
"""Point du matin, envoye sur Telegram a 8 h (heure de Paris).

    python3 rapport_matin.py            # envoie
    python3 rapport_matin.py --console  # affiche seulement, n'envoie rien

CE QUE CE RAPPORT DIT, ET CE QU'IL NE DIT PAS.

L'operateur a demande « les grosses annonces economiques du jour, et en
fonction des annonces les cryptos qu'il va suivre de pres et a quel
moment il est pret pour acheter ».

Les annonces, oui. Le lien annonce -> crypto, NON : le robot ne le fait
pas, et lui faire dire le contraire serait mentir sur son propre
fonctionnement. Sa strategie est le PRIX seul — il achete la cassure du
plus-haut de 20 jours. C'est une decision de l'operateur du 31 aout 2026
(refus d'armer un biais directionnel manuel), et le moteur n'a aucune
entree « avis de marche ».

Ce que les annonces changent VRAIMENT : le robot suspend ses entrees
20 minutes avant et 20 minutes apres une annonce a fort impact, et
resserre ses stops 45 minutes avant. C'est mesurable, c'est arme, et
c'est ce que le rapport annonce.

« A quel moment il est pret pour acheter » a donc une reponse exacte,
mais elle vient du prix : le plus-haut de 20 jours de chaque crypto. Le
rapport liste celles qui en sont le plus proches, avec le prix exact qui
declenchera l'achat. C'est la vraie liste de surveillance.

AUCUN ORDRE N'EST ENVOYE. Ce script lit, il n'engage rien.
"""
from __future__ import annotations

import datetime as dt
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env                          # noqa: E402

charger_env()

# UN RAPPORT NE DOIT RIEN ECRIRE. Construire un TradingEngine met a jour
# le marqueur de strategie, ce qui REMET A ZERO l'echantillon des
# 40 trades. C'est arrive le 9 septembre 2026 en lancant un diagnostic.
os.environ["GB_STRATEGIE_FILE"] = "/tmp/strategie-rapport-matin.json"

from dataclasses import replace                               # noqa: E402

from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig   # noqa: E402
from gold_bot.news import NewsFilter                          # noqa: E402
from gold_bot.notifiers import Notifier                       # noqa: E402
from gold_bot.settings import BotConfig                       # noqa: E402
from gold_bot.universe import univers_bitvavo                 # noqa: E402

PARIS = dt.timezone(dt.timedelta(hours=2))      # affichage ; l'heure exacte
                                                # vient du cron (Europe/Paris)


def _annonces_du_jour(filtre: NewsFilter) -> list:
    """Evenements economiques d'aujourd'hui, du plus proche au plus loin."""
    filtre.refresh(force=True)
    auj = dt.datetime.now(dt.timezone.utc).date()
    evenements = [e for e in filtre.events if e.when.date() == auj]
    return sorted(evenements, key=lambda e: e.ts)


def _proches_du_declenchement(limite: int = 8) -> tuple[list, int]:
    """Cryptos les plus proches de leur plus-haut de 20 jours.

    Rend (liste, nombre_examine). Chaque element porte le prix actuel, le
    prix qui declenchera l'achat, et l'ecart en pourcentage. C'est la
    reponse exacte a « a quel moment il est pret pour acheter ».
    """
    from gold_bot.datasources import DataRegistry

    registre = DataRegistry()
    instruments = [i for i in univers_bitvavo() if i.asset_class == "crypto"]
    lignes = []
    for inst in instruments:
        try:
            bougies = registre.candles(inst.symbol, "crypto", "D1", 40)
        except Exception:                                     # noqa: BLE001
            continue
        if len(bougies) < 22:
            continue
        # Le canal EXCLUT la bougie du jour, comme la strategie : sinon le
        # plus-haut se compare a lui-meme et rien ne casse jamais.
        canal = max(b.high for b in bougies[-21:-1])
        prix = bougies[-1].close
        if canal <= 0 or prix <= 0:
            continue
        ecart = (canal - prix) / prix * 100.0
        if ecart >= 0:                       # pas encore casse
            lignes.append((ecart, inst.symbol.replace("USD", ""), prix, canal))
    lignes.sort()
    return lignes[:limite], len(instruments)


def _compte() -> tuple[float, float, int]:
    cfg = BitvavoConfig.from_env()
    courtier = BitvavoBroker(replace(cfg, dry_run=True))
    if not courtier.connect():
        return 0.0, 0.0, 0
    compte = courtier.account()
    avoirs = sum(1 for actif, quantite in courtier._soldes.items()
                 if actif != cfg.quote_asset and quantite > 0)
    return compte.equity, compte.margin_free, avoirs


def construire() -> str:
    cfg = BotConfig.load(os.path.join(RACINE, "robot.bitvavo.json"))
    maintenant = dt.datetime.now(dt.timezone.utc)
    # `strftime` suit la locale du serveur, qui est anglaise et le restera :
    # installer une locale francaise sur un VPS pour trois mots est un
    # point de panne de plus. On traduit les sept jours et douze mois.
    local = maintenant.astimezone(PARIS)
    JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi",
             "samedi", "dimanche"]
    MOIS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
            "aout", "septembre", "octobre", "novembre", "decembre"]
    lignes = [f"Point du {JOURS[local.weekday()]} {local.day} "
              f"{MOIS[local.month - 1]}", ""]

    # ---------------------------------------------------- le compte
    capital, cash, positions = _compte()
    if capital > 0:
        lignes += [f"Capital : {capital:.2f} EUR",
                   f"Investi : {capital - cash:.2f} EUR sur {positions} crypto(s)",
                   f"Libre   : {cash:.2f} EUR", ""]
    else:
        lignes += ["Capital : lecture impossible ce matin "
                   "(Bitvavo injoignable) — rien n'est change.", ""]

    # ---------------------------------------------- annonces du jour
    filtre = NewsFilter()
    annonces = _annonces_du_jour(filtre)
    if annonces:
        lignes.append("ANNONCES ECONOMIQUES AUJOURD'HUI")
        for e in annonces:
            heure = e.when.astimezone(PARIS)
            fort = filtre.is_major(e)
            marge = filtre.config.high_before if fort else filtre.config.medium_before
            lignes.append(
                f"  {heure:%Hh%M}  {e.title}"
                + ("  [FORT IMPACT]" if fort else ""))
            lignes.append(
                f"         le robot n'ouvre rien de {marge} min avant "
                f"a {marge} min apres")
        lignes.append("")
    else:
        lignes += ["ANNONCES ECONOMIQUES AUJOURD'HUI",
                   "  aucune annonce connue au calendrier.", ""]

    # ------------------------------------ ce que le robot surveille
    proches, examines = _proches_du_declenchement()
    lignes.append(f"CE QU'IL SURVEILLE ({examines} cryptos scannees)")
    if proches:
        lignes.append("  il achete des que le prix depasse le plus-haut de 20 jours :")
        for ecart, nom, prix, canal in proches:
            lignes.append(f"  {nom:<8} {prix:>12.6f}  ->  achat au-dessus de "
                          f"{canal:.6f}   (+{ecart:.1f} % a faire)")
    else:
        lignes.append("  aucune crypto lisible ce matin.")
    lignes.append("")

    # --------------------------------------------------- la reserve
    lignes += [
        "CE QUE CE RAPPORT NE DIT PAS",
        "  Le robot ne choisit PAS ses cryptos en fonction des annonces.",
        "  Il achete sur le prix seul — la cassure du plus-haut de 20 jours.",
        "  Les annonces ne font qu'une chose : il suspend ses entrees autour",
        "  d'elles, et resserre ses stops "
        f"{filtre.config.tighten_before} min avant.",
        "",
        f"  Risque par position : {cfg.risk.base_risk_pct:.2f} % du capital"
        f" ({capital * cfg.risk.base_risk_pct / 100:.2f} EUR)" if capital > 0
        else f"  Risque par position : {cfg.risk.base_risk_pct:.2f} % du capital",
    ]
    return "\n".join(lignes)


def main() -> int:
    texte = construire()
    if "--console" in sys.argv:
        print(texte)
        return 0
    # Niveau « trade » : c'est le seuil du canal Telegram. En « info » le
    # rapport serait ecrit au journal et n'arriverait JAMAIS sur le
    # telephone — le piege du 10 septembre 2026.
    Notifier().notify("trade", "Point du matin", texte,
                      data={"rapport": "matin"})
    print(texte)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
