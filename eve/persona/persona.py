"""Chargement du character bible et construction des prompts de génération."""
from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from eve.config import settings

# Style photographique commun : c'est lui qui donne le rendu "ultra réaliste".
PHOTO_STYLE = (
    "photorealistic candid photograph, shot on Sony A7 IV with 35mm f/1.8 lens, "
    "natural daylight, shallow depth of field, realistic skin texture with visible pores, "
    "subtle skin imperfections, natural film grain, true-to-life color grading, "
    "sharp focus on the eyes, editorial lifestyle photography, 8k detail"
)

# Anti-prompt : évite le rendu "3D / plastique" typique des IA.
NEGATIVE_PROMPT = (
    "3d render, cgi, plastic skin, airbrushed, waxy, doll-like, uncanny valley, "
    "over-smoothed skin, oversaturated, hdr halo, deformed hands, extra fingers, "
    "extra limbs, malformed anatomy, mutated, blurry, low resolution, jpeg artifacts, "
    "watermark, text, logo, distorted face, asymmetric eyes, duplicate face, "
    "cartoon, anime, illustration, painting, lingerie, nsfw, nude, suggestive pose"
)


@dataclass(frozen=True)
class Pillar:
    key: str
    label: str
    share: float


class Persona:
    """Représente Eve. Fournit prompts image/vidéo, ton, garde-fous éditoriaux."""

    def __init__(self, data: dict[str, Any]):
        self._d = data

    # ---------------------------------------------------------------- accès
    @property
    def name(self) -> str:
        return self._d["identity"]["name"]

    @property
    def handle(self) -> str:
        return self._d["identity"]["handle"]

    @property
    def age(self) -> int:
        return int(self._d["identity"]["age"])

    @property
    def identity_lock(self) -> str:
        return " ".join(self._d["appearance"]["identity_lock"].split())

    @property
    def seed(self) -> int:
        return int(self._d["appearance"].get("seed", settings.seed))

    @property
    def disclaimer(self) -> str:
        return " ".join(self._d["expertise"]["disclaimer"].split())

    @property
    def banned_phrases(self) -> list[str]:
        return [p.lower() for p in self._d["voice"]["banned_phrases"]]

    @property
    def emoji_palette(self) -> list[str]:
        return list(self._d["voice"]["emoji_palette"])

    @property
    def disclosure(self) -> dict[str, Any]:
        return self._d["disclosure"]

    @property
    def pillars(self) -> list[Pillar]:
        return [Pillar(p["key"], p["label"], float(p["share"]))
                for p in self._d["expertise"]["pillars"]]

    @property
    def pain_points(self) -> list[str]:
        return list(self._d["audience"]["pain_points"])

    @property
    def tone(self) -> str:
        return self._d["voice"]["tone"]

    def raw(self) -> dict[str, Any]:
        return self._d

    # ------------------------------------------------------------- prompts
    def outfit(self, category: str = "", rng: random.Random | None = None) -> str:
        """Tenue tirée d'une catégorie de la garde-robe.

        Catégorie inconnue ou absente : on retombe sur la première déclarée,
        pour qu'un renommage dans le character bible ne casse rien.
        """
        rng = rng or random
        wardrobe = self._d["wardrobe"]
        options = wardrobe.get(category) or next(iter(wardrobe.values()))
        return rng.choice(options)

    def location(self, rng: random.Random | None = None) -> str:
        rng = rng or random
        return rng.choice(self._d["locations"])

    def image_prompt(
        self,
        scene: str,
        *,
        outfit: str | None = None,
        location: str | None = None,
        rng: random.Random | None = None,
    ) -> str:
        """Assemble un prompt image : verrou d'identité + scène + style photo.

        Le verrou d'identité est toujours en tête : c'est ce qui, combiné au
        seed fixe, garde le même visage d'un post à l'autre.
        """
        rng = rng or random
        outfit = outfit or self.outfit(rng=rng)
        location = location or self.location(rng=rng)
        parts = [
            self.identity_lock,
            f"wearing {outfit}",
            scene.strip().rstrip("."),
            f"at {location}",
            PHOTO_STYLE,
        ]
        return ", ".join(p for p in parts if p)

    def system_prompt(self) -> str:
        """Prompt système pour le LLM qui écrit scripts et légendes."""
        d = self._d
        pillars = ", ".join(p["label"] for p in d["expertise"]["pillars"])
        return (
            f"Tu écris à la place de {d['identity']['full_name']} ({d['identity']['age']} ans), "
            f"créatrice virtuelle lifestyle basée à {d['identity']['city']}, {d['identity']['state']}. "
            f"Positionnement : {d['expertise']['positioning']} "
            f"Ton : {d['voice']['tone']}. "
            f"Piliers de contenu : {pillars}. "
            f"Audience : {d['audience']['primary']}. "
            f"Valeurs : {', '.join(d['voice']['values'])}. "
            "Règles absolues : jamais de promesse de gain, jamais de conseil en "
            "investissement, jamais de lien entre son train de vie et un revenu "
            "quelconque, aucun chiffre de performance inventé, "
            f"n'utilise jamais ces expressions : {', '.join(d['voice']['banned_phrases'])}. "
            "Écris court, concret, parlé, sans jargon marketing."
        )


@lru_cache(maxsize=1)
def load_persona(path: Path | None = None) -> Persona:
    src = path or settings.paths.persona_file
    with open(src, "r", encoding="utf-8") as fh:
        return Persona(yaml.safe_load(fh))
