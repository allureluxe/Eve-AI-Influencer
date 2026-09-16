#!/usr/bin/env python3
"""Traite la file des generations Luna demandees depuis l'application.

Meme principe que les autres scripts de `ops/` : l'app ne touche jamais
au VPS directement, elle depose une ligne dans `luna_publications`
(statut `en_attente`) via Supabase, et ce script -- lance par cron --
la prend en charge :

    */2 * * * *  cd .../Eve-AI-Influencer && ops/executer_luna.py

Republie aussi `luna_persona` a chaque tour (cout negligeable), pour
que l'app affiche toujours le personnage tel qu'il est reellement
configure dans `luna/persona.py`, sans etape manuelle a part.

Se relance sous .venv-luna, comme alluxe_v2.py : c'est la que vivent
edge-tts/gTTS, separes du .venv du robot de trading.
"""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _relancer_sous_venv_si_besoin() -> None:
    venv_python = os.path.join(RACINE, ".venv-luna", "bin", "python3")
    deja_dedans = os.path.abspath(sys.executable) == os.path.abspath(venv_python)
    if os.path.exists(venv_python) and not deja_dedans:
        os.execv(venv_python, [venv_python] + sys.argv)


_relancer_sous_venv_si_besoin()
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from luna.alluxe_v2 import creer  # noqa: E402
from luna.persona import LUNA  # noqa: E402


def _rest(url_projet: str, cle: str) -> "_Rest":
    return _Rest(url_projet.rstrip("/"), cle)


class _Rest:
    """Petit client REST/Storage Supabase, en service_role -- contourne la
    RLS volontairement (ce script EST le service qui remplit les tables
    que l'app ne fait que lire)."""

    def __init__(self, url_projet: str, cle: str) -> None:
        self.url = url_projet
        self.cle = cle

    def _requete(self, methode: str, chemin: str, corps: bytes | None = None,
                 entetes: dict | None = None) -> bytes:
        h = {"apikey": self.cle, "authorization": f"Bearer {self.cle}",
             **(entetes or {})}
        r = urllib.request.Request(f"{self.url}{chemin}", data=corps,
                                    headers=h, method=methode)
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.read()

    def upsert(self, table: str, ligne: dict) -> None:
        self._requete(
            "POST", f"/rest/v1/{table}",
            json.dumps(ligne).encode("utf-8"),
            {"content-type": "application/json",
             "prefer": "resolution=merge-duplicates"})

    def reclamer_en_attente(self) -> dict | None:
        """Prend la plus ancienne demande `en_attente`, en la marquant
        `en_cours` de facon atomique -- si un autre passage l'a deja
        prise (cron precedent encore en cours), le PATCH renvoie 0 ligne
        et on ne fait rien."""
        brut = self._requete(
            "GET",
            "/rest/v1/luna_publications"
            "?statut=eq.en_attente&order=created_at.asc&limit=1")
        lignes = json.loads(brut)
        if not lignes:
            return None
        ligne = lignes[0]
        brut = self._requete(
            "PATCH",
            f"/rest/v1/luna_publications?id=eq.{ligne['id']}&statut=eq.en_attente",
            json.dumps({"statut": "en_cours"}).encode("utf-8"),
            {"content-type": "application/json", "prefer": "return=representation"})
        reclamees = json.loads(brut)
        return reclamees[0] if reclamees else None

    def completer(self, id_: str, champs: dict) -> None:
        self._requete(
            "PATCH", f"/rest/v1/luna_publications?id=eq.{id_}",
            json.dumps(champs).encode("utf-8"),
            {"content-type": "application/json"})

    def deposer_fichier(self, chemin_stockage: str, chemin_local: str) -> None:
        type_mime = mimetypes.guess_type(chemin_local)[0] or "application/octet-stream"
        with open(chemin_local, "rb") as f:
            self._requete(
                "POST", f"/storage/v1/object/luna/{chemin_stockage}",
                f.read(), {"content-type": type_mime, "x-upsert": "true"})


def _publier_persona(rest: _Rest) -> None:
    rest.upsert("luna_persona", {
        "id": "luna",
        "prenom": LUNA.prenom, "age": LUNA.age, "metier": LUNA.metier,
        "contexte": LUNA.contexte,
        "caractere": list(LUNA.caractere), "passions": list(LUNA.passions),
    })


def _traiter_une_demande(rest: _Rest) -> bool:
    """Rend True si une demande a ete traitee (peu importe le resultat)."""
    ligne = rest.reclamer_en_attente()
    if ligne is None:
        return False

    id_, demande = ligne["id"], ligne.get("demande", "")
    resultat = creer(demande)

    champs: dict = {
        "legende": resultat.legende, "scene_prompt": resultat.scene_prompt,
        "erreurs": resultat.erreurs,
    }
    for cle, chemin_local, nom_fichier in (
        ("chemin_photo", resultat.chemin_image, "photo.png"),
        ("chemin_voix", resultat.chemin_voix, "voix.mp3"),
        ("chemin_video", resultat.chemin_video, "video.mp4"),
    ):
        if not chemin_local:
            continue
        chemin_stockage = f"{id_}/{nom_fichier}"
        rest.deposer_fichier(chemin_stockage, chemin_local)
        champs[cle] = chemin_stockage

    # "terminee" des que le script a produit une legende, meme si photo/
    # voix/video ont echoue a cote -- le meme principe de degradation
    # partielle que `Resultat` lui-meme (voir luna/alluxe_v2.py). "echec"
    # seulement quand rien n'est exploitable.
    champs["statut"] = "terminee" if resultat.legende else "echec"
    rest.completer(id_, champs)
    return True


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        print("SUPABASE_URL ou SUPABASE_SERVICE_KEY absent, rien fait")
        return 1
    rest = _rest(url, cle)

    try:
        _publier_persona(rest)
    except urllib.error.HTTPError as e:
        print(f"persona non publiee : HTTP {e.code} {e.read()[:200]!r}")

    try:
        traite = _traiter_une_demande(rest)
    except urllib.error.HTTPError as e:
        print(f"echec traitement : HTTP {e.code} {e.read()[:200]!r}")
        return 1
    print("demande traitee" if traite else "aucune demande en attente")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
