"""Le cerveau de l'agent : planifier, produire, contrôler, publier, apprendre.

Un cycle quotidien complet (`daily_run`) enchaîne :
    collecte des métriques → ré-pondération des piliers → planification
    → production des médias → contrôle de conformité → publication
    → rapport.

Deux garde-fous structurent tout le module :
  · `DRY_RUN=1` (défaut) : rien n'est publié, tout est produit et rapporté ;
  · `REQUIRE_HUMAN_REVIEW=1` (défaut) : un contenu reste en `draft` tant
    qu'un humain ne l'a pas approuvé (`eve approve`).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date as Date, datetime, timedelta
from pathlib import Path

from eve.agent.state import Store
from eve.analytics import collector, optimizer
from eve.config import settings
from eve.content.captions import caption_for
from eve.content.llm import get_llm
from eve.content.planner import plan_days
from eve.content.scripts import Beat, ContentPiece, build_piece
from eve.media import images as image_mod
from eve.media import subtitles as sub_mod
from eve.media import video as video_mod
from eve.media import voice as voice_mod
from eve.monetization.links import build_offers, monetization_line, pick_offer
from eve.persona.persona import Persona, load_persona
from eve.publishing.base import PublishRequest
from eve.publishing.instagram import InstagramPublisher
from eve.publishing.tiktok import TikTokPublisher
from eve.safety.policy import PolicyError, check_persona, enforce, review_post

log = logging.getLogger(__name__)


@dataclass
class RunReport:
    started_at: str
    planned: int = 0
    produced: int = 0
    published: list[str] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metrics_collected: int = 0
    weights: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_markdown(self, persona: Persona) -> str:
        lines = [f"# Rapport d'exécution — {self.started_at}",
                 f"Compte : @{persona.handle} · mode : "
                 f"{'DRY-RUN' if settings.dry_run else 'PUBLICATION RÉELLE'}",
                 "",
                 f"- Contenus planifiés : **{self.planned}**",
                 f"- Vidéos produites : **{self.produced}**",
                 f"- Publications : **{len(self.published)}**",
                 f"- Bloqués par la conformité : **{len(self.blocked)}**",
                 f"- Mesures collectées : **{self.metrics_collected}**"]
        if self.published:
            lines += ["", "## Publié"] + [f"- {p}" for p in self.published]
        if self.blocked:
            lines += ["", "## Bloqué (à corriger)"] + [f"- {b}" for b in self.blocked]
        if self.errors:
            lines += ["", "## Erreurs"] + [f"- {e}" for e in self.errors]
        if self.weights:
            lines += ["", "## Nouvelles pondérations de piliers"]
            lines += [f"- {k} : {v:.0%}" for k, v in sorted(self.weights.items(), key=lambda kv: -kv[1])]
        if self.notes:
            lines += ["", "## Notes"] + [f"- {n}" for n in self.notes]
        return "\n".join(lines)


class EveAgent:
    def __init__(self, persona: Persona | None = None, store: Store | None = None):
        self.persona = persona or load_persona()
        self.store = store or Store()
        self.llm = get_llm()
        self.publishers = {"instagram": InstagramPublisher(), "tiktok": TikTokPublisher()}

    # ------------------------------------------------------------- 1. plan
    def plan(self, start: Date | None = None, days: int = 7) -> list[ContentPiece]:
        start = start or Date.today()
        weights = self.store.get_kv("pillar_weights") or None
        slots = plan_days(self.persona, start, days=days, weights=weights)

        pieces: list[ContentPiece] = []
        for slot in slots:
            if self.store.get_piece(slot.key):
                continue  # déjà planifié : on ne régénère jamais un contenu existant
            piece = build_piece(self.persona, day=slot.day, slot=slot.time,
                                pillar=slot.pillar, llm=self.llm)
            # On contrôle la légende telle qu'elle sera publiée, pas le corps
            # brut : c'est la version assemblée qui part sur les plateformes.
            review = check_persona(self.persona)
            for finale in self.captions(piece).values():
                _, controle = review_post(self.persona, caption=finale,
                                          visual_prompts=piece.shot_prompts,
                                          pillar=piece.pillar)
                review = review.merge(controle)
            status = "blocked" if not review.ok else (
                "draft" if settings.require_human_review else "approved")
            piece.status = status
            self.store.save_piece(piece.id, piece.date, piece.slot, piece.pillar,
                                  piece.to_dict() | {"review": review.report()}, status)
            pieces.append(piece)
        log.info("Planification : %d nouveau(x) contenu(s) sur %d jours.", len(pieces), days)
        return pieces

    # ---------------------------------------------------------- 2. produce
    def produce(self, piece: ContentPiece, *, force: bool = False) -> ContentPiece:
        """Génère images, voix, sous-titres et vidéo finale."""
        out_dir = settings.paths.videos / piece.id
        out_dir.mkdir(parents=True, exist_ok=True)
        video_path = out_dir / f"{piece.id}.mp4"

        if video_path.exists() and not force:
            piece.assets["video"] = str(video_path)
            return piece

        image_paths: list[Path] = []
        placeholders = 0
        for i, beat in enumerate(piece.beats):
            target = settings.paths.images / piece.id / f"shot_{i:02d}.png"
            result = image_mod.generate_image(
                beat.shot_prompt, target,
                seed=image_mod.shot_seed(self.persona.seed, i),
                width=settings.generation.reel_width,
                height=settings.generation.reel_height)
            image_paths.append(result.path)
            placeholders += int(result.placeholder)
        piece.assets["images"] = [str(p) for p in image_paths]
        piece.assets["placeholder_images"] = placeholders
        if placeholders:
            piece.assets["warning"] = (
                f"{placeholders}/{len(image_paths)} images sont des placeholders "
                "(provider indisponible) — à régénérer avant publication réelle.")

        audio = voice_mod.synthesize(piece.voiceover_text, settings.paths.audio / f"{piece.id}.mp3",
                                     expected_seconds=piece.duration_s)
        piece.assets["audio"] = str(audio.path)

        # Recale les sous-titres sur la durée réelle de la voix off.
        scale = 1.0
        real = voice_mod.audio_duration(audio.path)
        if real and piece.duration_s and not audio.silent:
            scale = max(0.6, min(1.6, real / piece.duration_s))
        beats = _rescale(piece.beats, scale)
        subs = sub_mod.write_ass(beats, out_dir / f"{piece.id}.ass")
        sub_mod.write_srt(beats, out_dir / f"{piece.id}.srt")
        piece.assets["subtitles"] = str(subs)

        music = _pick_music()
        try:
            result = video_mod.render(beats, image_paths, video_path,
                                      audio=audio.path, subtitles=subs, music=music)
            piece.assets["video"] = str(result.path)
            cover = video_mod.render_cover(image_paths[0], out_dir / "cover.jpg", piece.title)
            piece.assets["cover"] = str(cover)
        except video_mod.FFmpegMissing as exc:
            piece.assets["video_error"] = str(exc)
            log.warning("Vidéo non montée : %s", exc)

        # Légendes écrites à côté du MP4 : c'est ce qui rend la publication
        # manuelle possible sans ouvrir la base ni le code.
        piece.assets["captions"] = str(self._write_captions(piece, out_dir))

        piece.status = "ready" if piece.assets.get("video") else piece.status
        self.store.save_piece(piece.id, piece.date, piece.slot, piece.pillar,
                              piece.to_dict(), piece.status)
        return piece

    def captions(self, piece: ContentPiece) -> dict[str, str]:
        """Légende finale par plateforme, offre de monétisation incluse."""
        offers = build_offers()
        offer = pick_offer(piece.pillar, offers)
        out: dict[str, str] = {}
        for platform in piece.platforms:
            money = monetization_line(offer, platform, campaign=f"{piece.date}-{piece.pillar}")
            caption, _ = review_post(self.persona,
                                     caption=caption_for(piece, self.persona, platform, money),
                                     visual_prompts=piece.shot_prompts, pillar=piece.pillar)
            out[platform] = caption
        return out

    def _write_captions(self, piece: ContentPiece, out_dir: Path) -> Path:
        blocks = [f"{piece.title}", f"({piece.pillar} · {piece.duration_s:.0f} s)", ""]
        for platform, caption in self.captions(piece).items():
            blocks += [f"{'═' * 58}", f"  {platform.upper()} — à copier-coller",
                       f"{'═' * 58}", "", caption, ""]
        blocks += [f"{'═' * 58}", "  RAPPEL", f"{'═' * 58}",
                   "  Activer le label IA au moment de publier :",
                   "    Instagram → « AI info »",
                   "    TikTok    → « contenu généré par IA »"]
        path = out_dir / "legendes.txt"
        path.write_text("\n".join(blocks), encoding="utf-8")
        return path

    # ---------------------------------------------------------- 3. publish
    def publish(self, piece: ContentPiece, platforms: list[str] | None = None) -> list[str]:
        platforms = platforms or piece.platforms
        offers = build_offers()
        results: list[str] = []

        # Une image placeholder sur un vrai compte, c'est un post grillé.
        # En dry-run on laisse passer : c'est justement le mode d'essai.
        if not settings.dry_run and piece.assets.get("placeholder_images"):
            self.store.set_status(piece.id, "blocked")
            return [f"{p} · BLOQUÉ · {piece.assets['placeholder_images']} image(s) placeholder : "
                    "relancer la production quand le générateur d'images répond."
                    for p in platforms]

        for platform in platforms:
            publisher = self.publishers.get(platform)
            if not publisher:
                continue
            if self.store.is_published(piece.id, platform):
                log.info("%s déjà publié sur %s — ignoré.", piece.id, platform)
                continue

            offer = pick_offer(piece.pillar, offers)
            money_line = monetization_line(offer, platform, campaign=f"{piece.date}-{piece.pillar}")
            caption = caption_for(piece, self.persona, platform, money_line)

            caption, review = review_post(self.persona, caption=caption,
                                          visual_prompts=piece.shot_prompts,
                                          pillar=piece.pillar)
            try:
                enforce(review)
            except PolicyError as exc:
                self.store.set_status(piece.id, "blocked")
                results.append(f"{platform} · BLOQUÉ · {exc}")
                continue

            video_path = Path(piece.assets["video"]) if piece.assets.get("video") else None
            base_url = settings.publishing.public_media_base_url.rstrip("/")
            req = PublishRequest(
                caption=caption,
                video_path=video_path,
                cover_path=Path(piece.assets["cover"]) if piece.assets.get("cover") else None,
                video_url=f"{base_url}/{piece.id}.mp4" if base_url and video_path else "",
                is_ai_generated=True,
                metadata={"pillar": piece.pillar, "offer": offer.key if offer else ""},
            )
            result = publisher.publish(req)
            self.store.record_publication(piece.id, platform, result.ok, result.post_id,
                                          result.url, result.detail, result.dry_run)
            results.append(str(result))

        if any("OK" in r or "DRY-RUN" in r for r in results):
            self.store.set_status(piece.id, "published")
        return results

    # ------------------------------------------------------- 4. apprendre
    def learn(self) -> tuple[int, dict]:
        collected = collector.collect(self.store)
        weights = optimizer.suggest_weights(self.persona, self.store)
        self.store.set_kv("pillar_weights", weights)
        return collected, weights

    # ------------------------------------------------------- cycle complet
    def daily_run(self, *, days_ahead: int = 3, max_publish: int = 2,
                  produce_limit: int = 4) -> RunReport:
        report = RunReport(started_at=datetime.now().isoformat(timespec="seconds"))

        try:
            report.metrics_collected, report.weights = self.learn()
        except Exception as exc:
            report.errors.append(f"apprentissage : {exc}")

        try:
            report.planned = len(self.plan(days=days_ahead))
        except Exception as exc:
            report.errors.append(f"planification : {exc}")

        # Production anticipée : on fabrique avant l'heure de publication.
        horizon = (Date.today() + timedelta(days=1)).isoformat()
        to_produce = [p for p in self.store.pieces_by_status("approved", limit=produce_limit)
                      if p["day"] <= horizon]
        if not settings.require_human_review:
            to_produce += [p for p in self.store.pieces_by_status("draft", limit=produce_limit)
                           if p["day"] <= horizon]

        for row in to_produce[:produce_limit]:
            try:
                piece = _piece_from_row(row)
                self.produce(piece)
                report.produced += 1
            except Exception as exc:
                report.errors.append(f"production {row['id']} : {exc}")

        for row in self.store.due_pieces(Date.today().isoformat(), limit=max_publish):
            piece = _piece_from_row(row)
            if not piece.assets.get("video"):
                try:
                    piece = self.produce(piece)
                except Exception as exc:
                    report.errors.append(f"production {piece.id} : {exc}")
                    continue
            try:
                results = self.publish(piece)
                for r in results:
                    (report.blocked if "BLOQUÉ" in r else report.published).append(f"{piece.id} · {r}")
            except Exception as exc:
                report.errors.append(f"publication {piece.id} : {exc}")

        pending = self.store.pieces_by_status("draft", limit=100)
        if settings.require_human_review and pending:
            report.notes.append(
                f"{len(pending)} contenu(s) en attente de validation humaine "
                "(`python -m eve.cli approve --all` pour tout approuver).")
        report.notes += optimizer.recommendations(self.store, self.persona)

        path = settings.paths.reports / f"run_{Date.today().isoformat()}.md"
        path.write_text(report.to_markdown(self.persona), encoding="utf-8")
        log.info("Rapport écrit : %s", path)
        return report


# ------------------------------------------------------------------ outils
def _rescale(beats: list[Beat], scale: float) -> list[Beat]:
    if abs(scale - 1.0) < 0.02:
        return beats
    return [Beat(b.index, round(b.start_s * scale, 2), round(b.end_s * scale, 2),
                 b.voiceover, b.on_screen, b.shot_prompt) for b in beats]


def _piece_from_row(row: dict) -> ContentPiece:
    payload = json.loads(row["payload"])
    payload.pop("review", None)
    payload.pop("duration_s", None)
    payload["beats"] = [Beat(**b) for b in payload.get("beats", [])]
    payload.setdefault("status", row["status"])
    return ContentPiece(**payload)


def _pick_music() -> Path | None:
    """Musique de fond libre de droits déposée par l'utilisateur.

    Rien n'est fourni : utiliser la bibliothèque sonore native de TikTok ou
    d'Instagram donne plus de portée et évite tout risque de copyright.
    """
    folder = settings.paths.assets / "music"
    if not folder.exists():
        return None
    tracks = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".mp3", ".m4a", ".wav"})
    return tracks[0] if tracks else None
