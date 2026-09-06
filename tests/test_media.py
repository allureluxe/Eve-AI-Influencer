from datetime import date

import pytest

from eve.content.scripts import build_piece
from eve.media.images import generate_image, shot_seed
from eve.media.subtitles import write_ass, write_srt
from eve.media.video import ffmpeg_available, render
from eve.persona.persona import load_persona


@pytest.fixture(scope="module")
def piece():
    return build_piece(load_persona(), day=date(2026, 1, 9), slot="07:00", pillar="quick_workout")


def test_placeholder_provider_always_produces_a_file(tmp_path):
    result = generate_image("test", tmp_path / "a.png", seed=1, width=270, height=480,
                            provider="placeholder")
    assert result.path.exists() and result.placeholder


def test_failing_provider_falls_back_instead_of_crashing(tmp_path, monkeypatch):
    import eve.media.images as mod

    class Boom(mod.ImageProvider):
        name = "boom"

        def generate(self, *a, **k):
            raise RuntimeError("réseau indisponible")

    monkeypatch.setattr(mod, "get_provider", lambda name=None: Boom())
    result = mod.generate_image("x", tmp_path / "b.png", seed=2, width=270, height=480)
    assert result.placeholder, "l'agent ne doit jamais s'arrêter sur une panne de provider"


def test_shot_seeds_are_stable_and_distinct():
    assert shot_seed(100, 0) == shot_seed(100, 0)
    assert shot_seed(100, 1) != shot_seed(100, 0)


def test_subtitles_cover_the_whole_script(piece, tmp_path):
    srt = write_srt(piece.beats, tmp_path / "s.srt").read_text(encoding="utf-8")
    assert srt.count("-->") == len(piece.beats)
    ass = write_ass(piece.beats, tmp_path / "s.ass").read_text(encoding="utf-8")
    assert "[V4+ Styles]" in ass and ass.count("Dialogue:") >= len(piece.beats)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg absent de cet environnement")
def test_video_render_produces_a_playable_file(piece, tmp_path):
    images = [generate_image(b.shot_prompt, tmp_path / f"i{i}.png", seed=i,
                             width=270, height=480, provider="placeholder").path
              for i, b in enumerate(piece.beats)]
    subs = write_ass(piece.beats, tmp_path / "s.ass")
    result = render(piece.beats, images, tmp_path / "out.mp4", subtitles=subs,
                    width=270, height=480)
    assert result.path.exists() and result.path.stat().st_size > 10_000
    assert result.duration_s > 5


def test_voice_style_is_prefixed_to_the_text(monkeypatch, tmp_path):
    """La consigne de jeu doit atteindre le modèle, sinon le ton reste « pub »."""
    from eve.media import gemini, voice

    envoye = {}

    def faux_post(task, method, payload):
        envoye["texte"] = payload["contents"][0]["parts"][0]["text"]
        return {"candidates": [{"content": {"parts": [
            {"inlineData": {"data": "AAAA", "mimeType": "audio/L16;rate=24000"}}]}}]}

    monkeypatch.setattr(gemini, "post_with_fallback", faux_post)
    voice._gemini_tts("Bonjour.", tmp_path / "v.mp3", "Leda", "Ton détendu, pas publicitaire.")

    assert envoye["texte"].startswith("Ton détendu, pas publicitaire.")
    assert envoye["texte"].endswith("Bonjour.")


def test_voice_without_style_sends_only_the_text(monkeypatch, tmp_path):
    from eve.media import gemini, voice

    envoye = {}
    monkeypatch.setattr(gemini, "post_with_fallback", lambda task, me, p: (
        envoye.update(texte=p["contents"][0]["parts"][0]["text"]),
        {"candidates": [{"content": {"parts": [
            {"inlineData": {"data": "AAAA", "mimeType": "audio/L16;rate=24000"}}]}}]})[1])
    voice._gemini_tts("Bonjour.", tmp_path / "v.mp3", "Leda", "")
    assert envoye["texte"] == "Bonjour."
