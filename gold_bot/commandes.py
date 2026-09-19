"""Ce que le robot comprend quand on lui ecrit.

UN SEUL CERVEAU, DEUX BOUCHES. Ces regles servaient uniquement a
Telegram. L'operateur a demande le 19 septembre que l'application fasse
exactement la meme chose (« tout ce que le robot Telegram fait, je veux
que ce soit identique sur mon application »).

Recopier l'interpretation dans un second ecouteur aurait garanti la
divergence : c'est la faute que ce depot paie depuis le debut, et elle
s'est encore produite deux fois aujourd'hui (la ligne de position
dupliquee entre Demo et Direct, `etagePyramide` defini a deux endroits).
Le module ci-dessous ne connait ni Telegram ni Supabase : il recoit un
texte, il rend une reponse. Les deux ecouteurs ne font que du transport.

RIEN ICI N'AGIT SUR LE ROBOT. On lit, on repond. Pas d'ordre, pas
d'arret, pas de reglage — la contrainte vient de `ecoute_telegram.py` et
elle vaut d'autant plus pour l'application, qui est desormais le seul
canal.
"""
from __future__ import annotations

import datetime as dt
import os
import unicodedata
from dataclasses import dataclass
from typing import Optional

AIDE = ("Ce que je comprends :\n\n"
        "  rapport allure   la page complète depuis ta dernière demande\n"
        "  rapport jour     la page sur les dernières 24 heures\n"
        "  rapport semaine  la page sur les 7 derniers jours\n"
        "  etat             le point en deux lignes, sans page\n\n"
        "Je ne fais que lire : aucune commande ne touche au robot.")


@dataclass
class Reponse:
    """Ce que le robot repond. Le transport decide comment le livrer."""

    texte: str
    #: Chemin du fichier HTML de la page ALLURE, quand il y en a une.
    rapport: Optional[str] = None
    #: De quelle periode parle la page, en clair.
    titre_rapport: str = ""


def normaliser(texte: str) -> str:
    """Minuscules, sans accents : « Rapport ALLURE » == « rapport allure »."""
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn").strip()


def point_court() -> str:
    """Le point en deux lignes, sans fabriquer de page."""
    from rapports import _compte, _trades
    capital, cash, positions = _compte()
    depuis = (dt.datetime.now() - dt.timedelta(days=1)).timestamp()
    trades = _trades(depuis, dt.datetime.now().timestamp())
    net = sum(t["profit"] for t in trades)
    return (f"Capital {capital:.2f} EUR — {positions} position(s), "
            f"{cash:.2f} EUR disponibles.\n"
            f"Dernières 24 h : {len(trades)} trade(s), {net:+.2f} EUR.")


def repondre(texte: str, etat: dict) -> Reponse:
    """Interprete une demande et rend la reponse.

    `etat` porte la memoire entre deux demandes (la date du dernier
    rapport, pour que « rapport allure » couvre la periode ECOULEE
    depuis). Il est modifie sur place, et c'est a l'appelant de le
    sauvegarder — chaque canal a le sien.
    """
    from rapports import page_allure

    t = normaliser(texte)
    maintenant = dt.datetime.now().timestamp()

    if t.startswith("etat") or t in ("point", "ca va", "/start"):
        return Reponse(texte=point_court())

    if "rapport" not in t:
        return Reponse(texte=AIDE)

    if "semaine" in t:
        depuis = maintenant - 7 * 86400
        libelle = "les 7 derniers jours"
    elif "jour" in t or "24" in t:
        depuis = maintenant - 86400
        libelle = "les dernières 24 heures"
    else:
        depuis = etat.get("dernier_rapport") or (maintenant - 7 * 86400)
        quand = dt.datetime.fromtimestamp(depuis)
        libelle = f"depuis ta dernière demande ({quand:%d/%m à %Hh%M})"
        etat["dernier_rapport"] = maintenant

    chemin = page_allure(depuis=depuis, vers=maintenant, titre_periode=libelle)
    taille = os.path.getsize(chemin)
    return Reponse(
        texte=f"Rapport ALLURE — {libelle} ({taille // 1024} ko).",
        rapport=chemin, titre_rapport=libelle,
    )


def imprimer_si_possible(chemin: str, libelle: str) -> tuple[bool, str]:
    """Envoie la page a l'imprimante. Un echec n'est jamais bloquant.

    L'impression est un supplement : une imprimante eteinte ou un reseau
    capricieux ne doivent pas empecher le rapport d'arriver sur le
    telephone. Rend `(reussi, message)` ; le message est vide quand il
    n'y a rien a dire.
    """
    from gold_bot.impression import imprimer, nettoyer
    try:
        ok, message = imprimer(chemin, sujet=f"Rapport ALLURE — {libelle}")
        nettoyer()
        return ok, message
    except Exception as exc:                                  # noqa: BLE001
        return False, f"impression impossible : {str(exc)[:150]}"
