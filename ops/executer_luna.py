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
from luna.media import (  # noqa: E402
    MediaErreur,
    RunwayVideo,
    DEFAULT_VIDEO_DURATION,
    spec_depuis_demande,
    generer_photo,
    telecharger,
)
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

    def get(self, chemin: str) -> list | dict:
        brut = self._requete("GET", chemin)
        return json.loads(brut or b"[]")

    def upsert(self, table: str, ligne: dict) -> None:
        self._requete(
            "POST", f"/rest/v1/{table}",
            json.dumps(ligne).encode("utf-8"),
            {"content-type": "application/json",
             "prefer": "resolution=merge-duplicates"})

    def liberer_les_bloquees(self, minutes: int = 20) -> int:
        """Remet en attente ce qui traine « en cours » depuis trop longtemps.

        Le `try/except` de `_traiter_une_demande` ne suffit pas : un
        processus TUE (manque de memoire, redemarrage du serveur)
        n'execute aucun `except`. Sans ce filet, une demande reclamee
        juste avant la mort resterait bloquee indefiniment.

        Vingt minutes : bien au-dela d'une generation normale (une a
        deux minutes), assez court pour que Monsieur ne reste pas devant
        un ecran fige.
        """
        import datetime as _dt
        import urllib.parse as _up
        # Encode : le « + » du fuseau (+00:00) serait lu comme un ESPACE
        # dans une adresse, et PostgREST refuse la date en 400. Trouve en
        # posant ce filet, pas apres.
        limite = _up.quote(
            (_dt.datetime.now(_dt.timezone.utc)
             - _dt.timedelta(minutes=minutes)).isoformat(), safe="")
        try:
            reprises = json.loads(self._requete(
                "PATCH",
                f"/rest/v1/luna_publications?statut=eq.en_cours"
                f"&created_at=lt.{limite}&generation_status=neq.generating",
                json.dumps({"statut": "en_attente"}).encode("utf-8"),
                {"content-type": "application/json",
                 "prefer": "return=representation"}) or b"[]")
        except Exception as exc:                              # noqa: BLE001
            print(f"liberation impossible : {str(exc)[:120]}")
            return 0
        if reprises:
            print(f"{len(reprises)} demande(s) bloquee(s) remise(s) en attente")
        return len(reprises)

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




def _chemin_temp(id_: str, nom: str) -> str:
    import tempfile
    dossier = os.path.join(tempfile.gettempdir(), "luna-media", id_)
    os.makedirs(dossier, exist_ok=True)
    return os.path.join(dossier, nom)


def _erreur_existante(ligne: dict) -> dict:
    brut = ligne.get("erreurs")
    return dict(brut) if isinstance(brut, dict) else {}


def _publier_si_demande(ligne: dict, spec, champs: dict) -> None:
    """Publie une fois si Claude a explicitement demande publish=true."""
    if not spec.publish or ligne.get("published_media_id"):
        return
    try:
        from ops.instagram import publier_photo_luna, publier_reel_luna
        if spec.media_type == "video":
            chemin = champs.get("chemin_video") or ligne.get("chemin_video")
            if not chemin:
                return
            ident = publier_reel_luna(chemin, spec.caption)
        else:
            chemin = champs.get("chemin_photo") or ligne.get("chemin_photo")
            if not chemin:
                return
            ident = publier_photo_luna(chemin, spec.caption)
        from datetime import datetime, timezone
        champs.update({
            "published_at": datetime.now(timezone.utc).isoformat(),
            "published_platform": "instagram",
            "published_media_id": ident,
        })
        print(f"publication Instagram terminee : {ident}")
    except Exception as exc:  # noqa: BLE001
        erreurs = _erreur_existante(ligne)
        erreurs["publication"] = f"{type(exc).__name__} : {str(exc)[:400]}"
        champs["erreurs"] = erreurs
        print(f"publication demandee mais impossible : {str(exc)[:200]}")


def _traiter_job_media(rest: _Rest, ligne: dict, spec) -> bool:
    """Traite un job photo, ou lance/reprend une video image->video."""
    id_ = ligne["id"]
    erreurs = _erreur_existante(ligne)
    from datetime import datetime, timezone
    champs = {
        "legende": spec.caption,
        "scene_prompt": spec.prompt,
        "aspect_ratio": spec.aspect_ratio,
        "duration_seconds": spec.duration_seconds or DEFAULT_VIDEO_DURATION,
        "quality": spec.quality,
        "publish_requested": spec.publish,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if spec.media_type == "photo":
        photo = _chemin_temp(id_, "photo.png")
        try:
            generer_photo(spec, photo)
            chemin_stockage = f"{id_}/photo.png"
            rest.deposer_fichier(chemin_stockage, photo)
            champs.update({
                "chemin_photo": chemin_stockage,
                "provider": spec.provider or "image-fallback-chain",
                "generation_status": "succeeded",
                "statut": "terminee",
                "erreurs": erreurs,
            })
            _publier_si_demande(ligne, spec, champs)
            rest.completer(id_, champs)
            return True
        except Exception as exc:  # noqa: BLE001
            erreurs["generation"] = f"{type(exc).__name__} : {str(exc)[:500]}"
            champs.update({
                "statut": "echec",
                "generation_status": "failed",
                "erreurs": erreurs,
            })
            rest.completer(id_, champs)
            return True

    provider = RunwayVideo()
    task_id = str(ligne.get("provider_task_id") or "").strip()
    if task_id:
        try:
            statut, url = provider.resultat(task_id)
            if statut == "generating":
                return True
            video = _chemin_temp(id_, "video.mp4")
            telecharger(url, video)
            chemin_stockage = f"{id_}/video.mp4"
            rest.deposer_fichier(chemin_stockage, video)
            champs.update({
                "chemin_video": chemin_stockage,
                "provider": "runway",
                "generation_status": "succeeded",
                "statut": "terminee",
                "provider_task_id": task_id,
                "erreurs": erreurs,
            })
            _publier_si_demande(ligne, spec, champs)
            rest.completer(id_, champs)
            print(f"video terminee : {id_}")
            return True
        except MediaErreur as exc:
            erreurs["generation"] = str(exc)[:500]
            champs.update({
                "statut": "echec",
                "generation_status": "failed",
                "provider": "runway",
                "erreurs": erreurs,
            })
            rest.completer(id_, champs)
            return True

    try:
        if not ligne.get("chemin_photo"):
            from dataclasses import replace
            frame_spec = replace(
                spec,
                media_type="photo",
                aspect_ratio="9:16",
                publish=False,
            )
            photo = _chemin_temp(id_, "photo-start.png")
            generer_photo(frame_spec, photo)
            chemin_photo = f"{id_}/photo.png"
            rest.deposer_fichier(chemin_photo, photo)
            champs["chemin_photo"] = chemin_photo

        from ops.instagram import url_temporaire
        chemin_photo = champs.get("chemin_photo") or ligne.get("chemin_photo")
        if not chemin_photo:
            raise MediaErreur("video sans image de depart")
        image_url = url_temporaire(chemin_photo)
        task_id = provider.creer(
            image_url,
            spec.prompt,
            spec.aspect_ratio,
            spec.duration_seconds or DEFAULT_VIDEO_DURATION,
        )
        champs.update({
            "provider": "runway",
            "provider_task_id": task_id,
            "generation_status": "generating",
            "statut": "en_cours",
            "erreurs": erreurs,
        })
        rest.completer(id_, champs)
        print(f"video soumise : {id_} / task {task_id}")
        return True
    except Exception as exc:  # noqa: BLE001
        erreurs["generation"] = f"{type(exc).__name__} : {str(exc)[:500]}"
        champs.update({
            "statut": "echec",
            "generation_status": "failed",
            "erreurs": erreurs,
        })
        rest.completer(id_, champs)
        return True


def _reprendre_videos(rest: _Rest) -> int:
    """Sonde les taches video asynchrones sans les relancer."""
    lignes = rest.get(
        "/rest/v1/luna_publications?statut=eq.en_cours"
        "&media_type=eq.video&generation_status=eq.generating"
        "&provider_task_id=not.is.null"
        "&order=created_at.asc&limit=5"
    )
    compte = 0
    for ligne in lignes:
        spec = spec_depuis_demande(ligne.get("demande", ""))
        if spec is None:
            continue
        if _traiter_job_media(rest, ligne, spec):
            compte += 1
    return compte


def _traiter_une_demande(rest: _Rest) -> bool:
    """Rend True si une demande a ete traitee (peu importe le resultat)."""
    ligne = rest.reclamer_en_attente()
    if ligne is None:
        return False

    id_, demande = ligne["id"], ligne.get("demande", "")
    try:
        spec = spec_depuis_demande(demande)
    except MediaErreur as exc:
        rest.completer(id_, {
            "statut": "echec",
            "generation_status": "failed",
            "erreurs": {"contrat_media": str(exc)[:500]},
        })
        return True
    if spec is not None:
        return _traiter_job_media(rest, ligne, spec)

    # UNE DEMANDE RECLAMEE NE DOIT JAMAIS RESTER « EN COURS ».
    #
    # Elle est deja passee en `en_cours` : plus aucun passage ne la
    # reprendra. Si `creer()` leve -- quota d'images epuise, reseau
    # coupe, moteur qui refuse -- la ligne restait bloquee POUR
    # TOUJOURS, et l'application affichait « en génération » sans fin.
    #
    # Constate le 19 sept. : une demande de 17h52 tournait encore a
    # 23h30, alors que les DEUX generateurs d'images gratuits etaient a
    # sec (Hugging Face 402, Cloudflare 429). Monsieur a attendu six
    # heures devant un ecran qui ne lui disait rien.
    #
    # Un echec affiche vaut mieux qu'une attente muette.
    try:
        resultat = creer(demande)
    except Exception as exc:                                  # noqa: BLE001
        print(f"echec traitement : {type(exc).__name__} : {str(exc)[:200]}")
        rest.completer(id_, {
            "statut": "echec",
            "erreurs": {"traitement": f"{type(exc).__name__} : {str(exc)[:400]}"},
        })
        return True

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

    rest.liberer_les_bloquees()

    try:
        videos = _reprendre_videos(rest)
        if videos:
            print(f"{videos} video(s) sondee(s)")
    except Exception as exc:  # noqa: BLE001
        print(f"sondage video impossible : {str(exc)[:200]}")

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
