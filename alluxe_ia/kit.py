"""Le robot KIT de @alluxe.ia : QUOI répondre, sans réseau.

Quelqu'un commente KIT sous un post -> il reçoit le kit en message privé
(prompt n°6 du concept, docs/alluxe_ia/CONCEPT_8_PROMPTS.md).

Ce module décide ; `ops/alluxe_ia_kit.py` exécute. Séparés pour que la
décision se teste sans Instagram (tests/test_alluxe_ia_kit.py).

LES DEUX RÈGLES DE META QUI DESSINENT LA SÉQUENCE
-------------------------------------------------
1. Réponse privée à un commentaire : UN SEUL message, dans les 7 jours.
   Il n'y a donc pas de relance automatique possible : si la personne ne
   répond pas, on n'écrit plus. (Le concept du 3 oct. prévoyait un
   message 4 de relance ; l'API ne l'autorise pas, il est retiré.)
2. Dès que la personne répond, on a 24 heures pour lui écrire.
   Au-delà, plus rien d'automatique.
"""
from __future__ import annotations

import datetime as dt
import re
import zlib
from dataclasses import dataclass, field

FENETRE = dt.timedelta(hours=23)          # marge sous les 24 h de Meta
DELAI_COMMENTAIRE = dt.timedelta(days=6)  # marge sous les 7 jours

_KIT = re.compile(r"(?<![\w])kit(?![\w])", re.IGNORECASE)

# Quand Meta refuse le message privé (application pas encore vérifiée par
# Meta : en mode Développement, seuls les testeurs peuvent recevoir un
# message), on ne prétend pas l'avoir envoyé : on renvoie au lien de la bio.
REPONSE_BIO = "Le kit est en lien dans ma bio 👆"

REPONSES_PUBLIQUES = (
    "Envoyé en privé 👀",
    "Regarde tes messages !",
    "C'est parti, je t'ai écrit.",
)

MESSAGE_ZERO = (
    "Parfait, c'est exactement là où j'étais. Le premier prompt du kit "
    "(le cahier des charges) est celui qui m'a fait gagner le plus de "
    "temps. Tu voudrais construire quoi, toi ? Même une idée floue, ça "
    "m'aide à te répondre.")

MESSAGE_COMMENCE = (
    "Top ! Tu bloques plutôt sur quoi : l'IA qui oublie ce que tu lui as "
    "dit, ou les bugs qu'elle ne trouve pas ? J'ai un post sur chacun.")


def message_kit(lien: str, deja_recu: bool = False) -> str:
    if deja_recu:
        return (f"Re ! Le kit est toujours là : {lien}\n"
                "Si tu bloques sur un prompt, réponds-moi ici.")
    return (f"Salut ! Voilà le kit : {lien}\n"
            "Dedans, les prompts que j'utilise vraiment pour construire mes "
            "systèmes, dans l'ordre où je m'en sers.\n"
            "Petite question pour savoir quoi t'envoyer ensuite : tu pars de "
            "zéro, ou tu as déjà construit quelque chose avec l'IA ?")


def message_offre(lien: str) -> str:
    return (f"Je te partage l'outil que j'utilise pour ça. C'est lui qui fait "
            f"tourner mon labo depuis des semaines : {lien}\n"
            "(Publicité : c'est un lien partenaire, ça ne change rien pour toi "
            "et ça soutient le compte.) Si tu veux, je te dis comment je l'ai "
            "réglé.")


def demande_kit(texte: str | None) -> bool:
    return bool(texte and _KIT.search(texte))


_ZERO = ("zero", "zéro", "debut", "début", "debutant", "débutant", "rien",
         "jamais", "novice", "pas encore")
_COMMENCE = ("deja", "déjà", "commence", "commencé", "construit", "j'ai fait",
             "en cours")


def profil(texte: str | None) -> str | None:
    """« zero », « commence », ou None si la réponse ne dit rien de clair
    (alors un humain répond : on ne devine pas)."""
    t = (texte or "").strip().lower()
    if t in ("zero", "commence"):
        return t
    z = any(m in t for m in _ZERO)
    c = any(m in t for m in _COMMENCE)
    if z and not c:
        return "zero"
    if c and not z:
        return "commence"
    return None


@dataclass
class Action:
    genre: str          # reponse_publique | reponse_privee | message
    cible: str          # id du commentaire, ou id Instagram de la personne
    texte: str


@dataclass
class Decision:
    actions: list[Action] = field(default_factory=list)
    contact: dict = field(default_factory=dict)   # champs à mettre à jour
    resultat: str = ""


def _horodatage(v) -> dt.datetime | None:
    if not v:
        return None
    if isinstance(v, dt.datetime):
        return v
    return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def decider(ev: dict, contact: dict | None, maintenant: dt.datetime,
            lien_kit: str, lien_offre: str = "") -> Decision:
    """Ce qu'il faut faire pour UN évènement venu du webhook."""
    contact = contact or {}
    etape = int(contact.get("etape") or 0)
    recu = _horodatage(ev.get("recu_at")) or maintenant

    if ev["type"] == "commentaire":
        if not demande_kit(ev.get("texte")):
            return Decision(resultat="pas KIT")
        if maintenant - recu > DELAI_COMMENTAIRE:
            return Decision(resultat="trop ancien (7 jours de Meta)")
        n = zlib.crc32(ev["ident"].encode()) % len(REPONSES_PUBLIQUES)
        deja = bool(contact.get("kit_envoye_at"))
        return Decision(
            actions=[
                Action("reponse_publique", ev["ident"], REPONSES_PUBLIQUES[n]),
                Action("reponse_privee", ev["ident"], message_kit(lien_kit, deja)),
            ],
            contact={"username": ev.get("username"),
                     "kit_envoye_at": maintenant.isoformat(),
                     "etape": max(etape, 1)},
            resultat="kit renvoyé" if deja else "kit envoyé")

    # Un message privé de la personne.
    if maintenant - recu > FENETRE:
        return Decision(resultat="hors fenêtre de 24 h")
    base = {"derniere_reponse_at": recu.isoformat()}
    qui = ev["ig_user_id"]
    if etape == 1:
        p = profil(ev.get("texte"))
        if p is None:
            return Decision(contact=base, resultat="réponse à lire par un humain")
        texte = MESSAGE_ZERO if p == "zero" else MESSAGE_COMMENCE
        return Decision(actions=[Action("message", qui, texte)],
                        contact={**base, "etape": 2, "profil": p},
                        resultat=f"qualification envoyée ({p})")
    if etape == 2 and lien_offre:
        return Decision(actions=[Action("message", qui, message_offre(lien_offre))],
                        contact={**base, "etape": 3},
                        resultat="offre envoyée")
    return Decision(contact=base if etape else {},
                    resultat="à lire par un humain" if etape else "inconnu, ignoré")


def commentaires_releves(medias: dict[str, list[dict]], compte_id: str,
                         compte_nom: str) -> list[dict]:
    """Les commentaires lus par l'API, au format de `alluxe_ia_evenements`.

    `medias` : {id du post: [commentaires tels que rendus par
    GET /{media}/comments?fields=id,text,timestamp,username,from]}.
    Ceux du compte lui-même (ses propres réponses) sont écartés, sinon le
    robot se répondrait.
    """
    sortie = []
    for media_id, commentaires in medias.items():
        for c in commentaires:
            auteur = (c.get("from") or {}).get("id") or ""
            nom = c.get("username") or (c.get("from") or {}).get("username")
            if not c.get("id") or auteur == compte_id or (nom and nom == compte_nom):
                continue
            if not auteur:
                # Sans identifiant d'auteur, impossible de suivre la personne.
                continue
            ev = {"ident": str(c["id"]), "type": "commentaire",
                  "ig_user_id": str(auteur), "username": nom,
                  "texte": c.get("text"), "media_id": str(media_id)}
            if c.get("timestamp"):
                ev["recu_at"] = c["timestamp"]
            sortie.append(ev)
    return sortie
