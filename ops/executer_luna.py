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
import subprocess
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
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        brut = self._requete(
            "GET",
            "/rest/v1/luna_publications"
            "?statut=eq.en_attente&order=created_at.asc&limit=20")
        lignes = []
        for l in json.loads(brut):
            valeur = l.get("scheduled_at")
            if not valeur:
                lignes.append(l)
                continue
            try:
                cible = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
                if cible <= now:
                    lignes.append(l)
            except ValueError:
                # Une date invalide ne doit jamais partir plus tot que prevu.
                continue
        for ligne in lignes:
            brut = self._requete(
                "PATCH",
                f"/rest/v1/luna_publications?id=eq.{ligne['id']}&statut=eq.en_attente",
                json.dumps({"statut": "en_cours"}).encode("utf-8"),
                {"content-type": "application/json",
                 "prefer": "return=representation"})
            reclamees = json.loads(brut)
            if reclamees:
                return reclamees[0]
        return None

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


def _publier_si_demande(ligne: dict, spec, champs: dict, chemin_local: str = "") -> None:
    """Publie sur les plateformes demandees, avec declaration AIGC."""
    if not spec.publish:
        return

    platform = str(ligne.get("platform") or "instagram").lower()
    erreurs = _erreur_existante(ligne)
    from datetime import datetime, timezone

    publiees: list[tuple[str, str]] = []
    en_attente: list[tuple[str, str]] = []

    if platform in {"instagram", "both"}:
        try:
            from ops.instagram import publier_photo_luna, publier_reel_luna, publier_story_luna
            chemin = (
                champs.get("chemin_video") or ligne.get("chemin_video")
                if spec.media_type == "video"
                else champs.get("chemin_photo") or ligne.get("chemin_photo")
            )
            if chemin:
                fmt = str(ligne.get("content_format") or "")
                if fmt in {"story", "highlight_story"}:
                    ident = publier_story_luna(chemin, est_video=(spec.media_type == "video"))
                    if ligne.get("highlight_name"):
                        champs["highlight_status"] = "pending_manual"
                elif spec.media_type == "video":
                    ident = publier_reel_luna(chemin, spec.caption)
                else:
                    ident = publier_photo_luna(chemin, spec.caption)
                publiees.append(("instagram", ident))
        except Exception as exc:
            erreurs["instagram"] = f"{type(exc).__name__} : {str(exc)[:400]}"

    if platform in {"tiktok", "both"} and spec.media_type == "video":
        try:
            from ops.tiktok import publier_video, TikTokErreur
            if os.getenv("TIKTOK_AUTO_PUBLISH", "false").lower() != "true":
                raise TikTokErreur("TIKTOK_AUTO_PUBLISH=false")
            if not chemin_local:
                raise TikTokErreur("fichier video local absent")
            ident = publier_video(chemin_local, spec.caption)
            champs["publication_task_id"] = ident
            champs["publication_status"] = "pending"
            en_attente.append(("tiktok", ident))
        except Exception as exc:
            erreurs["tiktok"] = f"{type(exc).__name__} : {str(exc)[:400]}"

    if publiees and not en_attente:
        champs.update({
            "published_at": datetime.now(timezone.utc).isoformat(),
            "published_platform": ",".join(p[0] for p in publiees),
            "published_media_id": publiees[-1][1],
            "publication_status": "published",
        })
    elif publiees or en_attente:
        champs.update({
            "published_platform": ",".join(
                [p[0] for p in publiees] + [p[0] for p in en_attente]
            ),
            "published_media_id": publiees[-1][1] if publiees else en_attente[-1][1],
            "publication_status": "pending",
        })
    else:
        champs["publication_status"] = "failed"

    champs["erreurs"] = erreurs




def _assembler_clips(clips: list[str], sortie: str, duree_finale: int) -> None:
    """Assemble des clips video et coupe proprement a la duree demandee."""
    liste = sortie + ".concat.txt"
    with open(liste, "w", encoding="utf-8") as fh:
        for chemin in clips:
            fh.write("file '" + chemin.replace("'", "'\\\\''") + "'\n")
    try:
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", liste,
                "-t", str(int(duree_finale)),
                "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,"
                       "pad=720:1280:(ow-iw)/2:(oh-ih)/2",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-movflags", "+faststart", "-y", sortie,
            ],
            check=True, timeout=300,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise MediaErreur(f"assemblage ffmpeg impossible : {exc}") from exc
    finally:
        try:
            os.remove(liste)
        except OSError:
            pass


def _source_video_image(rest: _Rest, ligne: dict, spec) -> tuple[str, str]:
    """Rend (chemin_bucket, url) pour l'image de depart d'une video."""
    from ops.instagram import url_temporaire
    reference = spec.reference_path
    chemin_photo = ligne.get("chemin_photo")
    if reference:
        return reference, url_temporaire(reference)
    if chemin_photo:
        return chemin_photo, url_temporaire(chemin_photo)

    from dataclasses import replace
    frame_spec = replace(spec, media_type="photo", aspect_ratio="9:16", publish=False)
    photo = _chemin_temp(ligne["id"], "photo-start.jpg")
    generer_photo(frame_spec, photo)
    stockage = f"{ligne['id']}/photo.png"
    rest.deposer_fichier(stockage, photo)
    return stockage, url_temporaire(stockage)


def _traiter_tiktok_rewards_long(rest: _Rest, ligne: dict, spec) -> bool:
    """Produit un TikTok de 60-180 s par assemblage de clips AI <= 15 s."""
    id_ = ligne["id"]
    provider = RunwayVideo()
    brut = str(ligne.get("provider_task_id") or "").strip()
    try:
        state = json.loads(brut) if brut.startswith("{") else {}
    except json.JSONDecodeError:
        state = {}
    tasks = list(state.get("tasks") or [])
    duree = max(60, min(180, int(spec.duration_seconds)))
    segment_duree = 15
    segments = (duree + segment_duree - 1) // segment_duree

    stockage, image_url = _source_video_image(rest, ligne, spec)

    # Soumission progressive : une seule nouvelle tache par passage du cron.
    if len(tasks) < segments:
        numero = len(tasks) + 1
        prompt = (
            f"{spec.prompt} This is segment {numero} of {segments}. "
            "Keep Luna's face, outfit and location consistent with the supplied "
            "start image. Make this segment visually complete and suitable for "
            "a cut in a longer original vertical social video."
        )
        task_id = provider.creer(
            image_url, prompt, "9:16", segment_duree
        )
        tasks.append(task_id)
        state = {
            "tasks": tasks,
            "segment_count": segments,
            "segment_duration_seconds": segment_duree,
            "start_image": stockage,
        }
        rest.completer(id_, {
            "provider": "runway-sequence",
            "provider_task_id": json.dumps(state, ensure_ascii=False),
            "generation_status": "generating",
            "assembly_status": "collecting",
            "statut": "en_cours",
        })
        print(f"segment {numero}/{segments} soumis : {id_}")
        return True

    # Toutes les taches sont creees : on attend qu'elles soient toutes terminees.
    urls: list[str] = []
    for task_id in tasks:
        statut, url = provider.resultat(str(task_id))
        if statut == "generating":
            return True
        urls.append(url)

    try:
        clips = []
        for idx, url in enumerate(urls, start=1):
            chemin = _chemin_temp(id_, f"segment-{idx}.mp4")
            telecharger(url, chemin)
            clips.append(chemin)

        final = _chemin_temp(id_, "video.mp4")
        _assembler_clips(clips, final, duree)

        chemin_stockage = f"{id_}/video.mp4"
        rest.deposer_fichier(chemin_stockage, final)

        erreurs = _erreur_existante(ligne)
        champs = {
            "chemin_photo": ligne.get("chemin_photo") or stockage,
            "chemin_video": chemin_stockage,
            "provider": "runway-sequence",
            "provider_task_id": json.dumps(state, ensure_ascii=False),
            "generation_status": "succeeded",
            "assembly_status": "assembled",
            "statut": "terminee",
            "erreurs": erreurs,
        }
        _publier_si_demande(ligne, spec, champs, final)
        rest.completer(id_, champs)
        print(f"TikTok long format assemble : {id_} ({duree}s)")
        return True
    except MediaErreur as exc:
        erreurs = _erreur_existante(ligne)
        erreurs["generation"] = str(exc)[:500]
        rest.completer(id_, {
            "statut": "echec",
            "generation_status": "failed",
            "assembly_status": "failed",
            "provider": "runway-sequence",
            "erreurs": erreurs,
        })
        return True


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
        "content_format": ligne.get("content_format") or "legacy",
        "platform": ligne.get("platform") or "instagram",
        "highlight_name": ligne.get("highlight_name"),
        "monetization_track": ligne.get("monetization_track") or "growth",
        "ai_disclosure": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if spec.media_type == "photo":
        photo = _chemin_temp(id_, "photo.jpg")
        try:
            generer_photo(spec, photo)
            chemin_stockage = f"{id_}/photo.jpg"
            rest.deposer_fichier(chemin_stockage, photo)
            champs.update({
                "chemin_photo": chemin_stockage,
                "provider": spec.provider or "image-fallback-chain",
                "generation_status": "succeeded",
                "statut": "terminee",
                "erreurs": erreurs,
            })
            _publier_si_demande(ligne, spec, champs, photo)
            rest.completer(id_, champs)
            return True
        except Exception as exc:
            erreurs["generation"] = f"{type(exc).__name__} : {str(exc)[:500]}"
            champs.update({"statut": "echec", "generation_status": "failed", "erreurs": erreurs})
            rest.completer(id_, champs)
            return True

    if ligne.get("content_format") == "tiktok_rewards":
        return _traiter_tiktok_rewards_long(rest, ligne, spec)

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
            _publier_si_demande(ligne, spec, champs, video)
            rest.completer(id_, champs)
            print(f"video terminee : {id_}")
            return True
        except MediaErreur as exc:
            erreurs["generation"] = str(exc)[:500]
            champs.update({"statut": "echec", "generation_status": "failed",
                           "provider": "runway", "erreurs": erreurs})
            rest.completer(id_, champs)
            return True

    try:
        from ops.instagram import url_temporaire
        reference = spec.reference_path
        chemin_photo = ligne.get("chemin_photo")
        if reference:
            chemin_photo = reference
            champs["reference_path"] = reference
            image_url = url_temporaire(reference)
        elif not chemin_photo:
            from dataclasses import replace
            frame_spec = replace(spec, media_type="photo",
                                 aspect_ratio="9:16", publish=False)
            photo = _chemin_temp(id_, "photo-start.jpg")
            generer_photo(frame_spec, photo)
            chemin_photo = f"{id_}/photo.png"
            rest.deposer_fichier(chemin_photo, photo)
            champs["chemin_photo"] = chemin_photo
            image_url = url_temporaire(chemin_photo)
        else:
            image_url = url_temporaire(chemin_photo)

        if not chemin_photo:
            raise MediaErreur("video sans image de depart")
        task_id = provider.creer(
            image_url, spec.prompt, spec.aspect_ratio,
            spec.duration_seconds or DEFAULT_VIDEO_DURATION
        )
        champs.update({
            "provider": "runway", "provider_task_id": task_id,
            "generation_status": "generating", "statut": "en_cours",
            "erreurs": erreurs,
        })
        rest.completer(id_, champs)
        print(f"video soumise : {id_} / task {task_id}")
        return True
    except Exception as exc:
        erreurs["generation"] = f"{type(exc).__name__} : {str(exc)[:500]}"
        champs.update({"statut": "echec", "generation_status": "failed", "erreurs": erreurs})
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


def _reprendre_publications_tiktok(rest: _Rest) -> int:
    """Sonde les publications TikTok sans re-uploader la video."""
    lignes = rest.get(
        "/rest/v1/luna_publications?publish_requested=eq.true"
        "&publication_status=eq.pending&platform=in.(tiktok,both)"
        "&publication_task_id=not.is.null&order=created_at.asc&limit=5"
    )
    compte = 0
    for ligne in lignes:
        try:
            from ops.tiktok import statut
            data = statut(str(ligne["publication_task_id"]))
            info = data.get("data") or {}
            etat = str(info.get("status") or "").upper()
            if etat == "PUBLISH_COMPLETE":
                ids = info.get("publicaly_available_post_id") or []
                changes = {
                    "publication_status": "published",
                    "published_at": __import__("datetime").datetime.now(
                        __import__("datetime").timezone.utc
                    ).isoformat(),
                    "published_platform": "tiktok",
                }
                if ids:
                    changes["published_media_id"] = str(ids[0])
                rest.completer(str(ligne["id"]), changes)
                print(f"TikTok publie : {ligne['id']}")
            elif etat == "FAILED":
                erreurs = _erreur_existante(ligne)
                erreurs["tiktok"] = str(info.get("fail_reason") or "publication echouee")[:400]
                rest.completer(str(ligne["id"]), {
                    "publication_status": "failed",
                    "erreurs": erreurs,
                })
                print(f"TikTok echec : {ligne['id']}")
            compte += 1
        except Exception as exc:
            print(f"sondage TikTok impossible pour {ligne.get('id')}: {str(exc)[:180]}")
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
    # Cron toutes les 2 minutes : empeche deux workers de publier le meme
    # media si une execution precedente depasse son intervalle.
    import fcntl
    verrou = open("/tmp/luna-media-worker.lock", "w")
    try:
        fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("worker Luna deja en cours, ce passage saute")
        verrou.close()
        return 0

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
        tiktok = _reprendre_publications_tiktok(rest)
        if tiktok:
            print(f"{tiktok} publication(s) TikTok sondee(s)")
    except Exception as exc:  # noqa: BLE001
        print(f"sondage TikTok impossible : {str(exc)[:200]}")

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
