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


# --------------------------------------------------------- réglages de voix
def test_le_preset_par_defaut_demande_de_ne_pas_jouer():
    from eve.media.voice_styles import DEFAUT, resolve

    consigne = resolve()
    assert consigne == resolve(DEFAUT)
    assert "ne joue pas" in consigne.lower()


def test_le_preset_aucun_envoie_une_consigne_vide():
    from eve.media.voice_styles import resolve

    assert resolve("aucun") == ""


def test_un_style_ecrit_a_la_main_prime_sur_le_preset():
    from eve.media.voice_styles import resolve

    assert resolve("confidence", "  Ton plat.  ") == "Ton plat."


def test_un_preset_inconnu_retombe_sur_le_defaut():
    from eve.media.voice_styles import DEFAUT, PRESETS, resolve

    assert resolve("nexiste-pas") == PRESETS[DEFAUT]


def test_les_consignes_de_realisme_atteignent_pollinations(monkeypatch, tmp_path):
    """Sans prompt négatif possible, elles doivent passer positivement."""
    from eve.media.images import PollinationsProvider

    vu = {}

    class Reponse:
        status_code = 200
        content = b"x" * 4096

        @staticmethod
        def raise_for_status():
            return None

    def faux_get(url, params=None, timeout=None):
        vu["url"] = url
        return Reponse()

    monkeypatch.setattr("eve.media.images.requests.get", faux_get)
    PollinationsProvider().generate("une femme", tmp_path / "a.png",
                                    width=512, height=512, seed=1)
    import urllib.parse
    envoye = urllib.parse.unquote(vu["url"])
    # Le service n'accepte aucun prompt négatif : ces consignes doivent donc
    # voyager dans le prompt lui-même, sans quoi le rendu part en « poupée ».
    assert "not a render" in envoye
    assert "no beauty filter" in envoye


def test_le_personnage_est_blond():
    from eve.persona.persona import load_persona

    verrou = load_persona().identity_lock.lower()
    assert "blonde" in verrou and "dark blonde" not in verrou


def test_le_prompt_reste_sous_la_limite_du_service():
    """Un prompt trop long fait renvoyer une erreur serveur."""
    from eve.media.images import LONGUEUR_MAX, REALISME_POSITIF, prompt_realiste

    court = prompt_realiste("une femme")
    assert court.endswith(REALISME_POSITIF)

    long = prompt_realiste("x" * 5000)
    assert len(long) <= LONGUEUR_MAX
    assert long.endswith(REALISME_POSITIF), "le réalisme survit à la troncature"


def test_pollinations_reessaie_sur_erreur_serveur(monkeypatch, tmp_path):
    from eve.media.images import PollinationsProvider

    appels = []

    class Reponse:
        def __init__(self, code):
            self.status_code = code
            self.content = b"x" * 4096

        def raise_for_status(self):
            return None

    def faux_get(url, params=None, timeout=None):
        appels.append(1)
        return Reponse(500 if len(appels) < 3 else 200)

    monkeypatch.setattr("eve.media.images.requests.get", faux_get)
    monkeypatch.setattr("eve.media.images.time.sleep", lambda s: None)
    PollinationsProvider().generate("x", tmp_path / "a.png", width=512, height=512, seed=1)
    assert len(appels) == 3, "deux 500 puis un succès"


# ------------------------------------------------- accès gratuits à FLUX
def test_flux_choisit_le_provider_gratuit_disponible(monkeypatch):
    from eve.config import settings
    from eve.media.images import get_provider

    monkeypatch.setattr(settings.generation, "together_api_key", "x")
    monkeypatch.setattr(settings.generation, "huggingface_api_key", "")
    assert get_provider("flux").name == "together"

    monkeypatch.setattr(settings.generation, "together_api_key", "")
    monkeypatch.setattr(settings.generation, "huggingface_api_key", "x")
    assert get_provider("hf").name == "huggingface"


def test_sans_cle_on_ne_casse_pas(monkeypatch):
    from eve.config import settings
    from eve.media.images import get_provider

    monkeypatch.setattr(settings.generation, "together_api_key", "")
    monkeypatch.setattr(settings.generation, "huggingface_api_key", "")
    # Repli sur le provider sans clé plutôt qu'une erreur au démarrage.
    assert get_provider("flux").name == "pollinations"


def test_flux_exige_des_dimensions_multiples_de_16():
    from eve.media.images import _multiple_de_16

    for valeur in (1080, 1350, 1920, 100):
        assert _multiple_de_16(valeur) % 16 == 0
    assert _multiple_de_16(10) == 256, "on ne descend pas sous une taille utile"


def test_together_reessaie_quand_le_quota_gratuit_sature(monkeypatch, tmp_path):
    import base64

    from eve.media.images import TogetherProvider

    appels = []

    class Reponse:
        def __init__(self, code):
            self.status_code = code
            self.text = ""

        def json(self):
            return {"data": [{"b64_json": base64.b64encode(b"x" * 4096).decode()}]}

    def faux_post(url, headers=None, json=None, timeout=None):
        appels.append(1)
        return Reponse(429 if len(appels) < 3 else 200)

    monkeypatch.setattr("eve.media.images.requests.post", faux_post)
    monkeypatch.setattr("eve.media.images.time.sleep", lambda s: None)
    TogetherProvider("cle").generate("x", tmp_path / "a.png",
                                     width=512, height=512, seed=1)
    assert len(appels) == 3, "le palier gratuit sature : il faut réessayer"
