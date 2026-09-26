"""La bibliotheque de Luna : tout ce qui a ete genere, publie ou non.

POURQUOI ELLE EXISTE

Le 26 septembre au soir, l'inventaire a donne : **34 fichiers, 136 Mo**
de photos et de videos de Luna, posees sur le disque du serveur et
NULLE PART ailleurs. Dix seulement avaient atteint le stockage
Supabase, trois etaient rattachees a une ligne en base. Le reste
n'existait que dans `data/luna-profil/` — un repertoire qu'un
`git clean`, un disque plein ou une reinstallation efface sans
sommation.

Or ces fichiers ont coute de l'argent : 3,63 EUR ce jour-la, et le prix
monte a chaque image. Les perdre, c'est les repayer.

Demande de l'operateur : « toutes les publications, reel, video, image,
stockees dans un sous-onglet Luna pour avoir toujours une trace des
photos et videos generees, publiees ou non. Ce sera la bibliotheque et
memoire image et video. »

CE QU'ELLE N'EST PAS : la file d'attente. `luna_publications` est une
file de TRAVAIL — une ligne y nait d'une demande et meurt quand elle est
traitee. La bibliotheque est une MEMOIRE : rien n'en sort jamais.
Melanger les deux ferait disparaitre les brouillons le jour d'un
nettoyage, et ce sont justement eux qu'on veut garder — on n'a aucune
idee de ce qui resservira dans trois mois.

    deposer("data/luna-profil/essai.png", moteur="openai",
            modele="gpt-image-2", prompt=..., cout_eur=0.07)

Le fichier part dans le seau `luna` sous `bibliotheque/`, et la ligne
porte de quoi le REFAIRE : le moteur, le modele, la scene demandee.
C'est la difference entre une archive et un tas de fichiers.
"""
from __future__ import annotations

import datetime as dt
import json
import mimetypes
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SEAU = "luna"
PREFIXE = "bibliotheque"

#: Ce qui distingue une image d'une video, sans deviner sur l'extension
#: seule — un `.mp4` renomme `.png` casserait l'affichage de l'onglet.
GENRES = {"image": {".png", ".jpg", ".jpeg", ".webp"},
          "video": {".mp4", ".mov", ".webm"},
          "audio": {".mp3", ".m4a", ".wav", ".ogg"}}


class BibliothequeErreur(RuntimeError):
    pass


def _identifiants() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        raise BibliothequeErreur("SUPABASE_URL / SUPABASE_SERVICE_KEY absents")
    return url, cle


def genre_de(chemin: Path) -> str:
    suffixe = chemin.suffix.lower()
    for genre, suffixes in GENRES.items():
        if suffixe in suffixes:
            return genre
    return "image"


def _dimensions(chemin: Path, genre: str) -> dict:
    """Taille et duree, si on peut les lire. Jamais bloquant.

    Une image dont on ne sait pas mesurer les cotes reste une image
    qu'on veut garder : l'absence de metadonnee ne doit pas empecher
    l'archivage.
    """
    infos: dict = {"octets": chemin.stat().st_size}
    try:
        if genre == "image":
            from PIL import Image
            with Image.open(chemin) as im:
                infos["largeur"], infos["hauteur"] = im.size
        elif genre == "video":
            r = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", "-show_format", str(chemin)],
                capture_output=True, text=True, timeout=60)
            d = json.loads(r.stdout)
            flux = [s for s in d.get("streams", [])
                    if s.get("codec_type") == "video"]
            if flux:
                infos["largeur"] = flux[0].get("width")
                infos["hauteur"] = flux[0].get("height")
            duree = d.get("format", {}).get("duration")
            if duree:
                infos["duree_s"] = round(float(duree), 2)
    except Exception:                                          # noqa: BLE001
        pass
    return infos


def deposer(chemin_local: str | Path, *, moteur: str = "", modele: str = "",
            prompt: str = "", cout_eur: float = 0.0,
            nom_distant: str = "") -> dict | None:
    """Archive un fichier et rend sa ligne. `None` s'il etait deja la.

    IDEMPOTENT PAR CONSTRUCTION. Le chemin distant est unique en base :
    relancer un script d'archivage ne cree pas de doublon, il ignore ce
    qui est deja range. C'est ce qui permet de le passer sur tout un
    repertoire sans reflechir.
    """
    chemin = Path(chemin_local)
    if not chemin.is_file():
        raise BibliothequeErreur(f"fichier introuvable : {chemin}")

    url, cle = _identifiants()
    genre = genre_de(chemin)
    # Le jour dans le chemin : une bibliotheque qui grossit se parcourt
    # par date, et le stockage Supabase se navigue par dossiers.
    jour = dt.datetime.now(dt.timezone.utc).date().isoformat()
    distant = f"{PREFIXE}/{jour}/{nom_distant or chemin.name}"

    entetes = {"apikey": cle, "Authorization": f"Bearer {cle}"}
    mime = mimetypes.guess_type(chemin.name)[0] or "application/octet-stream"
    octets = chemin.read_bytes()
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/storage/v1/object/{SEAU}/{distant}", data=octets,
            method="POST",
            headers={**entetes, "Content-Type": mime, "x-upsert": "true"}),
            timeout=600).read()
    except urllib.error.HTTPError as e:
        raise BibliothequeErreur(
            f"depot refuse : {e.code} {e.read()[:200]!r}") from e

    ligne = {"chemin": distant, "genre": genre, "moteur": moteur,
             "modele": modele, "prompt": prompt[:4000],
             "cout_eur": round(float(cout_eur), 4),
             **_dimensions(chemin, genre)}
    corps = json.dumps(ligne).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"{url}/rest/v1/luna_bibliotheque", data=corps, method="POST",
                headers={**entetes, "Content-Type": "application/json",
                         "Prefer": "return=representation"}), timeout=60) as r:
            return json.loads(r.read())[0]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        # 23505 = doublon sur `chemin`. Ce n'est PAS une erreur : le
        # fichier est deja archive, on l'a juste remis a jour.
        if "23505" in detail or "duplicate key" in detail:
            return None
        raise BibliothequeErreur(f"enregistrement refuse : {detail[:250]}") from e


def marquer_publiee(chemin_distant: str, identifiant: str,
                    plateforme: str = "instagram") -> None:
    """Note qu'un media de la bibliotheque est parti en ligne.

    La ligne n'est jamais supprimee ni deplacee : une image publiee
    reste dans la bibliotheque, avec sa date de publication en plus.
    """
    url, cle = _identifiants()
    corps = json.dumps({
        "publiee_le": dt.datetime.now(dt.timezone.utc).isoformat(),
        "publiee_id": identifiant, "plateforme": plateforme}).encode()
    filtre = urllib.parse.quote(chemin_distant, safe="")
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{url}/rest/v1/luna_bibliotheque?chemin=eq.{filtre}",
            data=corps, method="PATCH",
            headers={"apikey": cle, "Authorization": f"Bearer {cle}",
                     "Content-Type": "application/json",
                     "Prefer": "return=minimal"}), timeout=60).read()
    except urllib.error.HTTPError as e:
        raise BibliothequeErreur(
            f"mise a jour refusee : {e.read()[:200]!r}") from e

