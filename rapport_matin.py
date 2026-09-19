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
plus-haut du canal Donchian ARME (`strategy.donchian_entrees`, 10 jours
depuis le 12 sept.). C'est une decision de l'operateur du 31 aout 2026
(refus d'armer un biais directionnel manuel), et le moteur n'a aucune
entree « avis de marche ».

Ce que les annonces changent VRAIMENT : le robot suspend ses entrees
20 minutes avant et 20 minutes apres une annonce a fort impact, et
resserre ses stops 45 minutes avant. C'est mesurable, c'est arme, et
c'est ce que le rapport annonce.

« A quel moment il est pret pour acheter » a donc une reponse exacte,
mais elle vient du prix : le plus-haut du canal arme, pour chaque crypto. Le
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


def _proches_du_declenchement(canal_jours: int, limite: int = 8) -> tuple[list, int]:
    """Cryptos les plus proches de leur plus-haut de `canal_jours` jours.

    Rend (liste, nombre_examine). Chaque element porte le prix actuel, le
    prix qui declenchera l'achat, et l'ecart en pourcentage. C'est la
    reponse exacte a « a quel moment il est pret pour acheter ».

    `canal_jours` VIENT DE LA CONFIGURATION ARMEE, il n'est pas ecrit ici :
    la longueur etait figee a 20 alors que le robot tourne sur 10 jours
    depuis le 12 septembre. Ce rapport ne se contentait donc pas d'ecrire
    un mauvais chiffre, il CALCULAIT sur le mauvais canal -- il listait
    les mauvaises cryptos et annoncait des prix de declenchement trop
    hauts (un plus-haut de 20 jours est toujours >= celui de 10), donc
    le robot achetait plus tot que ce que le rapport laissait croire.
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
        if len(bougies) < canal_jours + 2:
            continue
        # Le canal EXCLUT la bougie du jour, comme la strategie : sinon le
        # plus-haut se compare a lui-meme et rien ne casse jamais.
        canal = max(b.high for b in bougies[-(canal_jours + 1):-1])
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


def _lire_journal() -> list:
    """Tous les trades fermes du journal, les plus recents en dernier.

    Lit le fichier directement plutot que de construire un moteur : le
    rapport tourne dans un cron a cote du robot, et instancier un
    second moteur ouvrirait une deuxieme connexion au courtier pour
    rien.
    """
    import json

    class _Trade:
        __slots__ = ("symbol", "profit", "reason", "closed_at")

    trades = []
    try:
        with open(os.path.join(RACINE, "data", "trades.jsonl")) as f:
            for ligne in f:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    d = json.loads(ligne)
                except json.JSONDecodeError:
                    continue
                t = _Trade()
                t.symbol = d.get("symbol", "")
                t.profit = float(d.get("profit", 0.0))
                t.reason = d.get("reason", "")
                t.closed_at = float(d.get("closed_at", 0))
                trades.append(t)
    except OSError:
        return []
    return sorted(trades, key=lambda x: x.closed_at)


def _fenetre_8h_a_8h(maintenant: dt.datetime) -> tuple[float, float]:
    """De 8 h hier a 8 h aujourd'hui, heure de Paris.

    UNE JOURNEE QUI COMMENCE A MINUIT NE VEUT RIEN DIRE ICI. Le marche
    crypto ne ferme jamais, et le robot travaille la nuit : coupe a
    minuit, la moitie d'une nuit tombe d'un cote et la moitie de
    l'autre. En calant sur l'heure du rapport, chaque message couvre
    exactement ce qui s'est passe depuis le precedent — aucun trou,
    aucun doublon.
    """
    huit = maintenant.astimezone(PARIS).replace(
        hour=8, minute=0, second=0, microsecond=0)
    if maintenant.astimezone(PARIS) < huit:
        # Lance avant 8 h : la fenetre est celle d'avant-hier a hier.
        huit -= dt.timedelta(days=1)
    return (huit - dt.timedelta(days=1)).timestamp(), huit.timestamp()


def _bilan_depuis_le_debut(trades: list) -> list:
    """Le cumul depuis le premier trade, en francais et en euros.

    Le pourcentage est calcule sur le capital de DEPART reconstitue :
    capital actuel moins tout ce que le robot a gagne ou perdu. On ne
    peut pas le lire ailleurs — le compte a recu des versements et un
    retrait, qui ne sont pas des resultats de trading et ne doivent pas
    entrer dans la progression.
    """
    if not trades:
        return []

    from gold_bot.rapport_trades import nom_court

    total = sum(t.profit for t in trades)
    gagnants = [t for t in trades if t.profit > 0]
    perdants = [t for t in trades if t.profit < 0]
    somme_gains = sum(t.profit for t in gagnants)
    somme_pertes = -sum(t.profit for t in perdants)

    premier = dt.datetime.fromtimestamp(trades[0].closed_at, PARIS)
    jours = max(1, (dt.datetime.now(PARIS) - premier).days)

    meilleur = max(trades, key=lambda t: t.profit)
    pire = min(trades, key=lambda t: t.profit)

    lignes = [
        "DEPUIS LE DEBUT",
        f"  {len(trades)} trades en {jours} jours "
        f"({len(trades) / jours:.1f} par jour)",
        f"  Gagnants : {len(gagnants)} sur {len(trades)} "
        f"({len(gagnants) / len(trades) * 100:.0f} %)",
        "",
        f"  Ce qu'il a gagne  : +{somme_gains:.2f} EUR",
        f"  Ce qu'il a perdu  : -{somme_pertes:.2f} EUR",
        f"  Resultat net      : {total:+.2f} EUR",
        "",
        f"  Meilleur trade : {meilleur.profit:+.2f} EUR "
        f"({nom_court(meilleur.symbol)})",
        f"  Pire trade     : {pire.profit:+.2f} EUR "
        f"({nom_court(pire.symbol)})",
    ]
    return lignes
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

    # ------------------------------- la journee, de 8 h a 8 h
    #
    # C'EST LE SEUL MESSAGE DE LA JOURNEE, il doit donc porter les deux
    # reponses que l'operateur cherche : « il s'est passe quoi depuis
    # hier ? » et « on en est ou depuis le debut ? ».
    from gold_bot.rapport_trades import bilan

    tous = _lire_journal()
    debut, fin = _fenetre_8h_a_8h(maintenant)
    hier = [t for t in tous if debut <= t.closed_at < fin]

    lignes.append("DEPUIS HIER 8 H")
    if hier:
        gagnants = [t for t in hier if t.profit > 0]
        net = sum(t.profit for t in hier)
        lignes += [
            f"  Resultat : {net:+.2f} EUR",
            f"  {len(hier)} trades, {len(gagnants)} gagnants "
            f"({len(gagnants) / len(hier) * 100:.0f} %)",
            "",
        ]
        # Le detail vient sans sa ligne de tete : elle ferait doublon
        # avec les deux lignes ci-dessus.
        lignes += bilan(hier, "EUR", detail_max=10)[1:]
    else:
        # Une nuit sans trade est une information, pas un vide.
        lignes.append("  Aucune position fermee. Le robot n'a pas trouve "
                      "d'occasion qui passe ses filtres.")
    lignes.append("")

    # ------------------------------------------- le cumul
    depuis = _bilan_depuis_le_debut(tous)
    if depuis:
        lignes += depuis + [""]

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
    canal_jours = min(cfg.strategy.donchian_entrees or [20])
    proches, examines = _proches_du_declenchement(canal_jours)
    lignes.append(f"CE QU'IL SURVEILLE ({examines} cryptos scannees)")
    if proches:
        lignes.append(f"  il achete des que le prix depasse le plus-haut "
                      f"de {canal_jours} jours :")
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
        f"  Il achete sur le prix seul — la cassure du plus-haut de "
        f"{canal_jours} jours.",
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
