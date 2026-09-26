#!/usr/bin/env python3
"""CLI pour que Claude Code ou un job systeme depose un job media Luna."""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.parse
import urllib.request

from gold_bot.env import charger_env

charger_env()



def _appel_get(url: str, key: str, ident: str) -> dict:
    chemin = (
        "luna_publications?id=eq."
        + urllib.parse.quote(ident, safe="")
        + "&select=id,statut,generation_status,media_type,aspect_ratio,"
          "duration_seconds,chemin_photo,chemin_video,provider,provider_task_id,"
          "publish_requested,published_at,published_platform,published_media_id,erreurs"
    )
    req = urllib.request.Request(
        f"{url}/rest/v1/{chemin}",
        headers={"apikey": key, "authorization": f"Bearer {key}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        lignes = json.loads(response.read().decode("utf-8") or "[]")
    if not lignes:
        raise SystemExit("job introuvable : " + ident)
    return lignes[0]


def _attendre(url: str, key: str, ident: str, timeout: int) -> dict:
    fin = time.time() + timeout
    while time.time() < fin:
        ligne = _appel_get(url, key, ident)
        if ligne.get("generation_status") in {"succeeded", "failed"}:
            return ligne
        if ligne.get("statut") in {"terminee", "echec"}:
            return ligne
        time.sleep(5)
    return {"id": ident, "timeout": True}

def main() -> int:
    parser = argparse.ArgumentParser(description="Depose un job media Luna")
    parser.add_argument("type", choices=("photo", "video"))
    parser.add_argument("prompt")
    parser.add_argument("--caption", default="")
    parser.add_argument("--ratio", default=None)
    parser.add_argument("--duration", type=int, default=None)
    parser.add_argument("--quality", choices=("brouillon", "finale"), default="finale")
    parser.add_argument("--reference", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--wait", action="store_true", help="attendre la fin")
    parser.add_argument("--timeout", type=int, default=900, help="timeout en secondes")
    args = parser.parse_args()

    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_KEY absents")

    ratio = args.ratio or ("9:16" if args.type == "video" else "3:4")
    payload = {
        "type": args.type,
        "prompt": args.prompt,
        "caption": args.caption,
        "reference": args.reference,
        "aspect_ratio": ratio,
        "duration_seconds": args.duration or (10 if args.type == "video" else 10),
        "quality": args.quality,
        "provider": args.provider,
        "model": args.model,
        "publish": bool(args.publish),
    }

    body = json.dumps({"demande": json.dumps(payload, ensure_ascii=False)}).encode()
    req = urllib.request.Request(
        f"{url}/rest/v1/luna_publications",
        data=body,
        headers={"apikey": key, "authorization": f"Bearer {key}",
                 "content-type": "application/json",
                 "prefer": "return=representation"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            rows = json.loads(response.read().decode("utf-8") or "[]")
    except Exception as exc:
        raise SystemExit(f"creation du job impossible : {exc}") from exc

    row = rows[0] if rows else {}
    if args.wait and row.get("id"):
        row = _attendre(url, key, str(row["id"]), max(1, args.timeout))
    print(json.dumps(row, ensure_ascii=False, indent=2))
    return 2 if row.get("timeout") or row.get("generation_status") == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
