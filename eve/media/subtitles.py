"""Sous-titres incrustés — indispensables : la majorité des vues sont muettes."""
from __future__ import annotations

from pathlib import Path

from eve.content.scripts import Beat


def _ts(seconds: float, sep: str = ",") -> str:
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_srt(beats: list[Beat], out: Path, *, scale: float = 1.0) -> Path:
    """Sous-titres à partir des textes prononcés (redimensionnés si l'audio réel diffère)."""
    lines: list[str] = []
    for i, b in enumerate(beats, start=1):
        lines += [str(i),
                  f"{_ts(b.start_s * scale)} --> {_ts(b.end_s * scale)}",
                  _wrap(b.voiceover), ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


# Résolution de référence des sous-titres. libass met à l'échelle tout seul
# vers la taille réelle de la vidéo : on garde donc une police constante,
# quel que soit le rendu final (1080p, 720p, aperçu 540p).
ASS_PLAY_RES = (1080, 1920)


def write_ass(beats: list[Beat], out: Path, *, scale: float = 1.0,
              width: int = 1080, height: int = 1920) -> Path:
    """Style « caption TikTok » : gros, centré bas, contour épais."""
    del width, height  # la mise à l'échelle est gérée par libass
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {ASS_PLAY_RES[0]}
PlayResY: {ASS_PLAY_RES[1]}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Arial,66,&H00FFFFFF,&H00000000,&H80000000,-1,0,1,6,2,2,80,80,320,1
Style: Screen,Arial,56,&H0028E0FF,&H00000000,&H80000000,-1,0,1,6,2,8,80,80,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for b in beats:
        start, end = _ts(b.start_s * scale, "."), _ts(b.end_s * scale, ".")
        caption = _ass_text(b.voiceover, 22)
        events.append(f"Dialogue: 0,{start[:-1]},{end[:-1]},Caption,,0,0,0,,{caption}")
        if b.on_screen:
            screen = _ass_text(b.on_screen, 20)
            events.append(f"Dialogue: 0,{start[:-1]},{end[:-1]},Screen,,0,0,0,,{screen}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return out


def _ass_text(text: str, width: int) -> str:
    """Texte ASS : les sauts de ligne deviennent \\N."""
    return _wrap(text, width).replace("\n", "\\N")


def _wrap(text: str, width: int = 32) -> str:
    words, line, lines = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width and line:
            lines.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        lines.append(line)
    return "\n".join(lines[:3])
