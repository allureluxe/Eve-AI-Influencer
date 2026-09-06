"""Configuration centrale — tout est pilotable par variables d'environnement.

Aucune clé d'API n'est requise pour le mode gratuit : les providers par défaut
(`pollinations`, `edge-tts`, `template`) fonctionnent sans compte payant.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv est optionnel
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass

ROOT = Path(__file__).resolve().parent.parent


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


def _flag(key: str, default: bool = False) -> bool:
    raw = _env(key, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _int(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except ValueError:
        return default


@dataclass
class Paths:
    root: Path = ROOT
    data: Path = ROOT / "data"
    output: Path = ROOT / "output"
    images: Path = ROOT / "output" / "images"
    videos: Path = ROOT / "output" / "videos"
    audio: Path = ROOT / "output" / "audio"
    products: Path = ROOT / "output" / "products"
    reports: Path = ROOT / "output" / "reports"
    assets: Path = ROOT / "assets"
    persona_file: Path = ROOT / "eve" / "persona" / "eve.yaml"
    db: Path = ROOT / "data" / "eve.db"

    def ensure(self) -> None:
        for p in (self.data, self.output, self.images, self.videos,
                  self.audio, self.products, self.reports):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class GenerationConfig:
    """Providers de génération. `free` = aucun coût, aucune carte bancaire."""

    image_provider: str = field(default_factory=lambda: _env("IMAGE_PROVIDER", "pollinations"))
    image_model: str = field(default_factory=lambda: _env("IMAGE_MODEL", "flux"))
    image_width: int = field(default_factory=lambda: _int("IMAGE_WIDTH", 1080))
    image_height: int = field(default_factory=lambda: _int("IMAGE_HEIGHT", 1350))
    reel_width: int = field(default_factory=lambda: _int("REEL_WIDTH", 1080))
    reel_height: int = field(default_factory=lambda: _int("REEL_HEIGHT", 1920))

    comfyui_url: str = field(default_factory=lambda: _env("COMFYUI_URL", "http://127.0.0.1:8188"))
    stability_api_key: str = field(default_factory=lambda: _env("STABILITY_API_KEY"))
    replicate_api_token: str = field(default_factory=lambda: _env("REPLICATE_API_TOKEN"))

    voice_provider: str = field(default_factory=lambda: _env("VOICE_PROVIDER", "edge-tts"))
    voice_name: str = field(default_factory=lambda: _env("VOICE_NAME", "en-US-AvaNeural"))
    voice_rate: str = field(default_factory=lambda: _env("VOICE_RATE", "+8%"))
    # Consigne de jeu passée au TTS Gemini. C'est le levier principal :
    # la même voix passe du spot publicitaire au message vocal selon ce texte.
    voice_style: str = field(default_factory=lambda: _env(
        "VOICE_STYLE",
        "Lis ce texte comme une vidéo filmée au téléphone, pas comme une "
        "publicité : ton naturel et détendu, débit irrégulier, quelques "
        "hésitations, comme si tu parlais à une amie. Ne surarticule pas, "
        "n'exagère aucune intonation, ne souris pas dans la voix."))

    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "template"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", ""))
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://127.0.0.1:11434"))


@dataclass
class PublishingConfig:
    instagram_user_id: str = field(default_factory=lambda: _env("IG_USER_ID"))
    instagram_token: str = field(default_factory=lambda: _env("IG_ACCESS_TOKEN"))
    graph_api_version: str = field(default_factory=lambda: _env("GRAPH_API_VERSION", "v21.0"))

    tiktok_access_token: str = field(default_factory=lambda: _env("TIKTOK_ACCESS_TOKEN"))
    tiktok_client_key: str = field(default_factory=lambda: _env("TIKTOK_CLIENT_KEY"))
    tiktok_client_secret: str = field(default_factory=lambda: _env("TIKTOK_CLIENT_SECRET"))
    # TikTok exige un upload direct (FILE_UPLOAD) ou une URL publique vérifiée.
    public_media_base_url: str = field(default_factory=lambda: _env("PUBLIC_MEDIA_BASE_URL"))

    posts_per_day: int = field(default_factory=lambda: _int("POSTS_PER_DAY", 2))
    timezone: str = field(default_factory=lambda: _env("TIMEZONE", "America/New_York"))
    slots: str = field(default_factory=lambda: _env("POST_SLOTS", "06:30,18:00"))

    @property
    def time_slots(self) -> list[str]:
        return [s.strip() for s in self.slots.split(",") if s.strip()]


@dataclass
class MonetizationConfig:
    amazon_tag: str = field(default_factory=lambda: _env("AMAZON_ASSOCIATE_TAG"))
    shop_url: str = field(default_factory=lambda: _env("SHOP_URL"))
    linkinbio_url: str = field(default_factory=lambda: _env("LINKINBIO_URL"))
    stripe_payment_link: str = field(default_factory=lambda: _env("STRIPE_PAYMENT_LINK"))
    paypal_me: str = field(default_factory=lambda: _env("PAYPAL_ME"))
    business_email: str = field(default_factory=lambda: _env("BUSINESS_EMAIL"))


@dataclass
class Settings:
    paths: Paths = field(default_factory=Paths)
    generation: GenerationConfig = field(default_factory=GenerationConfig)
    publishing: PublishingConfig = field(default_factory=PublishingConfig)
    monetization: MonetizationConfig = field(default_factory=MonetizationConfig)

    dry_run: bool = field(default_factory=lambda: _flag("DRY_RUN", True))
    require_human_review: bool = field(default_factory=lambda: _flag("REQUIRE_HUMAN_REVIEW", True))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    seed: int = field(default_factory=lambda: _int("PERSONA_SEED", 774921))

    def describe(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "require_human_review": self.require_human_review,
            "image_provider": self.generation.image_provider,
            "voice_provider": self.generation.voice_provider,
            "llm_provider": self.generation.llm_provider,
            "instagram_configured": bool(self.publishing.instagram_token and self.publishing.instagram_user_id),
            "tiktok_configured": bool(self.publishing.tiktok_access_token),
            "posts_per_day": self.publishing.posts_per_day,
            "slots": self.publishing.time_slots,
        }


settings = Settings()
settings.paths.ensure()
