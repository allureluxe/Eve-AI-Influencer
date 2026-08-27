"""Ligne de commande de Luna.

    python3 luna.py app                 lance l'application (messages, appel, visio)
    python3 luna.py chat                conversation dans le terminal
    python3 luna.py dis "coucou"        un seul message
    python3 luna.py photo lingerie      le prompt (et l'image si configuree)
    python3 luna.py profil              qui elle est, ce qu'elle sait de toi
    python3 luna.py oublier             efface sa memoire
    python3 luna.py check               ce qui est configure, ce qui manque
"""
from __future__ import annotations

import os
import sys

from . import limites
from .chat import Luna
from .memoire import Memoire
from .moteurs import ErreurMoteur, GenerateurImages, choisir_moteur
from .persona import LUNA
from .photos import SCENES, prompt_photo
from .serveur import DOSSIER_DONNEES, lancer


def _luna() -> Luna:
    porte = limites.PorteAdulte(os.path.join(DOSSIER_DONNEES, "acces.json"))
    return Luna(memoire=Memoire(os.path.join(DOSSIER_DONNEES, "memoire.json")),
                porte=porte)


def commande_chat() -> int:
    luna = _luna()
    print(f"— {LUNA.prenom}, {LUNA.age} ans. Personnage IA fictif. "
          f"Ctrl+C pour partir. —\n")
    ouverture = luna.ouverture(canal="console")
    print(f"Luna : {ouverture.texte}\n")
    while True:
        try:
            texte = input("Toi  : ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nLuna : A tout a l'heure ❤️")
            return 0
        if not texte:
            continue
        if texte in ("/quit", "/exit"):
            print("Luna : A tout a l'heure ❤️")
            return 0
        reponse = luna.repondre(texte, canal="console")
        print(f"\nLuna : {reponse.texte}\n")


def commande_dis(message: str) -> int:
    reponse = _luna().repondre(message, canal="console")
    print(reponse.texte)
    return 0 if not reponse.erreur else 1


def commande_photo(scene: str) -> int:
    luna = _luna()
    registre = luna.registre_effectif("console")
    if not scene:
        for s in SCENES:
            marque = " (18+)" if s.registre != limites.TENDRE else ""
            print(f"  {s.cle:<12} {s.titre}{marque}")
        return 0
    try:
        demande = prompt_photo(scene, registre)
    except KeyError:
        print(f"Scene inconnue : {scene}")
        return 1
    except PermissionError as e:
        print(f"{e}. Confirme 18+ dans l'application d'abord.")
        return 1
    print(demande["titre"])
    print(f"  legende : {demande['legende']}")
    print(f"  graine  : {demande['graine']}")
    print(f"  prompt  : {demande['prompt']}")
    images = GenerateurImages()
    if not images.disponible:
        print("\n  (aucune cle d'images configuree : prompt seul)")
        return 0
    try:
        brut = images.generer(demande["prompt"], demande["negatif"], demande["graine"])
    except ErreurMoteur as e:
        print(f"\n  generation impossible : {e}")
        return 1
    os.makedirs("generated_images", exist_ok=True)
    chemin = os.path.join("generated_images", f"luna_{scene}.png")
    with open(chemin, "wb") as f:
        f.write(brut)
    print(f"\n  image : {chemin}")
    return 0


def commande_profil() -> int:
    luna = _luna()
    print(LUNA.presentation())
    print("\nCaractere :")
    for t in LUNA.caractere:
        print(f"  - {t}")
    print("\nPassions : " + ", ".join(LUNA.passions))
    print(f"\nMoment : {luna.moment().nom}")
    print(f"Registre effectif : {luna.registre_effectif('console')}")
    print(f"Acces 18+ : {'oui' if luna.porte.acces.majeur else 'non'}")
    print("\nCe qu'elle sait de toi :\n" + luna.memoire.resume())
    return 0


def commande_oublier() -> int:
    luna = _luna()
    luna.memoire.oublier()
    print("Memoire effacee.")
    return 0


def commande_check() -> int:
    moteur = choisir_moteur()
    images = GenerateurImages()
    print(f"moteur de conversation : {moteur.nom}")
    if moteur.nom == "hors-ligne":
        print("  → ajoute ANTHROPIC_API_KEY (ou LUNA_API_URL + LUNA_API_MODELE) dans .env")
    print(f"generateur d'images    : {'pret' if images.disponible else 'non configure'}")
    print(f"donnees                : {os.path.abspath(DOSSIER_DONNEES)}")
    print(f"jeton reseau           : {'defini' if os.getenv('LUNA_TOKEN') else 'aucun (local seulement)'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "aide"):
        print(__doc__)
        return 0
    commande, reste = argv[0], argv[1:]

    if commande == "app":
        hote = "127.0.0.1"
        port = int(os.getenv("LUNA_PORT", "8765"))
        if "--hote" in reste:
            hote = reste[reste.index("--hote") + 1]
        if "--port" in reste:
            port = int(reste[reste.index("--port") + 1])
        lancer(hote, port)
        return 0
    if commande == "chat":
        return commande_chat()
    if commande == "dis":
        if not reste:
            print("Il manque le message : python3 luna.py dis \"coucou\"")
            return 1
        return commande_dis(" ".join(reste))
    if commande == "photo":
        return commande_photo(reste[0] if reste else "")
    if commande == "profil":
        return commande_profil()
    if commande == "oublier":
        return commande_oublier()
    if commande == "check":
        return commande_check()

    print(f"Commande inconnue : {commande}\n")
    print(__doc__)
    return 1
