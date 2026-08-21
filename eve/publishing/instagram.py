"""Publication Instagram via l'API Graph officielle.

Pourquoi l'API officielle et pas `instagrapi` / une automatisation du site :
l'automatisation non officielle viole les CGU, fait bannir le compte et rend
la monétisation impossible. L'API Graph exige un compte *Professionnel*
(Business ou Creator) relié à une Page Facebook, plus une app Meta.

Le flux Reels est en trois temps :
  1. création d'un conteneur média (`/media`) ;
  2. attente du statut FINISHED ;
  3. publication (`/media_publish`).

Instagram télécharge la vidéo depuis une URL publique : il faut donc héberger
le fichier (voir `PUBLIC_MEDIA_BASE_URL` et docs/SETUP.md).
"""
from __future__ import annotations

import logging
import time

import requests

from eve.config import settings
from eve.publishing.base import Publisher, PublishRequest, PublishResult

log = logging.getLogger(__name__)


class InstagramPublisher(Publisher):
    platform = "instagram"

    def __init__(self, user_id: str = "", token: str = "", api_version: str = ""):
        cfg = settings.publishing
        self.user_id = user_id or cfg.instagram_user_id
        self.token = token or cfg.instagram_token
        self.base = f"https://graph.facebook.com/{api_version or cfg.graph_api_version}"

    @property
    def configured(self) -> bool:
        return bool(self.user_id and self.token)

    # ------------------------------------------------------------------ API
    def _post(self, path: str, data: dict) -> dict:
        r = requests.post(f"{self.base}/{path}", data={**data, "access_token": self.token}, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"Graph API {r.status_code} : {r.text[:400]}")
        return r.json()

    def _get(self, path: str, params: dict) -> dict:
        r = requests.get(f"{self.base}/{path}", params={**params, "access_token": self.token}, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"Graph API {r.status_code} : {r.text[:400]}")
        return r.json()

    def _wait_container(self, container_id: str, timeout_s: int = 600) -> None:
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            status = self._get(container_id, {"fields": "status_code,status"})
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code == "ERROR":
                raise RuntimeError(f"Conteneur en erreur : {status.get('status')}")
            time.sleep(5)
        raise TimeoutError("Le conteneur Instagram n'est jamais passé à FINISHED.")

    # -------------------------------------------------------------- publish
    def publish(self, req: PublishRequest) -> PublishResult:
        if settings.dry_run:
            return PublishResult(self.platform, True, dry_run=True,
                                 detail=f"dry-run · {len(req.caption)} car. · "
                                        f"{'reel' if (req.video_url or req.video_path) else 'photo'}")
        if not self.configured:
            return PublishResult(self.platform, False,
                                 detail="IG_USER_ID / IG_ACCESS_TOKEN manquants.")

        try:
            if req.video_url:
                payload = {"media_type": "REELS", "video_url": req.video_url,
                           "caption": req.caption, "share_to_feed": "true"}
                if req.cover_url:
                    payload["cover_url"] = req.cover_url
            elif req.image_url:
                payload = {"image_url": req.image_url, "caption": req.caption}
            else:
                return PublishResult(self.platform, False,
                                     detail="Instagram exige une URL publique (video_url/image_url). "
                                            "Renseigne PUBLIC_MEDIA_BASE_URL.")

            container = self._post(f"{self.user_id}/media", payload)
            container_id = container["id"]
            self._wait_container(container_id)
            published = self._post(f"{self.user_id}/media_publish", {"creation_id": container_id})
            post_id = published["id"]
            permalink = self._get(post_id, {"fields": "permalink"}).get("permalink", "")
            return PublishResult(self.platform, True, post_id=post_id, url=permalink)
        except Exception as exc:
            log.error("Publication Instagram échouée : %s", exc)
            return PublishResult(self.platform, False, detail=str(exc)[:300])

    # ------------------------------------------------------------- insights
    def fetch_metrics(self, post_id: str) -> dict:
        if settings.dry_run or not self.configured:
            return {}
        try:
            metrics = "likes,comments,saved,shares,reach,views,total_interactions"
            data = self._get(f"{post_id}/insights", {"metric": metrics})
            return {item["name"]: item["values"][0]["value"] for item in data.get("data", [])}
        except Exception as exc:
            log.warning("Insights Instagram indisponibles : %s", exc)
            return {}

    def account_metrics(self) -> dict:
        if settings.dry_run or not self.configured:
            return {}
        try:
            data = self._get(f"{self.user_id}", {"fields": "followers_count,media_count"})
            return {k: v for k, v in data.items() if k != "id"}
        except Exception as exc:
            log.warning("Métriques de compte indisponibles : %s", exc)
            return {}
