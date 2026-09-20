"""Publier sur Instagram pour Luna — API officielle, connexion Instagram.

POURQUOI CE FICHIER EXISTE, ET CE QU'IL REMPLACE
================================================

Le depot portait `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` : de
l'automatisation non officielle, qui pilote l'application comme le ferait
un humain. C'est la cause numero un des comptes bannis, et un compte
d'influenceuse banni ne se recupere pas.

Ce module passe par l'API OFFICIELLE (« Instagram API with Instagram
Login », branchee le 20 septembre 2026). Elle ne demande AUCUNE page
Facebook — c'est le chemin court, trouve apres deux soirees perdues sur
le chemin long, qui lui exige un compte Business, une page, et un compte
Instagram relie a cette page.

LA PUBLICATION SE FAIT EN DEUX TEMPS, et c'est impose par Instagram :

    1. on depose un « conteneur » avec l'URL de l'image et la legende
    2. on le publie

Entre les deux, Instagram telecharge l'image DEPUIS L'URL FOURNIE. Elle
doit donc etre publiquement accessible — un fichier local ne marche pas,
et c'est le piege qui fait perdre du temps la premiere fois. Les photos
de Luna vivent dans le seau Supabase `luna`, qui sert des URL publiques :
c'est ce qu'on lui donne.

LE JETON DURE 60 JOURS et se renouvelle tant qu'on le rafraichit avant
l'echeance. `rafraichir()` le fait ; il faut l'appeler au moins une fois
tous les deux mois, sinon il faut tout refaire a la main.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

BASE = "https://graph.instagram.com/v21.0"


class InstagramErreur(RuntimeError):
    pass


def _appel(methode: str, chemin: str, **params) -> dict:
    params["access_token"] = _jeton()
    url = f"{BASE}/{chemin}"
    donnees = None
    if methode == "POST":
        donnees = urllib.parse.urlencode(params).encode()
    else:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, data=donnees, method=methode)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        raise InstagramErreur(f"HTTP {e.code} sur {chemin} : {detail}") from e


def _jeton() -> str:
    j = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    if not j:
        raise InstagramErreur(
            "INSTAGRAM_ACCESS_TOKEN absent : refaire l'autorisation")
    return j


def _compte() -> str:
    c = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    if not c:
        raise InstagramErreur("INSTAGRAM_USER_ID absent")
    return c


def qui_suis_je() -> dict:
    """Le compte relie, son type et son nombre de publications."""
    return _appel("GET", "me",
                  fields="id,username,account_type,media_count")


def url_temporaire(chemin: str, seau: str = "luna",
                   secondes: int = 3600) -> str:
    """Un lien PUBLIC et LIMITE DANS LE TEMPS vers une photo de Luna.

    POURQUOI PAS UN SEAU PUBLIC. Instagram telecharge l'image depuis
    l'URL qu'on lui donne, donc elle doit etre joignable sans clef. La
    solution facile serait de rendre le seau `luna` public -- et alors
    TOUTES les photos deviendraient accessibles a qui connait le chemin,
    y compris les brouillons et les ratees, definitivement.

    Un lien signe repond a la meme question sans cette contrepartie : il
    s'ouvre a tous pendant une heure, puis il meurt. Instagram n'a besoin
    que de quelques secondes.
    """
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = (os.environ.get("SUPABASE_SERVICE_KEY")
           or os.environ.get("SUPABASE_KEY", ""))
    if not base or not cle:
        raise InstagramErreur("SUPABASE_URL / SUPABASE_SERVICE_KEY absents")
    req = urllib.request.Request(
        f"{base}/storage/v1/object/sign/{seau}/{chemin}",
        data=json.dumps({"expiresIn": int(secondes)}).encode(),
        headers={"apikey": cle, "Authorization": f"Bearer {cle}",
                 "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            signe = json.loads(r.read().decode())["signedURL"]
    except urllib.error.HTTPError as e:
        raise InstagramErreur(
            f"signature refusee pour {chemin} : {e.read().decode()[:200]}") from e
    return f"{base}/storage/v1{signe}" if signe.startswith("/") else signe


def publier_photo_luna(chemin: str, legende: str = "") -> str:
    """Publie une photo rangee dans le seau `luna`, par son chemin."""
    return publier(url_temporaire(chemin), legende)


def publier(image_url: str, legende: str = "",
            attente_max: float = 60.0) -> str:
    """Publie une photo. Rend l'identifiant de la publication.

    `image_url` doit etre PUBLIQUE : Instagram la telecharge lui-meme.
    """
    if not image_url.lower().startswith("https://"):
        raise InstagramErreur(
            f"l'image doit etre une URL publique en https, recu : {image_url[:60]}")

    conteneur = _appel("POST", f"{_compte()}/media",
                       image_url=image_url, caption=legende)
    cid = conteneur.get("id")
    if not cid:
        raise InstagramErreur(f"aucun conteneur rendu : {conteneur}")

    # INSTAGRAM TELECHARGE L'IMAGE EN TACHE DE FOND. Publier trop tot
    # echoue avec un message qui ne dit pas pourquoi ; on attend que le
    # conteneur soit pret, et on abandonne proprement s'il ne l'est pas.
    fin = time.time() + attente_max
    while time.time() < fin:
        etat = _appel("GET", cid, fields="status_code,status")
        code = etat.get("status_code")
        if code == "FINISHED":
            break
        if code == "ERROR":
            raise InstagramErreur(f"conteneur en erreur : {etat.get('status')}")
        time.sleep(3)
    else:
        raise InstagramErreur(
            f"conteneur toujours pas pret apres {attente_max:.0f} s")

    publiee = _appel("POST", f"{_compte()}/media_publish", creation_id=cid)
    ident = publiee.get("id")
    if not ident:
        raise InstagramErreur(f"publication refusee : {publiee}")
    log.info("publie sur Instagram : %s", ident)
    return ident


def rafraichir() -> int:
    """Repousse l'echeance du jeton. Rend le nombre de jours restants.

    A appeler au moins une fois tous les deux mois. Le nouveau jeton doit
    etre reecrit dans .env par l'appelant -- ce module ne touche jamais
    au fichier de secrets.
    """
    r = _appel("GET", "refresh_access_token", grant_type="ig_refresh_token")
    if "access_token" not in r:
        raise InstagramErreur(f"renouvellement refuse : {r}")
    jours = int(r.get("expires_in", 0)) // 86400
    log.info("jeton Instagram renouvele : %d jours", jours)
    return jours


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(json.dumps(qui_suis_je(), ensure_ascii=False, indent=2))
