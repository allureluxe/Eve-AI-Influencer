"""Compatibilite HTTP pour les notifications.

MoonX n'est plus un broker actif du projet, mais le module de notifications
utilise encore ``http_json``. Ce shim conserve cette API sans reintroduire
l'ancien broker MoonX.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Any, Optional


def http_json(
    url: str,
    method: str = "POST",
    payload: Optional[dict] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = 10.0,
) -> Any:
    body = json.dumps(payload or {}).encode("utf-8")
    hdrs = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "gold-bot/1.0",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw) if raw.strip() else {}
