"""Génération d'images photoréalistes, avec repli en cascade.

Providers, du plus gratuit au plus cher :
  pollinations : gratuit, sans clé, modèle Flux — le défaut du projet.
  gemini       : Google AI Studio, palier gratuit, Imagen ou Gemini Image.
  comfyui      : local (GPU), gratuit, contrôle total + LoRA de visage.
  stability    : payant, qualité stable.
  replicate    : payant, accès aux modèles récents.
  placeholder  : hors-ligne, image générée localement (tests, CI).

La cohérence du visage repose sur trois leviers cumulés :
  1. `identity_lock` du character bible en tête de chaque prompt ;
  2. un seed fixe (`appearance.seed`) réutilisé à chaque image ;
  3. optionnellement une LoRA / image de référence via ComfyUI.
"""
from __future__ import annotations

import hashlib
import logging
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import requests

from eve.config import settings
from eve.persona.persona import NEGATIVE_PROMPT

log = logging.getLogger(__name__)


@dataclass
class ImageResult:
    path: Path
    provider: str
    prompt: str
    seed: int
    placeholder: bool = False


class ImageProvider:
    name = "base"

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        raise NotImplementedError


class PollinationsProvider(ImageProvider):
    """Gratuit, sans compte. Idéal pour démarrer à coût zéro."""

    name = "pollinations"
    BASE = "https://image.pollinations.ai/prompt/"

    def __init__(self, model: str = "flux"):
        self.model = model or "flux"

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        url = self.BASE + urllib.parse.quote(prompt[:1800], safe="")
        params = {"width": width, "height": height, "seed": seed,
                  "model": self.model, "nologo": "true", "enhance": "false"}
        r = requests.get(url, params=params, timeout=180)
        r.raise_for_status()
        if not r.content or len(r.content) < 1024:
            raise RuntimeError("Réponse image vide de Pollinations.")
        out.write_bytes(r.content)
        return out


class ComfyUIProvider(ImageProvider):
    """ComfyUI local : gratuit après l'installation, meilleure cohérence.

    Attend un workflow au format API dans `assets/workflows/portrait.json`
    avec les jetons %PROMPT%, %NEGATIVE%, %SEED%, %WIDTH%, %HEIGHT%.
    """

    name = "comfyui"

    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self.workflow_path = settings.paths.assets / "workflows" / "portrait.json"

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        import json

        if not self.workflow_path.exists():
            raise RuntimeError(f"Workflow ComfyUI introuvable : {self.workflow_path}")
        raw = self.workflow_path.read_text(encoding="utf-8")
        raw = (raw.replace("%PROMPT%", json.dumps(prompt)[1:-1])
                  .replace("%NEGATIVE%", json.dumps(NEGATIVE_PROMPT)[1:-1])
                  .replace("%SEED%", str(seed))
                  .replace("%WIDTH%", str(width))
                  .replace("%HEIGHT%", str(height)))
        workflow = json.loads(raw)

        r = requests.post(f"{self.url}/prompt", json={"prompt": workflow}, timeout=30)
        r.raise_for_status()
        prompt_id = r.json()["prompt_id"]

        for _ in range(120):  # jusqu'à 4 minutes
            time.sleep(2)
            hist = requests.get(f"{self.url}/history/{prompt_id}", timeout=30).json()
            if prompt_id not in hist:
                continue
            outputs = hist[prompt_id].get("outputs", {})
            for node in outputs.values():
                for img in node.get("images", []):
                    data = requests.get(
                        f"{self.url}/view",
                        params={"filename": img["filename"], "subfolder": img.get("subfolder", ""),
                                "type": img.get("type", "output")},
                        timeout=60,
                    ).content
                    out.write_bytes(data)
                    return out
        raise RuntimeError("ComfyUI : timeout sans image produite.")


class StabilityProvider(ImageProvider):
    name = "stability"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        ratio = "9:16" if height > width else ("1:1" if height == width else "16:9")
        r = requests.post(
            "https://api.stability.ai/v2beta/stable-image/generate/core",
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "image/*"},
            files={"none": ""},
            data={"prompt": prompt[:9000], "negative_prompt": NEGATIVE_PROMPT[:9000],
                  "aspect_ratio": ratio, "seed": seed, "output_format": "png"},
            timeout=180,
        )
        r.raise_for_status()
        out.write_bytes(r.content)
        return out


class ReplicateProvider(ImageProvider):
    name = "replicate"

    def __init__(self, token: str, model: str = "black-forest-labs/flux-schnell"):
        self.token = token
        self.model = model

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        headers = {"Authorization": f"Bearer {self.token}", "Prefer": "wait"}
        r = requests.post(
            f"https://api.replicate.com/v1/models/{self.model}/predictions",
            headers=headers,
            json={"input": {"prompt": prompt[:2000], "seed": seed,
                            "aspect_ratio": "9:16" if height > width else "1:1",
                            "output_format": "png"}},
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()
        for _ in range(60):
            if data.get("status") in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(2)
            data = requests.get(data["urls"]["get"], headers=headers, timeout=30).json()
        if data.get("status") != "succeeded":
            raise RuntimeError(f"Replicate : statut {data.get('status')}")
        url = data["output"][0] if isinstance(data["output"], list) else data["output"]
        out.write_bytes(requests.get(url, timeout=120).content)
        return out


class GeminiProvider(ImageProvider):
    """Google AI Studio : Imagen si disponible, sinon Gemini Image.

    Imagen accepte un ratio d'image explicite, ce qui compte pour du 9:16 ;
    les modèles Gemini Image passent par `generateContent` et suivent le
    ratio décrit dans le prompt.
    """

    name = "gemini"

    def __init__(self, model: str = ""):
        self.model = model

    def _ratio(self, width: int, height: int) -> str:
        if height > width:
            return "9:16"
        if width > height:
            return "16:9"
        return "1:1"

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        from eve.media import gemini

        model = self.model or gemini.pick_model("image")
        ratio = self._ratio(width, height)

        if model.startswith("imagen"):
            data = gemini.post(model, "predict", {
                "instances": [{"prompt": prompt[:4000]}],
                "parameters": {"sampleCount": 1, "aspectRatio": ratio,
                               "personGeneration": "allow_adult"},
            })
            predictions = data.get("predictions") or []
            if not predictions or not predictions[0].get("bytesBase64Encoded"):
                raise RuntimeError(f"Imagen n'a rien renvoyé : {str(data)[:300]}")
            import base64
            out.write_bytes(base64.b64decode(predictions[0]["bytesBase64Encoded"]))
            return out

        # Modèles « gemini-*-image » : le ratio se demande dans le prompt.
        data = gemini.post(model, "generateContent", {
            "contents": [{"role": "user", "parts": [
                {"text": f"{prompt[:4000]}\n\nVertical {ratio} aspect ratio photograph."}]}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": ratio}},
        })
        blob, _ = gemini.first_inline_data(data)
        out.write_bytes(blob)
        return out


class PlaceholderProvider(ImageProvider):
    """Aucun réseau : image locale lisible, pour les tests et la CI."""

    name = "placeholder"

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        try:
            from PIL import Image, ImageDraw
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Pillow requis pour le provider placeholder.") from exc

        rnd = int(hashlib.sha256(f"{prompt}{seed}".encode()).hexdigest()[:6], 16)
        base = ((rnd >> 16) % 60 + 30, (rnd >> 8) % 60 + 40, rnd % 60 + 60)
        img = Image.new("RGB", (width, height), base)
        draw = ImageDraw.Draw(img)
        for y in range(0, height, 4):  # dégradé simple
            k = y / height
            draw.line([(0, y), (width, y)],
                      fill=(int(base[0] * (1 - k) + 220 * k),
                            int(base[1] * (1 - k) + 200 * k),
                            int(base[2] * (1 - k) + 190 * k)))
        words, line, lines = prompt.split(), "", []
        for w in words[:44]:
            if len(line) + len(w) > 34:
                lines.append(line)
                line = w
            else:
                line = f"{line} {w}".strip()
        lines.append(line)
        y = height // 2 - len(lines) * 12
        for ln in lines:
            draw.text((40, y), ln, fill=(255, 255, 255))
            y += 24
        draw.text((40, 40), f"[PLACEHOLDER seed={seed}]", fill=(255, 230, 120))
        img.save(out)
        return out


def get_provider(name: str | None = None) -> ImageProvider:
    g = settings.generation
    name = (name or g.image_provider or "pollinations").lower()
    if name == "comfyui":
        return ComfyUIProvider(g.comfyui_url)
    if name == "stability" and g.stability_api_key:
        return StabilityProvider(g.stability_api_key)
    if name == "replicate" and g.replicate_api_token:
        return ReplicateProvider(g.replicate_api_token)
    if name == "gemini":
        return GeminiProvider(g.image_model if g.image_model != "flux" else "")
    if name == "placeholder":
        return PlaceholderProvider()
    return PollinationsProvider(g.image_model)


def generate_image(
    prompt: str,
    out_path: Path,
    *,
    seed: int,
    width: int | None = None,
    height: int | None = None,
    provider: str | None = None,
    allow_placeholder: bool = True,
) -> ImageResult:
    """Génère une image, avec repli sur le placeholder si le provider échoue."""
    g = settings.generation
    width = width or g.reel_width
    height = height or g.reel_height
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and out_path.stat().st_size > 1024:
        return ImageResult(out_path, "cache", prompt, seed)

    p = get_provider(provider)
    try:
        p.generate(prompt, out_path, width=width, height=height, seed=seed)
        return ImageResult(out_path, p.name, prompt, seed, placeholder=p.name == "placeholder")
    except Exception as exc:
        log.warning("Provider image %s en échec (%s).", p.name, exc)
        if not allow_placeholder:
            raise
        PlaceholderProvider().generate(prompt, out_path, width=width, height=height, seed=seed)
        return ImageResult(out_path, "placeholder", prompt, seed, placeholder=True)


def shot_seed(persona_seed: int, index: int, vary_pose: bool = True) -> int:
    """Seed d'un plan.

    Le visage reste stable si le seed ne bouge pas ; on le fait varier
    légèrement pour éviter des images identiques d'un plan à l'autre, tout
    en gardant `identity_lock` pour tenir la ressemblance.
    """
    return persona_seed + (index * 17 if vary_pose else 0)
