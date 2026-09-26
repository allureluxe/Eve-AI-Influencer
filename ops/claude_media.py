#!/usr/bin/env python3
"""CLI pour que Claude Code ou un job systeme depose un job media Luna."""
from __future__ import annotations

import argparse
import json
import os
import urllib.request

from gold_bot.env import charger_env

charger_env()


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
    print(json.dumps({
        "id": row.get("id"),
        "statut": row.get("statut"),
        "generation_status": row.get("generation_status"),
        "media_type": row.get("media_type"),
        "publish_requested": row.get("publish_requested"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
