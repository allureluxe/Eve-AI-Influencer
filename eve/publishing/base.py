"""Contrat commun aux plateformes de publication."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PublishRequest:
    caption: str
    # "reel" | "story" | "photo" — la Story a son propre type côté Graph API,
    # ne porte pas de légende et disparaît au bout de 24 h.
    kind: str = "reel"
    video_path: Path | None = None
    image_path: Path | None = None
    cover_path: Path | None = None
    video_url: str = ""      # URL publique (obligatoire pour Instagram)
    image_url: str = ""
    cover_url: str = ""
    is_ai_generated: bool = True
    privacy: str = "PUBLIC_TO_EVERYONE"
    metadata: dict = field(default_factory=dict)


@dataclass
class PublishResult:
    platform: str
    ok: bool
    post_id: str = ""
    url: str = ""
    detail: str = ""
    dry_run: bool = False

    def __str__(self) -> str:
        state = "DRY-RUN" if self.dry_run else ("OK" if self.ok else "ÉCHEC")
        return f"[{self.platform}] {state} {self.post_id or ''} {self.detail}".strip()


class Publisher:
    platform = "base"

    @property
    def configured(self) -> bool:
        raise NotImplementedError

    def publish(self, req: PublishRequest) -> PublishResult:
        raise NotImplementedError

    def fetch_metrics(self, post_id: str) -> dict:
        return {}
