"""Montage vidéo vertical avec ffmpeg (gratuit, local).

Chaîne : 1 image par plan → effet Ken Burns → concaténation → voix off
(+ musique optionnelle) → sous-titres incrustés → MP4 9:16 prêt à publier.

Un clip par plan plutôt qu'un unique `filter_complex` géant : c'est plus
lent de quelques secondes, mais beaucoup plus robuste et débogable.
"""
from __future__ import annotations

import logging
import random
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from eve.config import settings
from eve.content.scripts import Beat

log = logging.getLogger(__name__)

FPS = 30


class FFmpegMissing(RuntimeError):
    pass


@dataclass
class VideoResult:
    path: Path
    duration_s: float
    has_audio: bool


def ffmpeg_available() -> bool:
    return bool(shutil.which("ffmpeg"))


def _run(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, timeout=1800)
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace")[-1500:]
        raise RuntimeError(f"ffmpeg a échoué :\n{tail}")


def _kenburns_clip(image: Path, out: Path, duration: float, *, width: int, height: int,
                   direction: str) -> Path:
    """Zoom lent + léger panoramique : le mouvement retient l'attention."""
    frames = max(int(duration * FPS), 1)
    zoom_in = direction in {"in", "in_left", "in_right"}
    zexpr = ("min(zoom+0.0012,1.18)" if zoom_in else "if(lte(zoom,1.0),1.18,max(1.001,zoom-0.0012))")
    xexpr = {"in_left": "iw/2-(iw/zoom/2)-on*0.25",
             "in_right": "iw/2-(iw/zoom/2)+on*0.25"}.get(direction, "iw/2-(iw/zoom/2)")
    vf = (
        f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=increase,"
        f"crop={width * 2}:{height * 2},"
        f"zoompan=z='{zexpr}':x='{xexpr}':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={FPS},"
        f"setsar=1"
    )
    _run(["ffmpeg", "-y", "-loop", "1", "-i", str(image), "-vf", vf,
          "-t", f"{duration:.2f}", "-c:v", "libx264", "-preset", "veryfast",
          "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)])
    return out


def render(
    beats: list[Beat],
    images: list[Path],
    out_path: Path,
    *,
    audio: Path | None = None,
    subtitles: Path | None = None,
    music: Path | None = None,
    width: int | None = None,
    height: int | None = None,
    work_dir: Path | None = None,
) -> VideoResult:
    if not ffmpeg_available():
        raise FFmpegMissing(
            "ffmpeg est requis pour le montage. Installation : "
            "`sudo apt install ffmpeg` (Linux) ou `brew install ffmpeg` (macOS)."
        )
    if len(images) < len(beats):
        raise ValueError("Il faut au moins une image par plan.")

    width = width or settings.generation.reel_width
    height = height or settings.generation.reel_height
    work = work_dir or (out_path.parent / f".work_{out_path.stem}")
    work.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(out_path.stem)
    directions = ["in", "out", "in_left", "in_right"]

    clips: list[Path] = []
    for i, beat in enumerate(beats):
        clip = work / f"clip_{i:03d}.mp4"
        _kenburns_clip(images[i], clip, max(beat.duration, 1.0),
                       width=width, height=height, direction=rng.choice(directions))
        clips.append(clip)

    concat_file = work / "concat.txt"
    concat_file.write_text("".join(f"file '{c.resolve()}'\n" for c in clips), encoding="utf-8")
    silent = work / "silent.mp4"
    _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
          "-c", "copy", str(silent)])

    args = ["ffmpeg", "-y", "-i", str(silent)]
    filters: list[str] = []
    audio_maps: list[str] = []
    has_audio = False

    if audio and audio.exists():
        args += ["-i", str(audio)]
        has_audio = True
        if music and music.exists():
            args += ["-stream_loop", "-1", "-i", str(music)]
            filters.append("[1:a]volume=1.0[voice];[2:a]volume=0.12[bed];"
                           "[voice][bed]amix=inputs=2:duration=first:dropout_transition=2[aout]")
            audio_maps = ["-map", "[aout]"]
        else:
            audio_maps = ["-map", "1:a"]

    vf = []
    if subtitles and subtitles.exists():
        escaped = str(subtitles.resolve()).replace("\\", "/").replace(":", r"\:")
        vf.append(f"subtitles='{escaped}'" if subtitles.suffix == ".srt" else f"ass='{escaped}'")
    if vf:
        filters.append(f"[0:v]{','.join(vf)}[vout]")
        video_map = ["-map", "[vout]"]
    else:
        video_map = ["-map", "0:v"]

    if filters:
        args += ["-filter_complex", ";".join(filters)]
    args += video_map + audio_maps
    args += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-r", str(FPS), "-movflags", "+faststart"]
    if has_audio:
        args += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    args.append(str(out_path))
    _run(args)

    shutil.rmtree(work, ignore_errors=True)
    duration = sum(max(b.duration, 1.0) for b in beats)
    return VideoResult(out_path, round(duration, 2), has_audio)


def render_cover(image: Path, out_path: Path, title: str,
                 *, width: int | None = None, height: int | None = None) -> Path:
    """Miniature/couverture : première impression dans le feed."""
    if not ffmpeg_available():
        shutil.copyfile(image, out_path)
        return out_path
    width = width or settings.generation.image_width
    height = height or settings.generation.image_height
    safe = title.replace("'", "").replace(":", "").replace("%", "")[:40]
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
          f"drawbox=y=ih*0.72:w=iw:h=ih*0.28:color=black@0.45:t=fill,"
          f"drawtext=text='{safe}':fontcolor=white:fontsize={int(width / 16)}:"
          f"x=(w-text_w)/2:y=h*0.78")
    try:
        _run(["ffmpeg", "-y", "-i", str(image), "-vf", vf, "-frames:v", "1", str(out_path)])
    except RuntimeError:  # drawtext absent de certains builds ffmpeg
        shutil.copyfile(image, out_path)
    return out_path
