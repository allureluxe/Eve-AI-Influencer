"""Publication TikTok officielle via Content Posting API.

La publication directe est active uniquement si TIKTOK_AUTO_PUBLISH=true.
Le contenu est toujours declare AIGC. L'API TikTok exige video.publish pour
Direct Post et impose un audit du client avant de lever la restriction privee
des clients non audites.
"""
from __future__ import annotations

import json
import mimetypes
import os
import urllib.error
import urllib.request


BASE = "https://open.tiktokapis.com/v2"


class TikTokErreur(RuntimeError):
    pass


def _token() -> str:
    token = os.getenv("TIKTOK_ACCESS_TOKEN", "").strip()
    if not token:
        raise TikTokErreur("TIKTOK_ACCESS_TOKEN absent")
    return token


def _appel(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path,
        data=data,
        headers={
            "Authorization": "Bearer " + _token(),
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "alluxe-luna-tiktok/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:800]
        raise TikTokErreur(f"TikTok HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TikTokErreur(f"TikTok reseau: {exc}") from exc


def createur() -> dict:
    """Recupere les permissions et limites actuelles du createur."""
    return _appel("/post/publish/creator_info/query/")


def _chunk_size(size: int) -> int:
    # TikTok accepte 5-64 MB par chunk, sauf final <=128 MB.
    if size <= 64 * 1024 * 1024:
        return size
    return 64 * 1024 * 1024


def publier_video(chemin: str, caption: str = "",
                  privacy: str = "PUBLIC_TO_EVERYONE") -> str:
    if os.getenv("TIKTOK_AUTO_PUBLISH", "false").lower() != "true":
        raise TikTokErreur("TIKTOK_AUTO_PUBLISH n'est pas active")

    fichier = os.path.abspath(chemin)
    taille = os.path.getsize(fichier)
    if taille <= 0:
        raise TikTokErreur("video vide")

    info = createur()
    data = info.get("data") or {}
    options = data.get("privacy_level_options") or []
    if options and privacy not in options:
        privacy = options[0]

    chunk = _chunk_size(taille)
    total = (taille + chunk - 1) // chunk
    init = _appel("/post/publish/video/init/", {
        "post_info": {
            "title": caption[:2200],
            "privacy_level": privacy,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "brand_content_toggle": False,
            "is_aigc": True,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": taille,
            "chunk_size": chunk,
            "total_chunk_count": total,
        },
    })
    bloc = init.get("data") or {}
    publish_id = bloc.get("publish_id")
    upload_url = bloc.get("upload_url")
    if not publish_id or not upload_url:
        raise TikTokErreur("TikTok n'a pas fourni publish_id/upload_url")

    mime = mimetypes.guess_type(fichier)[0] or "video/mp4"
    with open(fichier, "rb") as fh:
        start = 0
        while start < taille:
            data_chunk = fh.read(min(chunk, taille - start))
            end = start + len(data_chunk) - 1
            req = urllib.request.Request(
                upload_url,
                data=data_chunk,
                headers={
                    "Content-Type": mime,
                    "Content-Length": str(len(data_chunk)),
                    "Content-Range": f"bytes {start}-{end}/{taille}",
                },
                method="PUT",
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as response:
                    if response.status not in (200, 201, 206):
                        raise TikTokErreur(
                            f"upload TikTok inattendu: HTTP {response.status}"
                        )
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:600]
                raise TikTokErreur(
                    f"upload TikTok HTTP {exc.code}: {detail}"
                ) from exc
            start = end + 1

    return str(publish_id)


def statut(publish_id: str) -> dict:
    if not publish_id:
        raise TikTokErreur("publish_id absent")
    return _appel("/post/publish/status/fetch/", {"publish_id": publish_id})


def publier_video_et_verifier(chemin: str, caption: str = "",
                              privacy: str = "PUBLIC_TO_EVERYONE") -> str:
    publish_id = publier_video(chemin, caption, privacy)
    return publish_id
