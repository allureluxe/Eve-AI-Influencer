"""Le detail des trades fermes, dit en francais et en euros.

POURQUOI CE MODULE EXISTE
-------------------------
Le rapport periodique annoncait « Robot actif, capital X, 3 positions »
et rien d'autre. L'operateur voyait donc son capital bouger sans jamais
savoir CE QUI l'avait fait bouger — ni quelle crypto, ni combien, ni
pourquoi la position s'etait fermee.

Un rapport qui donne un solde sans son detail ne rassure pas, il
inquiete : quand le chiffre baisse, on n'a aucun moyen de savoir si
c'est normal.

LA TRADUCTION N'EST PAS DU CONFORT
----------------------------------
Les raisons de sortie sont ecrites par et pour le moteur :

    « stop temporel : 360 min sans progression (-0.84R) »
    « retournement confirme a +0.26R (dynamique -0.60 : supertrend
      retourne contre la position) »

Ces phrases ne veulent rien dire pour quelqu'un qui ne connait pas le
trading — et un rapport qu'on ne comprend pas est un rapport qu'on
cesse de lire. On les reecrit en francais courant, et les montants sont
donnes EN EUROS, jamais en R.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence


def _heures(minutes: float) -> str:
    if minutes < 90:
        return f"{round(minutes / 60 * 2) / 2:g} heure" \
               + ("s" if minutes >= 90 else "")
    heures = minutes / 60
    if heures < 24:
        return f"{round(heures)} heures"
    jours = round(heures / 24)
    return f"{jours} jour" + ("s" if jours > 1 else "")


def raison_lisible(brute: str, gain: float | None = None) -> str:
    """« stop temporel : 360 min sans progression (-0.84R) »
        -> « ca n'avancait plus depuis 6 heures ».

    `gain` change le mot employe pour une meme raison technique, et ce
    n'est pas cosmetique — voir le cas du stop ci-dessous.

    Repli sur la phrase d'origine : afficher du jargon est desagreable,
    inventer une explication fausse est pire.
    """
    r = (brute or "").strip().lower()
    if not r:
        return "sortie"

    # LE MEME STOP DIT DEUX CHOSES OPPOSEES SELON LE RESULTAT.
    #
    # Le robot remonte sa protection au fil de la hausse. Quand elle se
    # declenche sur une position gagnante, ce n'est pas un echec : c'est
    # le stop suiveur qui vient d'encaisser le gain, exactement comme
    # prevu. Ecrire « protection touchee » sur un +1,00 EUR ferait
    # passer un succes pour un rate — et sur un rapport ou 80 % des
    # sorties sont des stops, ca donne l'impression d'un robot qui se
    # fait sortir en permanence.
    if "stop" in r and ("declenche" in r or "atteint" in r or "plateforme" in r):
        if gain is not None and gain > 0:
            return "le stop suiveur a encaisse le gain"
        return "protection touchee"

    if "stop temporel" in r:
        m = re.search(r"(\d+)\s*min", r)
        if m:
            return f"ca n'avancait plus depuis {_heures(float(m.group(1)))}"
        return "ca n'avancait plus"

    if "prise partielle" in r:
        m = re.search(r"(\d+)\s*%", r)
        part = f"{m.group(1)} %" if m else "une partie"
        return f"benefice encaisse sur {part} de la position"

    if "retournement" in r:
        return "le cours s'est retourne"

    if "perte anormale" in r or "securite" in r:
        return "chute brutale, sortie d'urgence"

    if "micro-profit" in r or "gain encaisse" in r:
        return "petit gain encaisse, le mouvement faiblissait"

    if r in ("tp", "take profit") or "objectif" in r:
        return "objectif atteint"

    if "breakeven" in r or "seuil" in r:
        return "sortie au prix d'achat, sans perte"

    if "manuel" in r or "manual" in r:
        return "fermeture manuelle"

    # Rien de reconnu : on rend la phrase d'origine plutot que d'inventer.
    return brute.strip()


#: Noms courants, pour ne pas ecrire « le ADA ».
NOMS = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "XRP": "XRP",
    "ADA": "Cardano", "DOGE": "Dogecoin", "LINK": "Chainlink",
    "AVAX": "Avalanche", "DOT": "Polkadot", "LTC": "Litecoin",
    "ATOM": "Cosmos", "MATIC": "Polygon", "TRX": "Tron", "KNC": "Kyber",
    "MANA": "Decentraland", "PENDLE": "Pendle", "CAKE": "PancakeSwap",
}


def nom_court(symbole: str) -> str:
    """« TRXUSD » -> « Tron ». Repli sur la base du symbole."""
    s = (symbole or "").upper()
    for devise in ("USDT", "USDC", "EUR", "USD"):
        if s.endswith(devise) and len(s) > len(devise):
            s = s[: -len(devise)]
            break
    return NOMS.get(s, s)


def _euros(montant: float) -> str:
    return f"{montant:+.2f} EUR".replace(".", ",")


def lignes_trades(trades: Sequence, devise: str = "EUR") -> List[str]:
    """Une ligne par trade ferme, du plus recent au plus ancien."""
    lignes: List[str] = []
    for t in sorted(trades, key=lambda x: getattr(x, "closed_at", 0),
                    reverse=True):
        montant = float(getattr(t, "profit", 0.0))
        signe = "+" if montant >= 0 else ""
        lignes.append(
            f"  {signe}{montant:.2f} {devise}  {nom_court(t.symbol)}"
            f"  — {raison_lisible(getattr(t, 'reason', ''), montant)}"
        )
    return lignes


def bilan(trades: Sequence, devise: str = "EUR",
          detail_max: int = 8) -> List[str]:
    """Le bloc « trades fermes » du rapport periodique.

    Rend une liste vide quand rien ne s'est ferme : une section
    « 0 trade » repetee toutes les demi-heures fait du bruit et finit
    par faire ignorer le rapport entier.

    `detail_max` borne le detail. Une nuit agitee peut fermer trente
    positions ; un message de trente lignes sur Telegram n'est pas lu.
    Le total, lui, porte toujours sur TOUS les trades.
    """
    trades = list(trades)
    if not trades:
        return []

    gagnants = [t for t in trades if float(getattr(t, "profit", 0)) > 0]
    total = sum(float(getattr(t, "profit", 0)) for t in trades)

    n = len(trades)
    tete = (f"{n} trade ferme" if n == 1 else f"{n} trades fermes") \
        + f" : {_euros(total)} au total"
    if n > 1:
        tete += f"  ({len(gagnants)} gagnant" \
                + ("s" if len(gagnants) > 1 else "") + f" sur {n})"

    # ON TRIE AVANT DE COUPER. Couper d'abord garderait les plus
    # ANCIENS de la liste d'entree — soit exactement l'inverse de ce
    # qu'on veut montrer dans un rapport.
    recents = sorted(trades, key=lambda x: getattr(x, "closed_at", 0),
                     reverse=True)

    lignes = [tete]
    lignes += lignes_trades(recents[:detail_max], devise)
    if n > detail_max:
        reste = n - detail_max
        lignes.append(f"  ... et {reste} autre" + ("s" if reste > 1 else ""))
    return lignes
