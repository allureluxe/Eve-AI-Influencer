#!/usr/bin/env python3
"""Repond aux commandes envoyees au robot sur Telegram.

    python3 ecoute_telegram.py           # traite les messages en attente
    python3 ecoute_telegram.py --test    # affiche sans envoyer

Lance par cron chaque minute. Ecris « rapport allure » dans la
conversation Telegram du robot : il fabrique la page ALLURE — la vraie,
avec le logo — sur la periode ecoulee DEPUIS TA DERNIERE DEMANDE, et te
l'envoie en fichier.

POURQUOI UN FICHIER ET PAS UN LIEN. Servir la page sur une adresse
publique exposerait les resultats du compte a qui trouverait l'URL. Le
fichier reste dans la conversation privee : on ne met pas les finances de
quelqu'un sur le web ouvert pour economiser un clic.

DEUX PROTECTIONS QUI COMPTENT.

  1. SEUL LE CHAT DE L'OPERATEUR est servi. Un bot Telegram est joignable
     par n'importe qui : sans ce controle, le premier venu qui trouve son
     nom recevrait l'etat du compte.
  2. AUCUNE COMMANDE N'AGIT SUR LE ROBOT. On lit, on repond. Pas d'ordre,
     pas d'arret, pas de reglage. Un canal de discussion ne doit pas
     pouvoir engager de l'argent — un jeton Telegram vole ne doit donner
     accès qu'a de la lecture.

Aucun ordre n'est envoye. Ce script lit.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import uuid

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env                          # noqa: E402

charger_env()

# UN ECOUTEUR NE DOIT RIEN ECRIRE DANS L'ETAT DU ROBOT.
os.environ["GB_STRATEGIE_FILE"] = "/tmp/strategie-ecoute.json"

ETAT = os.path.join(RACINE, "data", "ecoute_telegram.json")
API = "https://api.telegram.org/bot"


def _normaliser(texte: str) -> str:
    """Minuscules, sans accents : « Rapport ALLURE » == « rapport allure »."""
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn").strip()


def _etat() -> dict:
    try:
        with open(ETAT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:                                         # noqa: BLE001
        return {}


def _ecrire_etat(donnees: dict) -> None:
    os.makedirs(os.path.dirname(ETAT), exist_ok=True)
    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(donnees, f)


def _appel(jeton: str, methode: str, params: dict | None = None):
    url = f"{API}{jeton}/{methode}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=25) as r:
        return json.load(r)


def _envoyer_texte(jeton: str, chat: str, texte: str) -> None:
    corps = json.dumps({"chat_id": chat, "text": texte}).encode()
    req = urllib.request.Request(f"{API}{jeton}/sendMessage", data=corps,
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=25).close()


def _envoyer_fichier(jeton: str, chat: str, chemin: str, legende: str) -> None:
    """Envoi multipart, ecrit a la main : pas de dependance a installer."""
    limite = uuid.uuid4().hex
    with open(chemin, "rb") as f:
        contenu = f.read()
    nom = f"rapport-allure-{dt.datetime.now():%d-%m-%Hh%M}.html"
    morceaux = []
    for cle, valeur in (("chat_id", chat), ("caption", legende)):
        morceaux.append(
            f"--{limite}\r\nContent-Disposition: form-data; name=\"{cle}\"\r\n\r\n"
            f"{valeur}\r\n".encode())
    morceaux.append(
        f"--{limite}\r\nContent-Disposition: form-data; name=\"document\"; "
        f"filename=\"{nom}\"\r\nContent-Type: text/html\r\n\r\n".encode())
    morceaux.append(contenu)
    morceaux.append(f"\r\n--{limite}--\r\n".encode())
    corps = b"".join(morceaux)
    req = urllib.request.Request(
        f"{API}{jeton}/sendDocument", data=corps,
        headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    urllib.request.urlopen(req, timeout=60).close()


AIDE = ("Ce que je comprends :\n\n"
        "  rapport allure   la page complète depuis ta dernière demande\n"
        "  rapport jour     la page sur les dernières 24 heures\n"
        "  rapport semaine  la page sur les 7 derniers jours\n"
        "  etat             le point en deux lignes, sans page\n\n"
        "Je ne fais que lire : aucune commande ne touche au robot.")


def _point_court() -> str:
    from rapports import _compte, _trades
    capital, cash, positions = _compte()
    depuis = (dt.datetime.now() - dt.timedelta(days=1)).timestamp()
    trades = _trades(depuis, dt.datetime.now().timestamp())
    net = sum(t["profit"] for t in trades)
    return (f"Capital {capital:.2f} EUR — {positions} position(s), "
            f"{cash:.2f} EUR disponibles.\n"
            f"Dernières 24 h : {len(trades)} trade(s), {net:+.2f} EUR.")


def _traiter(texte: str, jeton: str, chat: str, etat: dict, test: bool) -> None:
    from rapports import page_allure

    t = _normaliser(texte)
    maintenant = dt.datetime.now().timestamp()

    if t.startswith("etat") or t in ("point", "ca va", "/start"):
        message = _point_court()
        print(message)
        if not test:
            _envoyer_texte(jeton, chat, message)
        return

    if "rapport" not in t:
        if not test:
            _envoyer_texte(jeton, chat, AIDE)
        print("commande inconnue -> aide envoyee")
        return

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
    print(f"page generee sur {libelle} ({taille:,} octets)")
    if not test:
        _envoyer_fichier(jeton, chat, chemin,
                         f"Rapport ALLURE — {libelle}. "
                         "Ouvre le fichier pour voir la page.")


def main() -> int:
    test = "--test" in sys.argv
    jeton = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
    if not jeton or not chat:
        print("Telegram non configure : voir configurer_telegram.py")
        return 1

    etat = _etat()
    params = {"timeout": 0}
    if etat.get("offset"):
        params["offset"] = etat["offset"]
    try:
        maj = _appel(jeton, "getUpdates", params)
    except Exception as exc:                                  # noqa: BLE001
        print(f"lecture impossible : {str(exc)[:120]}")
        return 1

    resultats = maj.get("result", []) if isinstance(maj, dict) else []
    if not resultats:
        return 0

    for m in resultats:
        etat["offset"] = m.get("update_id", 0) + 1
        msg = m.get("message") or m.get("channel_post") or {}
        texte = str(msg.get("text") or "")
        envoyeur = str((msg.get("chat") or {}).get("id") or "")
        if not texte:
            continue
        # SEUL LE CHAT DE L'OPERATEUR EST SERVI. Un bot Telegram est
        # joignable par n'importe qui ; sans ce controle, le premier venu
        # qui trouve son nom recevrait l'etat du compte.
        if envoyeur != chat:
            print(f"message ignore : chat {envoyeur} inconnu")
            continue
        print(f"commande recue : {texte[:60]!r}")
        try:
            _traiter(texte, jeton, chat, etat, test)
        except Exception as exc:                              # noqa: BLE001
            print(f"echec : {str(exc)[:160]}")
            if not test:
                try:
                    _envoyer_texte(jeton, chat,
                                   f"Je n'ai pas pu faire le rapport : "
                                   f"{str(exc)[:150]}")
                except Exception:                             # noqa: BLE001
                    pass

    if not test:
        _ecrire_etat(etat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
