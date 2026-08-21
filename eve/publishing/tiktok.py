"""Publication TikTok via la Content Posting API officielle.

Flux `FILE_UPLOAD` (recommandé : pas besoin d'héberger le fichier) :
  1. `/v2/post/publish/creator_info/query/` → options de confidentialité
     autorisées pour ce compte ;
  2. `/v2/post/publish/video/init/` → `publish_id` + `upload_url` ;
  3. PUT du fichier sur `upload_url` (par morceaux) ;
  4. `/v2/post/publish/status/fetch/` → suivi jusqu'à PUBLISH_COMPLETE.

Deux points qui bloquent tout le monde au démarrage :
  · tant que l'application n'a pas passé l'audit TikTok, les publications
    sont limitées à `SELF_ONLY` (visible par la créatrice uniquement) ;
  · le champ `is_aigc` déclare le contenu généré par IA — obligatoire ici.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from eve.config import settings
from eve.publishing.base import Publisher, PublishRequest, PublishResult

log = logging.getLogger(__name__)

API = "https://open.tiktokapis.com/v2"
CHUNK = 10 * 1024 * 1024  # 10 Mo : dans les bornes imposées par TikTok


class TikTokPublisher(Publisher):
    platform = "tiktok"

    def __init__(self, access_token: str = ""):
        self.token = access_token or settings.publishing.tiktok_access_token

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json; charset=UTF-8"}

    def creator_info(self) -> dict:
        r = requests.post(f"{API}/post/publish/creator_info/query/",
                          headers=self._headers, timeout=60)
        r.raise_for_status()
        return r.json().get("data", {})

    def _init_upload(self, path: Path, req: PublishRequest, privacy: str) -> tuple[str, str]:
        size = path.stat().st_size
        chunk = min(CHUNK, size)
        total = max(1, size // chunk)
        body = {
            "post_info": {
                "title": req.caption[:2200],
                "privacy_level": privacy,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
                "video_cover_timestamp_ms": 1000,
                # Déclaration AIGC — obligatoire pour un personnage virtuel.
                "is_aigc": bool(req.is_ai_generated),
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": size,
                "chunk_size": chunk,
                "total_chunk_count": total,
            },
        }
        r = requests.post(f"{API}/post/publish/video/init/", headers=self._headers,
                          json=body, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"init upload {r.status_code} : {r.text[:400]}")
        data = r.json().get("data", {})
        if not data.get("upload_url"):
            raise RuntimeError(f"Réponse init inattendue : {r.text[:400]}")
        return data["publish_id"], data["upload_url"]

    def _upload(self, path: Path, upload_url: str) -> None:
        size = path.stat().st_size
        chunk = min(CHUNK, size)
        with open(path, "rb") as fh:
            start = 0
            while start < size:
                data = fh.read(chunk)
                end = start + len(data) - 1
                r = requests.put(
                    upload_url,
                    headers={"Content-Range": f"bytes {start}-{end}/{size}",
                             "Content-Type": "video/mp4",
                             "Content-Length": str(len(data))},
                    data=data, timeout=600,
                )
                if r.status_code not in (200, 201, 206):
                    raise RuntimeError(f"upload chunk {r.status_code} : {r.text[:300]}")
                start = end + 1

    def _wait_publish(self, publish_id: str, timeout_s: int = 900) -> dict:
        deadline = time.time() + timeout_s
        last: dict = {}
        while time.time() < deadline:
            r = requests.post(f"{API}/post/publish/status/fetch/", headers=self._headers,
                              json={"publish_id": publish_id}, timeout=60)
            r.raise_for_status()
            last = r.json().get("data", {})
            status = last.get("status")
            if status in {"PUBLISH_COMPLETE", "SEND_TO_USER_INBOX"}:
                return last
            if status == "FAILED":
                raise RuntimeError(f"TikTok a rejeté la vidéo : {last.get('fail_reason')}")
            time.sleep(6)
        raise TimeoutError(f"Statut TikTok non terminal : {last.get('status')}")

    def publish(self, req: PublishRequest) -> PublishResult:
        if settings.dry_run:
            return PublishResult(self.platform, True, dry_run=True,
                                 detail=f"dry-run · {req.video_path.name if req.video_path else 'sans fichier'} "
                                        f"· aigc={req.is_ai_generated}")
        if not self.configured:
            return PublishResult(self.platform, False, detail="TIKTOK_ACCESS_TOKEN manquant.")
        if not req.video_path or not req.video_path.exists():
            return PublishResult(self.platform, False, detail="Fichier vidéo introuvable.")

        try:
            privacy = req.privacy
            try:
                info = self.creator_info()
                options = info.get("privacy_level_options") or []
                if options and privacy not in options:
                    # App non auditée : TikTok n'autorise que SELF_ONLY.
                    privacy = "SELF_ONLY" if "SELF_ONLY" in options else options[0]
                    log.warning("Confidentialité ramenée à %s (limite du compte/app).", privacy)
            except Exception as exc:
                log.warning("creator_info indisponible (%s) — on continue avec %s.", exc, privacy)

            publish_id, upload_url = self._init_upload(req.video_path, req, privacy)
            self._upload(req.video_path, upload_url)
            status = self._wait_publish(publish_id)
            return PublishResult(self.platform, True, post_id=publish_id,
                                 detail=f"status={status.get('status')} privacy={privacy}")
        except Exception as exc:
            log.error("Publication TikTok échouée : %s", exc)
            return PublishResult(self.platform, False, detail=str(exc)[:300])

    def fetch_metrics(self, post_id: str) -> dict:
        """Statistiques via /v2/video/query/ (scope video.list requis)."""
        if settings.dry_run or not self.configured:
            return {}
        try:
            r = requests.post(
                f"{API}/video/query/",
                headers=self._headers,
                params={"fields": "id,like_count,comment_count,share_count,view_count"},
                json={"filters": {"video_ids": [post_id]}},
                timeout=60,
            )
            r.raise_for_status()
            videos = r.json().get("data", {}).get("videos", [])
            return videos[0] if videos else {}
        except Exception as exc:
            log.warning("Métriques TikTok indisponibles : %s", exc)
            return {}
