"""Voix off.

`edge-tts` est gratuit et sans clé ; `gemini` passe par Google AI Studio
(palier gratuit, clé requise) ; `piper` tourne hors-ligne. En dernier
recours, une piste muette permet au montage d'aboutir quand même.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import wave
from pathlib import Path

from eve.config import settings

log = logging.getLogger(__name__)


class VoiceResult:
    def __init__(self, path: Path, provider: str, silent: bool = False):
        self.path, self.provider, self.silent = path, provider, silent


def _edge_tts(text: str, out: Path, voice: str, rate: str) -> Path:
    """Utilise le binaire `edge-tts` (pip install edge-tts)."""
    exe = shutil.which("edge-tts")
    if not exe:
        raise RuntimeError("binaire edge-tts introuvable")
    subprocess.run(
        [exe, "--text", text, "--voice", voice, "--rate", rate, "--write-media", str(out)],
        check=True, capture_output=True, timeout=300,
    )
    if not out.exists() or out.stat().st_size < 512:
        raise RuntimeError("edge-tts n'a produit aucun audio")
    return out


def _piper(text: str, out: Path, model: str) -> Path:
    """Piper : TTS local, hors-ligne, gratuit."""
    exe = shutil.which("piper")
    if not exe:
        raise RuntimeError("binaire piper introuvable")
    wav = out.with_suffix(".wav")
    subprocess.run([exe, "--model", model, "--output_file", str(wav)],
                   input=text.encode(), check=True, capture_output=True, timeout=300)
    return wav


def _gemini_tts(text: str, out: Path, voice: str, style: str = "") -> Path:
    """Google AI Studio : voix neuronales, palier gratuit.

    Le modèle renvoie du PCM brut (16 bits, mono) ; on l'emballe dans un
    WAV, seul format que ffmpeg lira sans deviner.
    """
    from eve.media import gemini

    consigne = f"{style.strip()}\n\n{text}" if style.strip() else text
    data = gemini.post_with_fallback("tts", "generateContent", {
        "contents": [{"role": "user", "parts": [{"text": consigne}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {
                "voiceName": voice or "Kore"}}},
        },
    })
    pcm, mime = gemini.first_inline_data(data)

    rate = 24000
    for morceau in mime.split(";"):
        if morceau.strip().startswith("rate="):
            rate = int(morceau.split("=", 1)[1])

    wav = out.with_suffix(".wav")
    with wave.open(str(wav), "w") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(pcm)
    return wav


def _silence(out: Path, seconds: float) -> Path:
    """Piste muette : permet au montage d'aboutir sans TTS installé."""
    wav = out.with_suffix(".wav")
    frames = int(24000 * max(seconds, 1.0))
    with wave.open(str(wav), "w") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(24000)
        fh.writeframes(b"\x00\x00" * frames)
    return wav


def synthesize(text: str, out: Path, *, expected_seconds: float = 20.0,
               provider: str | None = None) -> VoiceResult:
    g = settings.generation
    provider = (provider or g.voice_provider or "edge-tts").lower()
    out.parent.mkdir(parents=True, exist_ok=True)

    if provider != "silent":
        try:
            if provider == "gemini":
                return VoiceResult(_gemini_tts(text, out, g.voice_name, g.voice_style), "gemini")
            if provider == "piper":
                return VoiceResult(_piper(text, out, g.voice_name), "piper")
            return VoiceResult(_edge_tts(text, out, g.voice_name, g.voice_rate), "edge-tts")
        except Exception as exc:
            log.warning("TTS %s indisponible (%s) — piste muette utilisée.", provider, exc)

    return VoiceResult(_silence(out, expected_seconds), "silent", silent=True)


def audio_duration(path: Path) -> float | None:
    """Durée réelle de l'audio via ffprobe (None si ffprobe absent)."""
    exe = shutil.which("ffprobe")
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=True, capture_output=True, timeout=60,
        )
        return float(r.stdout.decode().strip())
    except Exception:
        return None
