"""Reel 06 avec Luna — « J'ai construit CE site en 1 journée » (10 oct. 2026).

Demande de l'opérateur : Luna dans le prochain Reel. Mesuré le 10 oct. : le Reel
« Je ne suis pas développeur » (2,8 K vues) était PAYÉ ; sans publicité il fait
~130 vues, autant que le Reel Luna (129) — et sur TikTok la version Luna est la
seule regardée en entier (12,3 s pour 10 s, contre 3,3 s sur 21,6 s). Luna ouvre
donc la vidéo, dès la 1re seconde.

    0,0 - 3,0   Luna devant ses écrans, le VRAI site alluxe.fr sur le moniteur
    3,0 - 11,2  Reel 06 d'origine : le prompt exact, puis les vraies pages
    11,2 - 13,6 Luna montre le code écrit par Claude : « 0 ligne de code écrite par moi »
    13,6 - 16,3 Reel 06 d'origine : « Partie 1 / Abonne-toi pour la partie 2 »

    python3 alluxe_ia/reel_site_luna.py images
    python3 alluxe_ia/reel_site_luna.py videos
    python3 alluxe_ia/reel_site_luna.py montage

Chaque étape est en cache : relancer ne repaie rien. Rien n'est publié.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from alluxe_ia.reel_luna_ecrans import (COMMUN, REFERENCE_COMPO, REFERENCE_LUNA,  # noqa: E402
                                        _calque, _journal, _multipart)

DOSSIER = RACINE / "data/alluxe_ia/reel_site_luna"
REEL_06 = RACINE / "data/alluxe_ia/reels/06-site-en-1-journee.mp4"
SITE = RACINE / "data/alluxe_ia/captures/site/accueil.png"
CODE = sorted((RACINE / "data/alluxe_ia/captures/term").glob("claude_*.png"))

SCENES = [
    {
        "nom": "1_site",
        "capture": SITE,
        "duree": 3.0,
        "image": "The large monitor right next to her displays EXACTLY the provided "
                 "website screenshot (a clean cream and yellow homepage), sharp and "
                 "legible, in correct perspective, as if really shown on that physical "
                 "screen. She points her index finger at that monitor while looking "
                 "into the camera, eyebrows raised, proud and playful.",
        "video": "Handheld smartphone selfie video with subtle natural shake. The "
                 "woman looks at the camera, then turns toward the website monitor and "
                 "taps toward it with her index finger, then looks back at the camera "
                 "with a proud smile. The website on the screen scrolls down slowly. "
                 "Screen content stays fixed on the monitor surface. Her face stays "
                 "identical, no morphing, no new text.",
    },
    {
        "nom": "2_code",
        "capture": CODE[-1] if CODE else None,
        "duree": 2.4,
        "image": "The large monitor behind her shoulder displays EXACTLY the provided "
                 "terminal screenshot (an AI assistant writing code), sharp and legible, "
                 "in correct perspective, physically on that screen. She raises both "
                 "hands slightly, palms open, as if saying 'not me', with an amused "
                 "smile at the camera.",
        "video": "Handheld smartphone selfie video, subtle shake. The woman shrugs with "
                 "open palms and an amused smile, glances at the code on the monitor, "
                 "then back at the camera. The code on the screen scrolls slowly. "
                 "Screen content stays fixed on the monitor surface. Same face, no "
                 "morphing.",
    },
]

#: (début, fin, texte, style) sur la vidéo finale de 16,3 s
TEXTES = [
    (0.0, 3.0, "J'AI CONSTRUIT\nCE SITE…", "titre"),
    (0.9, 3.0, "EN 1 JOURNÉE", "rouge"),
    (11.2, 13.6, "0 ligne de code\nécrite par moi.", "bas"),
    (0.0, 3.0, "@alluxe.ia · Luna, personnage IA", "signature"),
    (11.2, 13.6, "@alluxe.ia · Luna, personnage IA", "signature"),
]

#: morceaux du Reel 06 d'origine repris tels quels (début, fin)
MORCEAUX_06 = {"prompt_pages": (2.2, 10.4), "fin": (12.8, 15.5)}


LEGENDE = "J'ai construit ce site en 1 journée. Je ne sais pas coder 👇\n\nLe prompt de départ (copie-le) :\n« Je veux construire [ton idée, même floue]. Je ne suis pas développeur. Pose-moi 10 questions, une à la fois, pour comprendre ce que je veux vraiment. N'écris aucun code. »\n\nPourquoi ça marche : l'IA arrête de deviner, et tu découvres ce que tu veux vraiment avant d'écrire la moindre ligne.\n\nPartie 1 sur 5 : je construis un business avec l'IA, sans coder.\n👉 Abonne-toi pour la partie 2 (le cahier des charges).\n💾 Enregistre ce Reel pour retrouver le prompt.\n📎 Les 12 prompts du kit, gratuits : lien dans ma bio\n\nLuna est un personnage créé avec l'IA.\n#ia #intelligenceartificielle #chatgpt #claude #nocode #creerunsite #entrepreneur"
REELS = {"06-site-en-1-journee-luna": {"legende": LEGENDE}}


def images() -> None:
    from luna.budget import Depenses
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
            refs.append(("image[]", s["capture"]))
            texte += (" Reference images: 1 = composition and mood, 2 = the woman's "
                      "face, 3 = the exact screenshot to show on the monitor.")
        Depenses().reserver(float(os.getenv("LUNA_COUT_IMAGE_EUR", "0.07")),
                            f"image openai reel site luna {s['nom']}")
        corps, ctype = _multipart({"model": modele, "prompt": texte, "size": "1024x1536",
                                   "n": "1", "quality": "high"}, refs)
        req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=corps,
                                     method="POST", headers={"Authorization": f"Bearer {cle}",
                                                             "Content-Type": ctype})
        _journal(f"image {s['nom']}…")
        with urllib.request.urlopen(req, timeout=600) as r:
            rep = json.loads(r.read())
        cible.write_bytes(base64.b64decode(rep["data"][0]["b64_json"]))
        _journal(f"image {s['nom']} ok")


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
        b64 = base64.b64encode((DOSSIER / "images" / f"{s['nom']}.png").read_bytes()).decode()
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
            elif statut in ("failed", "error"):
                raise SystemExit(f"kling {nom} a échoué")
            else:
                restant += 1
        if not restant:
            break
        time.sleep(20)


def _clip(entree: Path, sortie: Path, debut: float, duree: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{debut:.3f}", "-i", str(entree),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                           "fps=30,tpad=stop_mode=clone:stop_duration=2",
                    "-t", f"{duree:.3f}", "-an", "-c:v", "libx264", "-crf", "17",
                    "-pix_fmt", "yuv420p", str(sortie)], check=True)


def montage() -> Path:
    tmp = DOSSIER / "montage"
    tmp.mkdir(parents=True, exist_ok=True)
    vids = DOSSIER / "videos"
    a, b = MORCEAUX_06["prompt_pages"]
    c, d = MORCEAUX_06["fin"]
    plan = [(vids / "1_site.mp4", 0.0, SCENES[0]["duree"]),
            (REEL_06, a, b - a),
            (vids / "2_code.mp4", 0.0, SCENES[1]["duree"]),
            (REEL_06, c, d - c)]
    morceaux = []
    for i, (src, debut, duree) in enumerate(plan):
        m = tmp / f"m{i}.mp4"
        _clip(src, m, debut, duree)
        morceaux.append(m)
    total = sum(p[2] for p in plan)
    liste = tmp / "liste.txt"
    liste.write_text("".join(f"file '{m}'\n" for m in morceaux))
    brut = tmp / "brut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(liste),
                    "-c", "copy", str(brut)], check=True)
    from alluxe_ia.musique import ecrire_wav
    son = tmp / "musique.wav"
    ecrire_wav(str(son), total, graine="site")
    entrees, filtres, prec = ["-i", str(brut), "-i", str(son)], [], "0:v"
    for j, (t0, t1, texte, style) in enumerate(TEXTES):
        p = tmp / f"t{j}.png"
        _calque(texte, style).save(p)
        # Une image fixe n'a qu'UNE frame : sans boucle, un calque qui commence
        # tard (11,2 s) ne s'affichait jamais. Bouclé sur toute la durée.
        entrees += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(p)]
        filtres.append(f"[{prec}][{j + 2}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[v{j}]")
        prec = f"v{j}"
    filtres.append(f"[1:a]atrim=0:{total},afade=t=out:st={total - 0.6:.2f}:d=0.6[a]")
    final = RACINE / "data/alluxe_ia/reels/06-site-en-1-journee-luna.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entrees, "-filter_complex", ";".join(filtres),
                    "-map", f"[{prec}]", "-map", "[a]", "-t", f"{total:.3f}", "-c:v", "libx264",
                    "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(final)], check=True)
    _journal(f"Reel prêt : {final} ({total:.1f} s)")
    return final


if __name__ == "__main__":
    {"images": images, "videos": videos, "montage": montage}[sys.argv[1] if len(sys.argv) > 1 else "images"]()
