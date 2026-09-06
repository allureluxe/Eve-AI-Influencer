"""Génération d'images photoréalistes, avec repli en cascade.

Providers, du plus gratuit au plus cher :
  pollinations : gratuit, sans clé, mais un seul modèle (« sana »), qui
                 rend du semi-illustré : inutilisable pour un visage.
  replicate    : payant (~0,04 $/image), accès à FLUX 1.1 Pro — le seul
                 qui tienne le photoréalisme sur un visage.
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

# Certains services n'acceptent aucun prompt négatif (Pollinations, par
# exemple). Les consignes de réalisme doivent alors être formulées
# positivement, sinon toute la protection anti-plastique reste lettre morte
# — c'est ce qui donne les visages de poupée lissés.
# Complète `PHOTO_STYLE` sans le répéter : ce sont les seuls termes qui
# ne peuvent pas être formulés positivement ailleurs.
REALISME_POSITIF = "real photo, not a render, no beauty filter, no smoothing"

# Le service d'images renvoie une erreur serveur sur les prompts trop
# longs : celui-ci a fait tomber la génération en 500.
LONGUEUR_MAX = 900


def prompt_realiste(prompt: str, limite: int = LONGUEUR_MAX) -> str:
    """Prompt enrichi pour les providers sans paramètre négatif, borné.

    Le suffixe de réalisme est prioritaire : on rogne la description avant
    de le sacrifier, sinon on retombe sur des visages lissés.
    """
    suffixe = f", {REALISME_POSITIF}"
    place = max(0, limite - len(suffixe))
    return prompt[:place].rstrip(", ") + suffixe

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
        # Pollinations n'expose aucun prompt négatif : les consignes de
        # réalisme sont formulées positivement, sinon elles sont perdues.
        url = self.BASE + urllib.parse.quote(prompt_realiste(prompt), safe="")
        params = {"width": width, "height": height, "seed": seed,
                  "model": self.model, "nologo": "true", "enhance": "false"}

        # Le service renvoie régulièrement des 5xx passagers. Un seul essai
        # faisait basculer toute l'image sur un placeholder.
        derniere: Exception | None = None
        for essai in range(3):
            try:
                r = requests.get(url, params=params, timeout=180)
                if r.status_code >= 500:
                    raise RuntimeError(f"Pollinations {r.status_code} (essai {essai + 1}/3)")
                r.raise_for_status()
                if not r.content or len(r.content) < 1024:
                    raise RuntimeError("Réponse image vide de Pollinations.")
                out.write_bytes(r.content)
                return out
            except Exception as exc:
                derniere = exc
                log.warning("%s", exc)
                if essai < 2:
                    time.sleep(4 * (essai + 1))
        raise RuntimeError(f"Pollinations indisponible après 3 essais : {derniere}")


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
    """Replicate — accès aux modèles FLUX, dont le photoréalisme est le seul
    à tenir sur des visages.

    FLUX n'accepte **pas** de prompt négatif : c'est un modèle distillé sur
    la guidance. Toutes les consignes de réalisme doivent donc être
    formulées positivement, ce dont `prompt_realiste` se charge.
    """

    name = "replicate"
    DEFAUT = "black-forest-labs/flux-1.1-pro"

    # Ratios acceptés par FLUX. On choisit le plus proche du format demandé
    # plutôt que d'imposer un recadrage.
    RATIOS = {(9, 16): "9:16", (4, 5): "4:5", (1, 1): "1:1",
              (3, 4): "3:4", (16, 9): "16:9", (4, 3): "4:3"}

    def __init__(self, token: str, model: str = ""):
        self.token = token
        self.model = model or self.DEFAUT

    def _ratio(self, width: int, height: int) -> str:
        cible = width / height
        return min(self.RATIOS.items(), key=lambda kv: abs(kv[0][0] / kv[0][1] - cible))[1]

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        headers = {"Authorization": f"Bearer {self.token}", "Prefer": "wait"}
        entree = {
            "prompt": prompt_realiste(prompt, limite=2000),
            "aspect_ratio": self._ratio(width, height),
            "output_format": "png",
            "seed": seed,
            # 2 = tolérance par défaut de Replicate ; on ne la relâche pas.
            "safety_tolerance": 2,
            # L'enrichissement automatique réécrit le prompt et fait dériver
            # le visage d'une image à l'autre : à laisser désactivé.
            "prompt_upsampling": False,
        }
        r = requests.post(
            f"https://api.replicate.com/v1/models/{self.model}/predictions",
            headers=headers, json={"input": entree}, timeout=300)
        if r.status_code >= 400:
            raise RuntimeError(f"Replicate {r.status_code} : {r.text[:300]}")

        data = r.json()
        for _ in range(90):
            if data.get("status") in {"succeeded", "failed", "canceled"}:
                break
            time.sleep(2)
            data = requests.get(data["urls"]["get"], headers=headers, timeout=60).json()

        if data.get("status") != "succeeded":
            raise RuntimeError(f"Replicate : {data.get('status')} — "
                               f"{str(data.get('error'))[:200]}")

        sortie = data["output"]
        url = sortie[0] if isinstance(sortie, list) else sortie
        contenu = requests.get(url, timeout=180).content
        if len(contenu) < 1024:
            raise RuntimeError("Replicate a renvoyé une image vide.")
        out.write_bytes(contenu)
        return out


class TogetherProvider(ImageProvider):
    """Together AI — FLUX.1 schnell, palier **gratuit** et sans carte.

    Le modèle « -Free » est bridé en débit mais ne coûte rien. FLUX rend un
    visage sans commune mesure avec « sana » : c'est le meilleur
    photoréalisme accessible sans payer.

    FLUX n'accepte pas de prompt négatif — modèle distillé sur la guidance.
    Les consignes de réalisme passent donc par le prompt positif.
    """

    name = "together"
    DEFAUT = "black-forest-labs/FLUX.1-schnell-Free"
    URL = "https://api.together.xyz/v1/images/generations"

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model = model or self.DEFAUT

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        import base64

        # FLUX schnell est distillé en 4 étapes : au-delà, on paie du temps
        # sans gagner en qualité.
        corps = {"model": self.model, "prompt": prompt_realiste(prompt, limite=2000),
                 "width": _multiple_de_16(width), "height": _multiple_de_16(height),
                 "steps": 4, "n": 1, "seed": seed, "response_format": "b64_json"}

        derniere: Exception | None = None
        for essai in range(3):
            try:
                r = requests.post(self.URL, headers={"Authorization": f"Bearer {self.api_key}"},
                                  json=corps, timeout=180)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"Together {r.status_code} (essai {essai + 1}/3)")
                if r.status_code >= 400:
                    raise RuntimeError(f"Together {r.status_code} : {r.text[:250]}")
                donnees = r.json()["data"][0]
                brut = (base64.b64decode(donnees["b64_json"]) if donnees.get("b64_json")
                        else requests.get(donnees["url"], timeout=120).content)
                if len(brut) < 1024:
                    raise RuntimeError("Together a renvoyé une image vide.")
                out.write_bytes(brut)
                return out
            except Exception as exc:
                derniere = exc
                log.warning("%s", exc)
                if essai < 2:
                    time.sleep(6 * (essai + 1))
        raise RuntimeError(f"Together indisponible après 3 essais : {derniere}")


class HuggingFaceProvider(ImageProvider):
    """Hugging Face — FLUX.1 schnell, palier gratuit lui aussi.

    Le premier appel réveille le modèle et peut renvoyer un 503 : c'est
    normal, on patiente et on relance.
    """

    name = "huggingface"
    DEFAUT = "black-forest-labs/FLUX.1-schnell"

    def __init__(self, api_key: str, model: str = ""):
        self.api_key = api_key
        self.model = model or self.DEFAUT

    def generate(self, prompt: str, out: Path, *, width: int, height: int, seed: int) -> Path:
        url = f"https://api-inference.huggingface.co/models/{self.model}"
        corps = {"inputs": prompt_realiste(prompt, limite=2000),
                 "parameters": {"width": _multiple_de_16(width),
                                "height": _multiple_de_16(height),
                                "num_inference_steps": 4, "seed": seed}}

        derniere: Exception | None = None
        for essai in range(4):
            try:
                r = requests.post(url, headers={"Authorization": f"Bearer {self.api_key}"},
                                  json=corps, timeout=180)
                if r.status_code in (429, 503) or r.status_code >= 500:
                    raise RuntimeError(f"Hugging Face {r.status_code} (essai {essai + 1}/4)")
                if r.status_code >= 400:
                    raise RuntimeError(f"Hugging Face {r.status_code} : {r.text[:250]}")
                if len(r.content) < 1024:
                    raise RuntimeError("Hugging Face a renvoyé une image vide.")
                out.write_bytes(r.content)
                return out
            except Exception as exc:
                derniere = exc
                log.warning("%s", exc)
                if essai < 3:
                    time.sleep(10 * (essai + 1))
        raise RuntimeError(f"Hugging Face indisponible après 4 essais : {derniere}")


def _multiple_de_16(valeur: int) -> int:
    """FLUX exige des dimensions multiples de 16."""
    return max(256, round(valeur / 16) * 16)


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
    if name in {"replicate", "flux"} and g.replicate_api_token:
        # « flux » est un alias : c'est le modèle que l'on veut, Replicate
        # n'est que le chemin pour y accéder.
        return ReplicateProvider(g.replicate_api_token,
                                 g.image_model if "/" in g.image_model else "")
    if name == "gemini":
        return GeminiProvider(g.image_model if g.image_model != "flux" else "")
    if name in {"together", "flux"} and g.together_api_key:
        return TogetherProvider(g.together_api_key, g.image_model if "/" in g.image_model else "")
    if name in {"huggingface", "hf"} and g.huggingface_api_key:
        return HuggingFaceProvider(g.huggingface_api_key,
                                   g.image_model if "/" in g.image_model else "")
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
