#!/usr/bin/env python3
"""Branche Telegram sur le robot, sans toucher au reste de .env.

    python3 configurer_telegram.py

POURQUOI CET OUTIL EXISTE. Le 10 septembre 2026, Telegram repondait 404
depuis des jours : le jeton dans `.env` faisait 10 caracteres au lieu de
46, et le chat_id n'etait pas un nombre. Les deux etaient des valeurs
d'essai. Consequence : AUCUNE alerte n'arrivait a l'operateur — ni les
pertes, ni le declenchement du chien de garde, ni les avertissements du
moteur. Le robot croyait prevenir et ne prevenait personne.

CE QU'IL FAIT, ET CE QU'IL NE FAIT PAS.

`.env` porte les cles Bitvavo. Une faute de frappe dedans et le robot ne
demarre plus. Cet outil ne reecrit donc QUE les deux lignes Telegram,
laisse tout le reste octet pour octet, et sauvegarde avant d'ecrire.

Il n'AFFICHE jamais une valeur secrete — ni le jeton que vous tapez, ni
ce que le fichier contenait. C'est volontaire : ce qui s'affiche dans un
terminal partage avec une session Claude part dans la conversation.

Le chat_id n'est pas demande : il est LU chez Telegram apres que vous
avez ecrit au bot. Le recopier a la main est la premiere source d'erreur.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
import urllib.request
from getpass import getpass

RACINE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(RACINE, ".env")

VERT, ROUGE, JAUNE, GRIS, GRAS, FIN = (
    "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[1m", "\033[0m")


def _api(jeton: str, methode: str) -> dict:
    """Appelle l'API Telegram. Les erreurs remontent telles quelles."""
    url = f"https://api.telegram.org/bot{jeton}/{methode}"
    with urllib.request.urlopen(url, timeout=20) as reponse:
        return json.load(reponse)


def _envoyer(jeton: str, chat_id: str, texte: str) -> None:
    donnees = json.dumps({"chat_id": chat_id, "text": texte}).encode()
    requete = urllib.request.Request(
        f"https://api.telegram.org/bot{jeton}/sendMessage",
        data=donnees, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(requete, timeout=20):
        pass


def _ecrire(valeurs: dict[str, str]) -> str:
    """Remplace les lignes demandees dans .env. Rend le chemin de la copie.

    Toute ligne non concernee est recopiee a l'identique — commentaires,
    lignes vides et ordre compris. Une cle absente est ajoutee a la fin.
    """
    with open(ENV, "r", encoding="utf-8") as f:
        lignes = f.readlines()

    copie = ENV + ".avant-telegram"
    shutil.copy2(ENV, copie)

    restantes = dict(valeurs)
    sorties = []
    for ligne in lignes:
        nom = ligne.split("=", 1)[0].strip()
        if nom in restantes:
            sorties.append(f"{nom}={restantes.pop(nom)}\n")
        else:
            sorties.append(ligne)
    if sorties and not sorties[-1].endswith("\n"):
        sorties[-1] += "\n"
    for nom, valeur in restantes.items():
        sorties.append(f"{nom}={valeur}\n")

    with open(ENV, "w", encoding="utf-8") as f:
        f.writelines(sorties)
    os.chmod(ENV, 0o600)
    return copie


def main() -> int:
    if not os.path.exists(ENV):
        print(f"{ROUGE}Fichier .env introuvable dans {RACINE}{FIN}")
        return 1

    print(f"""
{GRAS}  BRANCHER TELEGRAM SUR LE ROBOT{FIN}

  {GRAS}Etape 1{FIN} — creer le bot, sur votre telephone
    Ouvrez Telegram, cherchez  {GRAS}@BotFather{FIN}
    Envoyez-lui  {GRAS}/newbot{FIN}
    Il demande un nom, puis un identifiant finissant par « bot ».
    Il repond avec un jeton, de la forme  {GRIS}1234567890:AAF...{FIN}
    {GRIS}(Si le bot existe deja : envoyez /token et choisissez-le.){FIN}
""")
    # getpass exige un vrai terminal. Lance depuis un contexte qui n'en a
    # pas, il leve — et l'outil mourait sur la premiere question au lieu
    # de faire son travail. On retombe alors sur une saisie ordinaire :
    # moins discret, mais un outil qui marche vaut mieux qu'un outil elegant.
    try:
        jeton = getpass("  Collez le jeton ici (rien ne s'affiche) : ").strip()
    except Exception:                                         # noqa: BLE001
        print(f"{GRIS}  (terminal sans masquage : le jeton sera visible){FIN}")
        try:
            jeton = input("  Collez le jeton ici : ").strip()
        except EOFError:
            print(f"\n{ROUGE}  Impossible de lire la saisie.{FIN}")
            print(f"{GRIS}  Relancez la commande en la prefixant de « ! » "
                  f"dans le terminal Claude, ou depuis un vrai shell.{FIN}")
            return 1
    if not jeton:
        print(f"\n{JAUNE}  Rien saisi — aucune modification.{FIN}")
        return 1

    # Une erreur tres frequente : coller « bot1234:AAA » ou le mot-cle
    # « HTTP API » que BotFather ecrit juste avant le jeton.
    jeton = jeton.split()[-1].removeprefix("bot").strip()

    # On valide AVANT d'ecrire : un .env casse arrete le robot, et un
    # jeton faux ecrit sans controle est exactement ce qui a produit
    # trois jours de 404 silencieux.
    try:
        moi = _api(jeton, "getMe")
    except Exception as exc:                                  # noqa: BLE001
        print(f"\n{ROUGE}  Telegram refuse ce jeton : {str(exc)[:70]}{FIN}")
        print(f"{GRIS}  Rien n'a ete ecrit. Verifiez que vous avez colle la"
              f" ligne ENTIERE, avec le « : » au milieu.{FIN}")
        return 1

    nom_bot = moi.get("result", {}).get("username", "?")
    print(f"\n{VERT}  Jeton valide — c'est le bot @{nom_bot}{FIN}")

    print(f"""
  {GRAS}Etape 2{FIN} — dire bonjour au bot
    Sur Telegram, ouvrez  {GRAS}@{nom_bot}{FIN}  et envoyez-lui n'importe
    quoi ({GRAS}salut{FIN} suffit). C'est ce message qui donne au robot le
    droit de vous ecrire — sans lui, Telegram bloque tout.
    {GRIS}Rien a valider ici : je detecte le message tout seul.{FIN}
""")
    # ON ATTEND LE MESSAGE, ON NE DEMANDE PAS DE CONFIRMER.
    #
    # « Appuyez sur Entree quand c'est fait » ajoute une etape ou l'on
    # peut se tromper, et rate le cas ou le message met dix secondes a
    # arriver. L'outil interroge donc Telegram jusqu'a le voir.
    chats: list[dict] = []
    print(f"  {GRIS}j'attends votre message", end="", flush=True)
    for essai in range(40):                       # ~2 minutes
        try:
            maj = _api(jeton, "getUpdates")
        except Exception as exc:                              # noqa: BLE001
            print(f"\n{ROUGE}  Lecture impossible : {str(exc)[:70]}{FIN}")
            return 1
        for m in maj.get("result", []):
            msg = m.get("message") or m.get("channel_post") or {}
            chat = msg.get("chat") or {}
            if chat.get("id") and chat["id"] not in [c["id"] for c in chats]:
                chats.append(chat)
        if chats:
            break
        print(".", end="", flush=True)
        time.sleep(3)
    print(FIN)

    if not chats:
        print(f"""
{JAUNE}  Aucun message recu.{FIN}
{GRIS}  Le bot n'a pas vu votre message. Deux causes possibles :
    - le message n'est pas parti, ou pas au bon bot (@{nom_bot})
    - un autre programme lit deja les messages de ce bot et les consomme
  Relancez cet outil apres avoir renvoye un message.{FIN}
""")
        return 1

    if len(chats) == 1:
        chat = chats[0]
    else:
        print("\n  Plusieurs conversations trouvees :")
        for n, c in enumerate(chats, 1):
            qui = c.get("first_name") or c.get("title") or "?"
            print(f"    {n}. {qui} ({c.get('type')})")
        choix = input("  Laquelle ? (numero) : ").strip()
        try:
            chat = chats[int(choix) - 1]
        except Exception:                                     # noqa: BLE001
            print(f"{ROUGE}  Choix invalide — rien n'a ete ecrit.{FIN}")
            return 1

    chat_id = str(chat["id"])
    qui = chat.get("first_name") or chat.get("title") or "?"
    print(f"{VERT}  Conversation trouvee : {qui}{FIN}")

    copie = _ecrire({"TELEGRAM_BOT_TOKEN": jeton,
                     "TELEGRAM_CHAT_ID": chat_id,
                     "TELEGRAM_ENABLED": "1"})
    print(f"{VERT}  .env mis a jour{FIN} {GRIS}(copie de securite : "
          f"{os.path.basename(copie)}){FIN}")

    try:
        _envoyer(jeton, chat_id,
                 "Robot de trading : Telegram est branche. "
                 "Vous recevrez desormais les alertes.")
        print(f"{VERT}  Message d'essai envoye — regardez votre telephone.{FIN}")
    except Exception as exc:                                  # noqa: BLE001
        print(f"{ROUGE}  Envoi refuse : {str(exc)[:70]}{FIN}")
        return 1

    print(f"""
{GRAS}  Etape 3 — derniere{FIN}
    Le robot lit .env au demarrage. Pour qu'il prenne le changement :

      {GRAS}sudo systemctl restart robot-dual-live{FIN}

{GRIS}  Le redemarrage est sans risque : les positions ouvertes et leurs
  stops sont deposes chez Bitvavo, ils survivent a l'arret du robot.{FIN}
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
