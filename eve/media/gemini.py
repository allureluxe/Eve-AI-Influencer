"""Accès commun à Google AI Studio (images et voix).

Les noms de modèles Google changent souvent. Plutôt que de les figer, on
interroge `/v1beta/models` et on choisit le meilleur candidat disponible
pour la tâche demandée. Le résultat est mis en cache pour la session.
"""
from __future__ import annotations

import logging
from functools import lru_cache

import requests

from eve.config import settings

log = logging.getLogger(__name__)

BASE = "https://generativelanguage.googleapis.com/v1beta"
TIMEOUT = 180

# Préférences par ordre décroissant. Le premier motif trouvé gagne.
PREFERENCES = {
    # Imagen d'abord s'il est accessible (ratio d'image explicite), sinon les
    # modèles Gemini Image du plus capable au plus léger.
    "image": ("imagen-4", "imagen-3", "-pro-image", "3.1-flash-image",
              "flash-image", "image"),
    "tts": ("3.1-flash-tts", "flash-preview-tts", "pro-preview-tts", "-tts"),
}


class GeminiError(RuntimeError):
    pass


def api_key() -> str:
    key = settings.generation.gemini_api_key
    if not key:
        raise GeminiError("GEMINI_API_KEY absente : aucune clé Google AI Studio configurée.")
    return key


def _headers() -> dict:
    return {"x-goog-api-key": api_key(), "Content-Type": "application/json"}


@lru_cache(maxsize=1)
def list_models() -> tuple[dict, ...]:
    r = requests.get(f"{BASE}/models", headers=_headers(), params={"pageSize": 200}, timeout=60)
    if r.status_code >= 400:
        raise GeminiError(f"Liste des modèles refusée ({r.status_code}) : {r.text[:200]}")
    return tuple(r.json().get("models", []))


def pick_model(task: str) -> str:
    """Nom du modèle à utiliser pour « image » ou « tts »."""
    noms = [m.get("name", "").removeprefix("models/") for m in list_models()]
    for motif in PREFERENCES[task]:
        candidats = sorted(n for n in noms if motif in n)
        if candidats:
            # Le plus court d'abord : « imagen-4.0-generate-001 » plutôt
            # qu'une variante expérimentale à rallonge.
            choisi = min(candidats, key=len)
            log.info("Modèle Gemini retenu pour %s : %s", task, choisi)
            return choisi
    raise GeminiError(
        f"Aucun modèle {task} disponible sur cette clé. "
        f"Modèles vus : {', '.join(noms[:12])}…")


def post(model: str, method: str, payload: dict) -> dict:
    r = requests.post(f"{BASE}/models/{model}:{method}", headers=_headers(),
                      json=payload, timeout=TIMEOUT)
    if r.status_code >= 400:
        raise GeminiError(f"{model}:{method} → {r.status_code} : {r.text[:400]}")
    return r.json()


def first_inline_data(response: dict) -> tuple[bytes, str]:
    """Extrait la première pièce binaire d'une réponse generateContent."""
    import base64

    for candidat in response.get("candidates", []):
        for part in candidat.get("content", {}).get("parts", []):
            blob = part.get("inlineData") or part.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"]), blob.get("mimeType", "")
    raise GeminiError(f"Aucune donnée binaire dans la réponse : {str(response)[:300]}")
