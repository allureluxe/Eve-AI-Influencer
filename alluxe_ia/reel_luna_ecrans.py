"""Reel « Luna devant ses écrans » — 8 oct. 2026.

Demande de l'opérateur (ChatGPT ne l'a jamais comprise) : reprendre le Reel
qui a le mieux marché, « Je ne suis pas développeur » (~400 vues), et au lieu
de montrer les captures seules, les afficher SUR LES ÉCRANS de Luna, dans une
vraie vidéo où elle bouge. Accroche tirée de sa photo de référence :
« J'ai demandé à mon IA de faire ça… elle a refusé ! ».

    1. captures   : découpées dans le Reel d'origine (code, robot, labo, agent)
    2. images     : gpt-image-2, Luna + poste multi-écrans, la capture À
                    L'INTÉRIEUR du moniteur (pas collée par-dessus)
    3. vidéos     : Kling image→vidéo, 5 s par scène — elle bouge vraiment
    4. montage    : ffmpeg, textes nets posés au montage, son d'origine

Chaque étape est mise en cache : relancer ne repaie rien de ce qui existe.
Aucun montant de trading à l'écran (loi du 9 juin 2023). Rien n'est publié.

    python3 alluxe_ia/reel_luna_ecrans.py images
    python3 alluxe_ia/reel_luna_ecrans.py videos
    python3 alluxe_ia/reel_luna_ecrans.py montage
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

DOSSIER = RACINE / "data/alluxe_ia/reel_luna_ecrans"
SOURCE = Path(os.getenv("REEL_SOURCE", "/tmp/1000016175.mp4"))
REFERENCE_COMPO = DOSSIER / "reference_composition.png"
REFERENCE_LUNA = RACINE / "docs/luna/reference.jpg"
POLICE = RACINE / "alluxe_ia/polices/BricolageGrotesque.ttf"

#: (instant dans le Reel d'origine, boîte de découpe 720x1280)
CAPTURES = {
    "code": (6.0, (60, 85, 660, 770)),
    "robot": (8.5, (54, 0, 666, 680)),
    "labo": (16.0, (48, 100, 672, 832)),
    "agent": (20.0, (40, 92, 680, 768)),
}

COMMUN = (
    "Vertical smartphone selfie photo, ultra realistic, shot on a high-end "
    "phone at night. The young woman is EXACTLY the woman of the reference "
    "portrait: same face, platinum blonde long wavy hair with slightly darker "
    "roots, grey-green eyes, golden natural skin with real pores, one single "
    "small beauty mark above the left side of her upper lip, black "
    "sweatshirt. She sits very close to the camera in a dim home office in "
    "front of a multi-monitor desk exactly like the composition reference: "
    "several large computer monitors and a laptop around and behind her, the "
    "screens fill a large part of the frame and glow on her face. "
    "ABSOLUTELY NO text overlays, no captions, no stickers, no arrows, no "
    "watermark added on top of the photo: only what is physically displayed "
    "on the monitors. No money amounts or profit figures on any screen. "
    "Natural skin, no beauty filter, no plastic look."
)

SCENES = [
    {
        "nom": "1_refuse",
        "capture": None,
        "image": "She points her index finger at the big monitor on the right, "
                 "which shows a dark Claude interface with a red 'Action "
                 "bloquée' card and a checklist with green ticks; the laptop "
                 "in front shows a terminal log with a yellow WARNING line and "
                 "red lines. Other monitors show crypto candlestick charts "
                 "without numbers. She looks into the camera, lips slightly "
                 "pursed, confident and playful. Same framing as the "
                 "composition reference.",
        "video": "Handheld smartphone selfie video with subtle natural shake. "
                 "The woman blinks, breathes, glances at the camera then turns "
                 "her head toward the right monitor and taps toward it with her "
                 "index finger, then looks back at the camera with a small "
                 "knowing smile. The terminal text on the laptop scrolls "
                 "slowly. Screen content stays fixed on the monitor surfaces. "
                 "Her face stays identical, no morphing, no new text.",
    },
    {
        "nom": "2_code",
        "capture": "code",
        "image": "The large monitor right behind her shoulder displays EXACTLY "
                 "the provided code screenshot (dark code editor, green diff "
                 "lines), sharp and legible, in correct perspective, as if "
                 "really shown on that physical screen. She looks at that "
                 "monitor, one hand on the keyboard, focused.",
        "video": "Handheld smartphone selfie video, subtle shake. The woman "
                 "types a little on the keyboard, looks at the code on the "
                 "monitor, nods slightly, then glances at the camera. The code "
                 "on the screen scrolls down slowly. Screen content stays "
                 "fixed on the monitor surface. Same face, no morphing.",
    },
    {
        "nom": "3_robot",
        "capture": "robot",
        "image": "The large monitor next to her displays EXACTLY the provided "
                 "terminal screenshot (black terminal, many INFO log lines, "
                 "some yellow words), sharp and legible, in correct "
                 "perspective, physically on that screen. She points at it "
                 "with her index finger while looking at the camera, eyebrows "
                 "raised.",
        "video": "Handheld smartphone selfie video, subtle shake. The woman "
                 "points at the terminal monitor, her finger moves along the "
                 "log lines, she looks at the camera and raises her eyebrows. "
                 "New log lines scroll up on the terminal. Screen content "
                 "stays fixed on the monitor surface. Same face, no morphing.",
    },
    {
        "nom": "4_labo",
        "capture": "labo",
        "image": "The large monitor beside her displays EXACTLY the provided "
                 "white dashboard screenshot titled 'Laboratoire', sharp and "
                 "legible, in correct perspective, physically on that screen; "
                 "the other monitors show dark terminals. She leans toward "
                 "it, impressed, hand near her chin.",
        "video": "Handheld smartphone selfie video, subtle shake. The woman "
                 "leans toward the dashboard monitor, reads it, then turns to "
                 "the camera impressed and nods. The cursor moves a little on "
                 "the dashboard. Screen content stays fixed on the monitor "
                 "surface. Same face, no morphing.",
    },
    {
        "nom": "5_agent",
        "capture": "agent",
        "image": "The large monitor behind her displays EXACTLY the provided "
                 "chat screenshot (an AI assistant answering that it cannot "
                 "restart the real robot), sharp and legible, in correct "
                 "perspective, physically on that screen. She faces the camera "
                 "with a satisfied small smile and points her thumb back at "
                 "the screen.",
        "video": "Handheld smartphone selfie video, subtle shake. The woman "
                 "smiles at the camera, points her thumb back at the chat on "
                 "the monitor, glances at it, then looks back at the camera "
                 "and gives a small satisfied nod. Screen content stays fixed "
                 "on the monitor surface. Same face, no morphing.",
    },
]

#: (début, fin, texte, style) — secondes dans le Reel final
TEXTES = [
    (0.0, 4.2, "J'AI DEMANDÉ À MON IA\nDE FAIRE ÇA…", "titre"),
    (0.6, 4.2, "ELLE A REFUSÉ !", "rouge"),
    (4.2, 8.4, "1  Claude écrit le code.", "bas"),
    (8.4, 12.6, "2  Un robot qui surveille\n194 marchés.", "bas"),
    (12.6, 16.8, "3  Un labo qui a testé\n3 254 idées.", "bas"),
    (16.8, 21.6, "4  Un agent IA qui refuse\nce qui est dangereux.", "bas"),
    (18.6, 21.6, "ET C'EST EXACTEMENT\nCE QUE JE VEUX !", "final"),
    (0.0, 21.6, "Je ne suis pas développeur · @alluxe.ia", "signature"),
]
DUREE_SCENE = 4.2
DUREE_TOTALE = 21.6


def _journal(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


# 1 ----------------------------------------------------------------- captures
def captures() -> dict[str, Path]:
    sortie = DOSSIER / "captures"
    sortie.mkdir(parents=True, exist_ok=True)
    chemins = {}
    for nom, (t, boite) in CAPTURES.items():
        cible = sortie / f"{nom}.png"
        if not cible.exists():
            brut = sortie / f"{nom}_brut.png"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i",
                            str(SOURCE), "-frames:v", "1", str(brut)], check=True)
            Image.open(brut).crop(boite).save(cible)
            brut.unlink()
        chemins[nom] = cible
    return chemins


# 2 ------------------------------------------------------------------- images
def _multipart(champs: dict, fichiers: list[tuple[str, Path]]) -> tuple[bytes, str]:
    borne = uuid.uuid4().hex
    corps = bytearray()
    for k, v in champs.items():
        corps += (f"--{borne}\r\nContent-Disposition: form-data; name=\"{k}\""
                  f"\r\n\r\n{v}\r\n").encode()
    for k, chemin in fichiers:
        mime = "image/png" if chemin.suffix == ".png" else "image/jpeg"
        corps += (f"--{borne}\r\nContent-Disposition: form-data; name=\"{k}\"; "
                  f"filename=\"{chemin.name}\"\r\nContent-Type: {mime}\r\n\r\n"
                  ).encode()
        corps += chemin.read_bytes() + b"\r\n"
    corps += f"--{borne}--\r\n".encode()
    return bytes(corps), f"multipart/form-data; boundary={borne}"


def images() -> None:
    from luna.budget import Depenses
    caps = captures()
    sortie = DOSSIER / "images"
    sortie.mkdir(parents=True, exist_ok=True)
    cle = os.environ["OPENAI_API_KEY"]
    modele = os.getenv("LUNA_IMAGE_MODELE_OPENAI", "gpt-image-2")
    for s in SCENES:
        cible = sortie / f"{s['nom']}.png"
        if cible.exists():
            continue
        refs = [("image[]", REFERENCE_COMPO), ("image[]", REFERENCE_LUNA)]
        texte = COMMUN + " " + s["image"]
        if s["capture"]:
            refs.append(("image[]", caps[s["capture"]]))
            texte += (" Reference images: 1 = composition and mood, 2 = the "
                      "woman's face, 3 = the exact screenshot to show on the "
                      "monitor.")
        else:
            texte += " Reference images: 1 = composition, 2 = the woman's face."
        Depenses().reserver(float(os.getenv("LUNA_COUT_IMAGE_EUR", "0.07")),
                            f"image openai reel ecrans {s['nom']}")
        corps, ctype = _multipart({"model": modele, "prompt": texte,
                                   "size": "1024x1536", "n": "1",
                                   "quality": "high"}, refs)
        req = urllib.request.Request(
            "https://api.openai.com/v1/images/edits", data=corps, method="POST",
            headers={"Authorization": f"Bearer {cle}", "Content-Type": ctype})
        _journal(f"image {s['nom']}…")
        with urllib.request.urlopen(req, timeout=600) as r:
            rep = json.loads(r.read())
        cible.write_bytes(base64.b64decode(rep["data"][0]["b64_json"]))
        _journal(f"image {s['nom']} ok")


# 3 ------------------------------------------------------------------- vidéos
def videos() -> None:
    from luna.media import KlingVideo, telecharger
    k = KlingVideo()
    if not k.disponible:
        raise SystemExit("Kling non configuré")
    sortie = DOSSIER / "videos"
    sortie.mkdir(parents=True, exist_ok=True)
    taches_f = sortie / "taches.json"
    taches = json.loads(taches_f.read_text()) if taches_f.exists() else {}
    for s in SCENES:
        if (sortie / f"{s['nom']}.mp4").exists() or s["nom"] in taches:
            continue
        img = DOSSIER / "images" / f"{s['nom']}.png"
        b64 = base64.b64encode(img.read_bytes()).decode()
        taches[s["nom"]] = k.creer(b64, s["video"], "9:16", 5)
        taches_f.write_text(json.dumps(taches, indent=1))
        _journal(f"kling {s['nom']} lancé : {taches[s['nom']]}")
    while True:
        restant = 0
        for nom, tache in taches.items():
            cible = sortie / f"{nom}.mp4"
            if cible.exists():
                continue
            statut, url = k.resultat(tache)
            if statut == "succeeded":
                telecharger(url, str(cible))
                _journal(f"kling {nom} prêt")
            else:
                restant += 1
        if not restant:
            break
        time.sleep(20)


# 4 ------------------------------------------------------------------ montage
def _police(taille: int, poids: int = 800) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(POLICE), taille)
    try:
        f.set_variation_by_axes([poids])
    except Exception:
        pass
    return f


def _calque(texte: str, style: str) -> Image.Image:
    W, H = 1080, 1920
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if style == "titre":
        f = _police(74)
        d.multiline_text((W // 2, 150), texte, font=f, fill="white", anchor="ma",
                         align="center", stroke_width=7, stroke_fill="black",
                         spacing=6)
    elif style == "rouge":
        f = _police(96, 900)
        x0, y0, x1, y1 = d.textbbox((W // 2, 360), texte, font=f, anchor="ma")
        d.rounded_rectangle((x0 - 40, y0 - 26, x1 + 40, y1 + 30), 22,
                            fill=(228, 20, 30))
        d.text((W // 2, 360), texte, font=f, fill="white", anchor="ma")
    elif style == "bas":
        f = _police(62)
        x0, y0, x1, y1 = d.multiline_textbbox((70, 1420), texte, font=f,
                                              spacing=10)
        d.rounded_rectangle((x0 - 30, y0 - 26, x1 + 30, y1 + 30), 20,
                            fill=(20, 20, 22, 225))
        d.multiline_text((70, 1420), texte, font=f, fill=(255, 214, 0),
                         spacing=10)
    elif style == "final":
        f = _police(70, 900)
        x0, y0, x1, y1 = d.multiline_textbbox((W // 2, 1060), texte, font=f,
                                              anchor="ma", align="center",
                                              spacing=8)
        d.rectangle((x0 - 40, y0 - 30, x1 + 40, y1 + 34), fill="white")
        d.multiline_text((W // 2, 1060), texte, font=f, fill="black",
                         anchor="ma", align="center", spacing=8)
    elif style == "signature":
        f = _police(34, 600)
        d.text((W // 2, 1840), texte, font=f, fill="white", anchor="ma",
               stroke_width=3, stroke_fill="black")
    return im


def montage() -> Path:
    vids = DOSSIER / "videos"
    tmp = DOSSIER / "montage"
    tmp.mkdir(parents=True, exist_ok=True)
    morceaux = []
    for i, s in enumerate(SCENES):
        duree = DUREE_TOTALE - DUREE_SCENE * 4 if i == 4 else DUREE_SCENE
        m = tmp / f"m{i}.mp4"
        # 9:16 plein cadre, 30 i/s ; la dernière scène est allongée si besoin
        subprocess.run([
            "ffmpeg", "-v", "error", "-y", "-i", str(vids / f"{s['nom']}.mp4"),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
                   "crop=1080:1920,fps=30,tpad=stop_mode=clone:stop_duration=2",
            "-t", f"{duree:.3f}", "-an", "-c:v", "libx264", "-crf", "17",
            "-pix_fmt", "yuv420p", str(m)], check=True)
        morceaux.append(m)
    liste = tmp / "liste.txt"
    liste.write_text("".join(f"file '{m}'\n" for m in morceaux))
    brut = tmp / "brut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(liste), "-c", "copy", str(brut)], check=True)
    entrees = ["-i", str(brut), "-i", str(SOURCE)]
    filtres, prec = [], "0:v"
    for j, (t0, t1, texte, style) in enumerate(TEXTES):
        p = tmp / f"t{j}.png"
        _calque(texte, style).save(p)
        entrees += ["-i", str(p)]
        sortie = f"v{j}"
        filtres.append(f"[{prec}][{j + 2}:v]overlay=0:0:enable="
                       f"'between(t,{t0},{t1})'[{sortie}]")
        prec = sortie
    final = DOSSIER / "reel_luna_ecrans.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entrees,
                    "-filter_complex", ";".join(filtres),
                    "-map", f"[{prec}]", "-map", "1:a", "-t", str(DUREE_TOTALE),
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                    str(final)], check=True)
    _journal(f"Reel prêt : {final}")
    return final


if __name__ == "__main__":
    etape = sys.argv[1] if len(sys.argv) > 1 else "images"
    {"captures": captures, "images": images, "videos": videos,
     "montage": montage}[etape]()
