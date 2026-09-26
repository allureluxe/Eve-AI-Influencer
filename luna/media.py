"""Adaptateurs média pour les jobs Luna pilotes par Claude.

- Claude choisit le prompt, la legende et l'intention de publication.
- Le worker VPS fait la generation reelle.
- Supabase garde l'etat durable du job.
- Runway est l'adaptateur video asynchrone integre.
- La generation photo reutilise GenerateurImages.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .moteurs import ErreurMoteur, GenerateurImages
from .persona import LUNA
from .photos import NEGATIF, RENDU, SIGNATURE

log = logging.getLogger(__name__)

ASPECTS = {
    "1:1": "carre",
    "3:4": "portrait_3_4",
    "4:5": "portrait",
    "2:3": "portrait",
    "3:2": "paysage",
    "4:3": "paysage",
    "9:16": "portrait_9_16",
    "16:9": "paysage_16_9",
}

DEFAULT_PHOTO_RATIO = "3:4"
DEFAULT_VIDEO_RATIO = "9:16"
DEFAULT_VIDEO_DURATION = 10


class MediaErreur(RuntimeError):
    pass


@dataclass(frozen=True)
class MediaSpec:
    media_type: str
    prompt: str
    caption: str = ""
    reference_path: str = ""
    aspect_ratio: str = DEFAULT_PHOTO_RATIO
    duration_seconds: int = DEFAULT_VIDEO_DURATION
    quality: str = "finale"
    provider: str = ""
    model: str = ""
    publish: bool = False


def _entier(valeur: object, defaut: int, minimum: int, maximum: int) -> int:
    try:
        n = int(valeur)
    except (TypeError, ValueError):
        return defaut
    return max(minimum, min(maximum, n))


def spec_depuis_demande(demande: str | dict) -> MediaSpec | None:
    """Decode une demande structuree.

    Une demande non JSON (ancien bouton de l'application) rend None :
    l'appelant doit alors conserver le pipeline legacy.
    """
    if isinstance(demande, dict):
        objet = demande
    else:
        try:
            objet = json.loads(demande)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    if not isinstance(objet, dict):
        return None

    typ = str(objet.get("type") or objet.get("media_type") or "").strip().lower()
    if typ not in {"photo", "video"}:
        return None
    content_format = str(objet.get("content_format") or "").strip().lower()

    prompt = str(objet.get("prompt") or objet.get("scene_prompt") or "").strip()
    if not prompt:
        raise MediaErreur("job media sans prompt")

    ratio_defaut = DEFAULT_VIDEO_RATIO if typ == "video" else DEFAULT_PHOTO_RATIO
    ratio = str(objet.get("aspect_ratio") or ratio_defaut).strip()
    if ratio not in ASPECTS:
        raise MediaErreur("aspect_ratio invalide : " + ratio)

    qualite = str(objet.get("quality") or "finale").strip().lower()
    if qualite not in {"brouillon", "finale"}:
        raise MediaErreur("quality doit etre brouillon ou finale")

    duree = _entier(objet.get("duration_seconds"), DEFAULT_VIDEO_DURATION, 1, 180)
    if typ == "video" and duree > 30 and content_format != "tiktok_rewards":
        raise MediaErreur("une video standard ne peut pas depasser 30 secondes")
    if content_format == "tiktok_rewards" and duree < 60:
        raise MediaErreur("tiktok_rewards doit viser au moins 60 secondes")

    return MediaSpec(
        media_type=typ,
        prompt=prompt,
        caption=str(objet.get("caption") or objet.get("legende") or "").strip(),
        reference_path=str(objet.get("reference") or objet.get("reference_path") or "").strip(),
        aspect_ratio=ratio,
        duration_seconds=duree,
        quality=qualite,
        provider=str(objet.get("provider") or "").strip().lower(),
        model=str(objet.get("model") or "").strip(),
        publish=bool(objet.get("publish", False)),
    )


def prompt_photo(spec: MediaSpec) -> str:
    return ", ".join((LUNA.apparence.ancre, spec.prompt, RENDU, SIGNATURE))


def generer_photo(spec: MediaSpec, chemin_sortie: str) -> str:
    if spec.media_type not in {"photo", "video"}:
        raise MediaErreur("generer_photo attend un job photo ou video")
    images = GenerateurImages()
    if not images.disponible:
        raise MediaErreur("aucun fournisseur image configure")
    try:
        image = images.generer(
            prompt_photo(spec),
            NEGATIF,
            LUNA.apparence.graine,
            format=ASPECTS[spec.aspect_ratio],
            qualite=spec.quality,
        )
    except ErreurMoteur:
        raise
    cible = Path(chemin_sortie)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(image)
    return str(cible)


class RunwayVideo:
    """Adaptateur HTTP minimal pour Runway image vers video."""

    BASE = "https://api.dev.runwayml.com"
    VERSION = "2024-11-06"
    MODEL = "seedance2_5"

    def __init__(self) -> None:
        self.cle = (os.getenv("RUNWAYML_API_SECRET")
                    or os.getenv("RUNWAY_API_KEY") or "").strip()
        self.base = (os.getenv("LUNA_VIDEO_RUNWAY_BASE") or self.BASE).rstrip("/")
        self.version = os.getenv("LUNA_VIDEO_RUNWAY_API_VERSION", self.VERSION)
        self.model = os.getenv("LUNA_VIDEO_MODEL", self.MODEL)
        self.resolution = os.getenv("LUNA_VIDEO_RESOLUTION", "720p")

    @property
    def disponible(self) -> bool:
        return bool(self.cle)

    def _requete(self, methode: str, chemin: str, corps: dict | None = None) -> dict:
        if not self.cle:
            raise MediaErreur("RUNWAYML_API_SECRET / RUNWAY_API_KEY absent")
        data = json.dumps(corps).encode("utf-8") if corps is not None else None
        req = urllib.request.Request(
            self.base + chemin,
            data=data,
            headers={
                "Authorization": "Bearer " + self.cle,
                "X-Runway-Version": self.version,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "alluxe-luna-media/1.0",
            },
            method=methode,
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            raise MediaErreur(f"Runway HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MediaErreur(f"Runway reseau: {exc}") from exc

    @staticmethod
    def _ratio_api(ratio: str) -> str:
        """Convertit notre ratio social en dimension acceptee par Gen-4.5."""
        valeurs = {
            "9:16": "720:1280",
            "16:9": "1280:720",
            "3:4": "832:1104",
            "4:3": "1104:832",
            "1:1": "960:960",
        }
        try:
            return valeurs[ratio]
        except KeyError as exc:
            raise MediaErreur(
                f"ratio {ratio} non supporte par Runway gen4.5"
            ) from exc

    def creer(self, image_url: str, prompt: str, ratio: str,
              duree: int) -> str:
        if not self.disponible:
            raise MediaErreur("Runway n'est pas configure")
        if not 4 <= int(duree) <= 30:
            raise MediaErreur("Runway demande une duree video entre 4 et 30 secondes")
        payload = {
            "model": self.model,
            "promptImage": image_url,
            "promptText": prompt,
            "ratio": self._ratio_api(ratio),
            "duration": int(duree),
        }
        rep = self._requete("POST", "/v1/image_to_video", payload)
        if not rep.get("id"):
            raise MediaErreur("Runway n'a pas rendu d'id de tache : " + str(rep)[:500])
        return str(rep["id"])

    def etat(self, task_id: str) -> dict:
        return self._requete("GET", f"/v1/tasks/{task_id}")

    @staticmethod
    def extraire_url(rep: dict) -> str:
        for key in ("output", "outputs", "artifacts"):
            val = rep.get(key)
            if isinstance(val, str) and val.startswith("http"):
                return val
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.startswith("http"):
                        return item
                    if isinstance(item, dict):
                        for subkey in ("url", "uri", "asset_url"):
                            lien = item.get(subkey)
                            if isinstance(lien, str) and lien.startswith("http"):
                                return lien
        raise MediaErreur("Runway termine sans URL de sortie")

    def resultat(self, task_id: str) -> tuple[str, str]:
        rep = self.etat(task_id)
        statut = str(rep.get("status") or "").upper()
        if statut in {"SUCCEEDED", "SUCCESS", "COMPLETED"}:
            return "succeeded", self.extraire_url(rep)
        if statut in {"FAILED", "CANCELED", "CANCELLED"}:
            detail = rep.get("failure") or rep.get("error") or rep.get("message") or rep
            raise MediaErreur("Runway tache echouee : " + str(detail)[:500])
        return "generating", ""


def telecharger(url: str, chemin_sortie: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=180) as response:
            contenu = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise MediaErreur(f"telechargement media impossible : {exc}") from exc
    if not contenu:
        raise MediaErreur("media distant vide")
    cible = Path(chemin_sortie)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(contenu)
    return str(cible)
