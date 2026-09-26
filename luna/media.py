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


class SoraVideo:
    """Sora, l'API video d'OpenAI — LA MEME CLE QUE LES PHOTOS.

    POURQUOI ELLE REMPLACE RUNWAY

    Le 26 septembre, l'operateur a pose la bonne question : « OpenAI
    permet aussi de faire des videos ? ». Oui, et ca change trois choses
    a la fois.

    **`input_reference` resout le probleme que je disais insoluble.**
    Je lui avais ecrit, la nuit meme, que « la video ne tient pas les
    visages » et qu'il fallait ruser en filmant Luna de dos. C'est vrai
    du texte-vers-video ; ca ne l'est pas ici. Sora accepte une IMAGE DE
    DEPART : on lui donne la photo produite par `gpt-image-1`, et le
    visage tient toute la sequence. Les deux bouts de la chaine se
    tiennent enfin.

    **Le format est deja le bon.** 720x1280, c'est du 9:16 — exactement
    ce que demandent les Reels et TikTok. Aucun recadrage, donc aucune
    perte.

    **Une seule cle, une seule facture, un seul plafond.** Runway exigeait
    un second compte, un second abonnement, une seconde surveillance.

    Le prix : 4, 8 ou 12 secondes, pas plus. C'est court — et c'est la
    longueur d'un Reel qui tourne.

    L'interface est VOLONTAIREMENT celle de `RunwayVideo` (`creer`,
    `etat`, `resultat`) pour que le worker n'ait qu'un seul chemin :
    dupliquer la boucle video aurait refait l'erreur que ce depot
    raconte sept fois.
    """

    BASE = "https://api.openai.com"
    MODEL = "sora-2"
    nom = "sora"

    def __init__(self) -> None:
        cle = os.getenv("OPENAI_API_KEY", "").strip()
        # Convention de ce depot : un « your_... » non remplace vaut absent.
        self.cle = "" if cle.lower().startswith("your_") else cle
        self.base = (os.getenv("LUNA_VIDEO_SORA_BASE") or self.BASE).rstrip("/")
        self.model = os.getenv("LUNA_VIDEO_MODELE_SORA", self.MODEL)

    @property
    def disponible(self) -> bool:
        return bool(self.cle)

    def _entetes(self) -> dict:
        return {"Authorization": "Bearer " + self.cle,
                "User-Agent": "alluxe-luna-media/1.0"}

    def entetes_telechargement(self) -> dict:
        """Sora sert la video DERRIERE L'AUTHENTIFICATION, pas Runway.

        Runway rend un lien signe qu'on peut ouvrir tel quel ; Sora rend
        un identifiant, et le fichier vit sur `/v1/videos/{id}/content`
        qui exige la cle. Sans ces en-tetes, le telechargement rend un
        401 que rien dans le message ne relie a la video.
        """
        return self._entetes()

    @staticmethod
    def _taille(ratio: str) -> str:
        """Sora n'accepte QUE deux resolutions. Les autres donnent un 400."""
        if ratio in ("16:9", "4:3", "paysage"):
            return "1280x720"
        return "720x1280"

    @staticmethod
    def _duree(secondes: int) -> str:
        """4, 8 ou 12 — et rien d'autre. On arrondit au plus proche permis."""
        permises = (4, 8, 12)
        return str(min(permises, key=lambda p: abs(p - int(secondes or 8))))

    def creer(self, image_url: str, prompt: str, ratio: str,
              duree: int) -> str:
        if not self.disponible:
            raise MediaErreur("OPENAI_API_KEY absente")
        taille = self._taille(ratio)
        secondes = self._duree(duree)

        # LE MEME PLAFOND QUE LES IMAGES ET QUE RUNWAY. La video se
        # facture a la seconde et c'est, de loin, le poste le plus cher.
        from luna.budget import BudgetEpuise, Depenses
        cout_seconde = float(os.getenv("LUNA_COUT_VIDEO_SECONDE_EUR", "0.10"))
        try:
            Depenses().reserver(cout_seconde * int(secondes),
                                f"video sora {secondes} s")
        except BudgetEpuise as exc:
            raise MediaErreur(str(exc)) from exc

        champs = {"model": self.model, "prompt": prompt,
                  "seconds": secondes, "size": taille}
        fichiers = {}
        if image_url:
            # L'IMAGE DE DEPART EST TOUT L'INTERET. On la telecharge
            # depuis son lien temporaire pour la reposter en formulaire :
            # l'API veut le fichier, pas une adresse.
            try:
                with urllib.request.urlopen(image_url, timeout=120) as r:
                    octets = r.read()
                fichiers["input_reference"] = ("depart.png", octets, "image/png")
            except (urllib.error.URLError, urllib.error.HTTPError,
                    TimeoutError, OSError) as exc:
                raise MediaErreur(
                    f"image de depart illisible ({exc}) — sans elle le "
                    "visage de Luna derivera, on refuse plutot que de "
                    "produire une inconnue") from exc

        rep = self._multipart("/v1/videos", champs, fichiers)
        if not rep.get("id"):
            raise MediaErreur("Sora n'a pas rendu d'id : " + str(rep)[:400])
        return str(rep["id"])

    def _multipart(self, chemin: str, champs: dict, fichiers: dict) -> dict:
        import uuid
        limite = uuid.uuid4().hex
        corps = b""
        for nom, valeur in champs.items():
            corps += (f"--{limite}\r\n"
                      f'Content-Disposition: form-data; name="{nom}"\r\n\r\n'
                      f"{valeur}\r\n").encode("utf-8")
        for nom, (nom_fichier, octets, mime) in fichiers.items():
            corps += (f"--{limite}\r\n"
                      f'Content-Disposition: form-data; name="{nom}"; '
                      f'filename="{nom_fichier}"\r\n'
                      f"Content-Type: {mime}\r\n\r\n").encode("utf-8")
            corps += octets + b"\r\n"
        corps += f"--{limite}--\r\n".encode("utf-8")
        entetes = self._entetes()
        entetes["Content-Type"] = f"multipart/form-data; boundary={limite}"
        req = urllib.request.Request(self.base + chemin, data=corps,
                                     headers=entetes, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            raise MediaErreur(f"Sora HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MediaErreur(f"Sora reseau: {exc}") from exc

    def etat(self, task_id: str) -> dict:
        req = urllib.request.Request(
            f"{self.base}/v1/videos/{task_id}", headers=self._entetes())
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:600]
            raise MediaErreur(f"Sora HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise MediaErreur(f"Sora reseau: {exc}") from exc

    def resultat(self, task_id: str) -> tuple[str, str]:
        rep = self.etat(task_id)
        statut = str(rep.get("status") or "").lower()
        if statut in {"completed", "succeeded", "success"}:
            # Pas d'URL signee : le contenu vit derriere l'authentification.
            return "succeeded", f"{self.base}/v1/videos/{task_id}/content"
        if statut in {"failed", "cancelled", "canceled", "error"}:
            detail = rep.get("error") or rep.get("failure") or rep
            raise MediaErreur("Sora tache echouee : " + str(detail)[:500])
        return "generating", ""


def fournisseur_video():
    """Le generateur de video a utiliser, selon ce qui est configure.

    SORA D'ABORD, parce qu'il part de notre photo et tient le visage —
    le seul critere qui compte. Runway reste en repli : il marche, il
    est juste redondant des qu'une cle OpenAI existe.

    UN SEUL POINT DE SUBSTITUTION. Le worker appelle cette fonction et
    ne connait que `creer` / `resultat` ; il n'a pas a savoir lequel
    repond. Brancher Sora en dupliquant la boucle video aurait refait
    l'erreur que ce depot raconte sept fois : deux chemins pour la meme
    chose, dont un seul est corrige le jour venu.
    """
    sora = SoraVideo()
    if sora.disponible:
        return sora
    return RunwayVideo()


class RunwayVideo:
    """Adaptateur HTTP minimal pour Runway image vers video."""

    nom = "runway"

    def entetes_telechargement(self) -> dict:
        """Runway rend un lien SIGNE : rien a ajouter pour le lire."""
        return {}

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

        # LA VIDEO PASSE PAR LE MEME PLAFOND QUE LES IMAGES.
        #
        # Un plafond qui ne couvre qu'une partie des depenses n'en est
        # pas un — et c'est la video qui coute le plus cher, de loin :
        # elle se facture a la SECONDE. Dix secondes valent plusieurs
        # images, et le planificateur peut en demander plusieurs par jour
        # sans que personne ne regarde.
        #
        # Le cout est reserve AVANT la creation de la tache : une fois
        # l'identifiant rendu, Runway a commence et facturera, que notre
        # processus survive ou non.
        from luna.budget import BudgetEpuise, Depenses
        cout_seconde = float(os.getenv("LUNA_COUT_VIDEO_SECONDE_EUR", "0.05"))
        try:
            Depenses().reserver(cout_seconde * int(duree),
                                f"video runway {int(duree)} s")
        except BudgetEpuise as e:
            raise MediaErreur(str(e)) from e

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


def telecharger(url: str, chemin_sortie: str,
                entetes: dict | None = None) -> str:
    """`entetes` sert a Sora, dont le contenu vit derriere la cle.

    Runway rend un lien signe qu'on ouvre tel quel ; Sora rend un
    identifiant, et le fichier est sur `/v1/videos/{id}/content`, qui
    exige l'autorisation. Sans ce parametre, la video d'OpenAI
    echouerait en 401 avec un message qui ne parle pas d'elle.
    """
    requete = urllib.request.Request(url, headers=entetes or {})
    try:
        with urllib.request.urlopen(requete, timeout=180) as response:
            contenu = response.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise MediaErreur(f"telechargement media impossible : {exc}") from exc
    if not contenu:
        raise MediaErreur("media distant vide")
    cible = Path(chemin_sortie)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(contenu)
    return str(cible)
