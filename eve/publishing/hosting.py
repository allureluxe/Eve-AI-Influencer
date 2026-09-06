"""Hébergement public des vidéos, condition d'une publication Instagram.

Instagram ne reçoit pas de fichier : il télécharge la vidéo depuis une URL
publique. Plutôt que d'imposer un serveur, on dépose le MP4 comme
**asset d'une release GitHub** — gratuit, stable, et déjà disponible dans
le workflow (`GITHUB_TOKEN` est fourni automatiquement).

Limite à connaître : l'URL d'un asset n'est publique que si le dépôt l'est.
Sur un dépôt privé, Instagram reçoit un 404 — `check_public_access()` le
détecte et le dit clairement plutôt que de laisser échouer la publication.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import requests

log = logging.getLogger(__name__)

API = "https://api.github.com"
UPLOADS = "https://uploads.github.com"
TIMEOUT = 300


class HostingError(RuntimeError):
    pass


@dataclass
class HostedFile:
    url: str
    asset_id: int
    name: str


class GitHubReleaseHost:
    """Dépose les médias dans une release dédiée et renvoie leur URL publique."""

    def __init__(self, repo: str = "", token: str = "", tag: str = "media"):
        self.repo = repo or os.getenv("GITHUB_REPOSITORY", "")
        self.token = token or os.getenv("GITHUB_TOKEN", "") or os.getenv("GH_TOKEN", "")
        self.tag = tag

    @property
    def configured(self) -> bool:
        return bool(self.repo and self.token)

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def _ensure_release(self) -> int:
        """Identifiant de la release d'hébergement, créée au besoin."""
        r = requests.get(f"{API}/repos/{self.repo}/releases/tags/{self.tag}",
                         headers=self._headers(), timeout=60)
        if r.status_code == 200:
            return r.json()["id"]
        if r.status_code != 404:
            raise HostingError(f"Lecture de la release : {r.status_code} {r.text[:200]}")

        r = requests.post(
            f"{API}/repos/{self.repo}/releases", headers=self._headers(),
            json={"tag_name": self.tag, "name": "Médias publiés",
                  "body": "Fichiers hébergés pour la publication Instagram. "
                          "Généré automatiquement, ne pas supprimer.",
                  "draft": False, "prerelease": True},
            timeout=60)
        if r.status_code >= 400:
            raise HostingError(f"Création de la release : {r.status_code} {r.text[:200]}")
        return r.json()["id"]

    def _delete_existing(self, release_id: int, name: str) -> None:
        """Un asset de même nom ferait échouer l'envoi : on remplace."""
        r = requests.get(f"{API}/repos/{self.repo}/releases/{release_id}/assets",
                         headers=self._headers(), params={"per_page": 100}, timeout=60)
        if r.status_code >= 400:
            return
        for asset in r.json():
            if asset.get("name") == name:
                requests.delete(f"{API}/repos/{self.repo}/releases/assets/{asset['id']}",
                                headers=self._headers(), timeout=60)

    def upload(self, path: Path, name: str = "") -> HostedFile:
        if not self.configured:
            raise HostingError(
                "Hébergement GitHub non configuré : GITHUB_REPOSITORY et GITHUB_TOKEN "
                "sont requis (fournis automatiquement dans un workflow Actions).")
        if not path.exists():
            raise HostingError(f"Fichier introuvable : {path}")

        name = name or path.name
        release_id = self._ensure_release()
        self._delete_existing(release_id, name)

        types = {".mp4": "video/mp4", ".jpg": "image/jpeg",
                 ".jpeg": "image/jpeg", ".png": "image/png"}
        r = requests.post(
            f"{UPLOADS}/repos/{self.repo}/releases/{release_id}/assets",
            headers={**self._headers(),
                     "Content-Type": types.get(path.suffix.lower(), "application/octet-stream")},
            params={"name": name}, data=path.read_bytes(), timeout=TIMEOUT)
        if r.status_code >= 400:
            raise HostingError(f"Envoi de l'asset : {r.status_code} {r.text[:200]}")

        data = r.json()
        log.info("Média hébergé : %s", data["browser_download_url"])
        return HostedFile(data["browser_download_url"], data["id"], name)

    def check_public_access(self) -> tuple[bool, str]:
        """Le dépôt est-il public ? Sinon Instagram ne pourra rien télécharger."""
        if not self.configured:
            return False, "GITHUB_REPOSITORY ou GITHUB_TOKEN manquant."
        r = requests.get(f"{API}/repos/{self.repo}", headers=self._headers(), timeout=60)
        if r.status_code >= 400:
            return False, f"Dépôt illisible : {r.status_code}"
        if r.json().get("private"):
            return False, (
                f"Le dépôt {self.repo} est privé : les URLs de release ne sont pas "
                "accessibles publiquement, Instagram recevra un 404. Rendre le dépôt "
                "public, ou renseigner PUBLIC_MEDIA_BASE_URL vers un autre hébergement.")
        return True, "Dépôt public : les URLs de release sont accessibles."
