#!/usr/bin/env python3
"""Repond aux messages ecrits dans l'onglet Discussion d'Alluxe Bot.

    python3 ops/ecoute_discussion.py          # traite ce qui attend
    python3 ops/ecoute_discussion.py --test   # affiche sans ecrire

Lance par cron chaque minute, comme `ecoute_telegram.py` -- dont il
REMPLACE l'usage. Decision de l'operateur le 19 septembre : « je n'ai
plus besoin des messages Telegram [...] l'onglet Discussion, je veux que
ce soit ici que je reçois les messages et là où je peux écrire ».

L'interpretation des commandes vit dans `gold_bot/commandes.py`, partagee
avec Telegram : les deux canaux comprennent donc exactement la meme
chose, par construction et non par discipline.

LA PAGE VOYAGE DANS LA LIGNE, pas sur une adresse publique. Telegram la
livrait en fichier dans une conversation privee, pour la raison ecrite
dans `ecoute_telegram.py` : « on ne met pas les finances de quelqu'un sur
le web ouvert pour economiser un clic ». Un lien de stockage, meme
obscur, reste une adresse trouvable.

RIEN ICI N'AGIT SUR LE ROBOT. On lit, on repond.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env                          # noqa: E402

charger_env()

# UN ECOUTEUR NE DOIT RIEN ECRIRE DANS L'ETAT DU ROBOT.
os.environ["GB_STRATEGIE_FILE"] = "/tmp/strategie-discussion.json"

from gold_bot.commandes import (Reponse, est_une_commande,  # noqa: E402
                                imprimer_si_possible, repondre)

ETAT = os.path.join(RACINE, "data", "ecoute_discussion.json")
TABLE = "alluxe_bot_discussion"

# Au-dela, la page ne part pas : une ligne de plusieurs megaoctets
# ralentirait le chargement de TOUTE la conversation, a chaque
# ouverture de l'onglet. Les pages observees font quelques dizaines de
# kilo-octets ; ce plafond ne doit jamais etre atteint, et s'il l'est
# c'est le signe d'une page qui a deraille.
RAPPORT_MAX_OCTETS = 2_000_000


def _base() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    cle = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        raise SystemExit("Supabase non configure (SUPABASE_URL / SERVICE_KEY)")
    return url, cle


def _appel(chemin: str, methode: str = "GET", corps=None) -> list:
    url, cle = _base()
    entetes = {"apikey": cle, "authorization": f"Bearer {cle}",
               "content-type": "application/json"}
    donnees = json.dumps(corps).encode() if corps is not None else None
    req = urllib.request.Request(f"{url}/rest/v1/{chemin}", data=donnees,
                                 headers=entetes, method=methode)
    with urllib.request.urlopen(req, timeout=60) as rep:
        brut = rep.read()
        return json.loads(brut) if brut else []


def _etat() -> dict:
    try:
        with open(ETAT) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _ecrire_etat(etat: dict) -> None:
    os.makedirs(os.path.dirname(ETAT), exist_ok=True)
    tmp = ETAT + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(etat, fh, indent=2)
    os.replace(tmp, ETAT)


def _publier(reponse: Reponse, test: bool) -> None:
    """Depose la reponse du robot dans le fil."""
    ligne = {"auteur": "robot", "texte": reponse.texte, "traite": True}

    if reponse.rapport:
        taille = os.path.getsize(reponse.rapport)
        if taille > RAPPORT_MAX_OCTETS:
            ligne["texte"] += (f"\n\n(La page fait {taille // 1024} ko, "
                               "trop lourde pour la conversation. "
                               "Elle reste imprimable.)")
        else:
            with open(reponse.rapport, "rb") as fh:
                ligne["rapport_html"] = fh.read().decode("utf-8", "replace")
            ligne["rapport_titre"] = reponse.titre_rapport

    if test:
        apercu = dict(ligne)
        if "rapport_html" in apercu:
            apercu["rapport_html"] = f"<{len(apercu['rapport_html'])} caracteres>"
        print("  reponse :", json.dumps(apercu, ensure_ascii=False)[:400])
        return
    _appel(TABLE, "POST", ligne)


def main() -> int:
    test = "--test" in sys.argv

    try:
        attente = _appel(
            f"{TABLE}?auteur=eq.operateur&traite=eq.false"
            f"&order=created_at.asc&limit=20")
    except urllib.error.HTTPError as exc:
        corps = exc.read().decode()[:200]
        if "does not exist" in corps or exc.code == 404:
            print("table absente : appliquer la migration "
                  "20260919233000_discussion_alluxe_bot.sql")
            return 1
        print(f"lecture impossible : {exc.code} {corps}")
        return 1
    except Exception as exc:                                  # noqa: BLE001
        print(f"lecture impossible : {str(exc)[:160]}")
        return 1

    if not attente:
        return 0

    etat = _etat()
    for message in attente:
        texte = str(message.get("texte") or "").strip()

        # PAS POUR MOI : c'est une question, pas une commande.
        #
        # Le service `alluxe-agent` la traite, avec ses outils et son
        # modele. Il tourne en permanence et repond en quelques secondes,
        # la ou ce script ne passe qu'une fois par minute -- on le laisse
        # donc faire plutot que de repondre « je ne comprends pas ».
        if not est_une_commande(texte):
            continue

        print(f"commande recue : {texte[:60]!r}")

        try:
            reponse = repondre(texte, etat)
        except Exception as exc:                              # noqa: BLE001
            print(f"echec : {str(exc)[:160]}")
            reponse = Reponse(
                texte=f"Je n'ai pas pu faire le rapport : {str(exc)[:150]}")

        try:
            _publier(reponse, test)
        except Exception as exc:                              # noqa: BLE001
            # LA COMMANDE RESTE NON TRAITEE : on reessaiera au prochain
            # passage. La marquer traitee alors que la reponse n'est pas
            # partie la ferait disparaitre en silence.
            print(f"publication impossible : {str(exc)[:160]}")
            continue

        if reponse.rapport:
            ok, msg = imprimer_si_possible(reponse.rapport,
                                           reponse.titre_rapport)
            if msg:
                print(msg)
                # On ne previent que si ca a rate : confirmer chaque
                # impression reussie repeterait ce que la feuille dit.
                if not ok and not test:
                    try:
                        _appel(TABLE, "POST",
                               {"auteur": "robot", "texte": msg, "traite": True})
                    except Exception:                         # noqa: BLE001
                        pass

        if not test:
            _appel(f"{TABLE}?id=eq.{message['id']}", "PATCH", {"traite": True})

    if not test:
        _ecrire_etat(etat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
