"""Reel 10 : Luna en VLOG, sans parler — « une boutique de Noël en une nuit » (12 oct. 2026).

L'opérateur, après le Reel 09 : « la voix sonne ordinateur, pas réelle, et je n'aime pas
trop ce style 3 photos, essaie autre chose ». D'où un format sans voix : une histoire
racontée en texte à l'écran (POV / vlog), deux plans Kling de Luna, et le VRAI site
alluxe.fr/apercu/noel qui défile (capture du navigateur, gratuite). 73 % des top vidéos
de la niche utilisent le son original ; ici la musique est composée et intégrée (TikTok),
Instagram peut poser un son tendance par-dessus à la publication.

    python3 alluxe_ia/reel_luna_vlog.py images video montage

Rien n'est publié par ce script.
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from alluxe_ia import reel_luna_parle as r  # noqa: E402  (images, plans, journal)
from alluxe_ia.reel_luna_ecrans import _calque, _journal  # noqa: E402

ID_REEL = "10-luna-boutique-en-une-nuit"
r.ID_REEL = ID_REEL
r.DOSSIER = DOSSIER = RACINE / "data/alluxe_ia/reel_luna_vlog"
ECRAN = DOSSIER / "ecran" / "site.png"          # capture 1080 px de large de la boutique
FIN_CTA = 2.0

SCENES = {
    "nuit": (" Night scene in her small cosy Lyon apartment: she sits at a desk in front of an "
             "open laptop, warm Christmas fairy lights on the wall behind her, a mug of tea. She "
             "looks up at the camera with a mischievous, excited smile, as if she just had a "
             "crazy idea. Vertical phone photo, natural.",
             "Vertical handheld video at night. The woman looks at the camera with an excited, "
             "mischievous smile, then turns back to her laptop and starts typing quickly. Fairy "
             "lights twinkle softly. Natural small movements. Same face throughout."),
    "matin": (" Morning in the same apartment, soft daylight through the window, she is in "
              "pyjamas with a big mug of coffee, standing next to the desk with the open laptop, "
              "looking proud and amazed, tired eyes but a big smile. Vertical phone photo.",
              "Vertical handheld video, morning light. The woman takes a sip of coffee, looks at "
              "the laptop screen, then back at the camera with a proud, amazed smile and a small "
              "shrug as if to say 'I did it'. Same face throughout, no morphing."),
}

#: (début y, fin y) dans la capture du site, en px — repérés sur la capture du 12 oct.
SITE = {"tete": (0, 250), "avant_apres": (2390, 2420), "produits": (8200, 12000)}

#: la trame : (plan, durée, texte à l'écran, style du texte). Pas d'emoji à l'écran :
#: la police des calques ne les a pas (carrés vides au rendu du 12 oct.).
TRAME = [
    ("nuit", 4.0, "23h. Je n'ai jamais codé.\nJe lance une boutique\nde Noël.", "titre"),
    ("tete", 4.5, "J'ai TOUT demandé\nà une IA.", "titre"),
    ("avant_apres", 5.5, "Une photo au téléphone…\n→ un portrait de Noël.", "titre"),
    ("produits", 8.0, "Affiches, toiles, mugs,\npyjamas, papier cadeau…", "titre"),
    ("matin", 5.0, "8h. La boutique est en ligne.\nEn une nuit.", "titre"),
]

LEGENDE = (
    "J'ai construit une boutique de Noël entière avec l'IA. En une nuit. Sans savoir coder. 🎄\n\n"
    "Le principe : tu envoies une photo de ta famille, de ton couple ou de tes enfants, "
    "et l'IA en fait un portrait de Noël imprimé sur une affiche, une toile, un mug ou des cartes.\n\n"
    "💬 Commente NOËL et je t'explique comment je l'ai fait.\n"
    "👉 Abonne-toi : je montre tout, étape par étape.\n\n"
    "Luna est un personnage créé avec l'IA.\n"
    "#noel #ia #intelligenceartificielle #cadeaudenoel #chatgpt #entrepreneur #iafrance"
)


def images() -> None:
    base = r.avec_tenue(r.LUNA, ID_REEL)
    for nom, (scene, _) in SCENES.items():
        r._image(nom, base + scene, [("image[]", r.REFERENCE_LUNA)])


def video() -> None:
    from luna.media import KlingVideo, telecharger
    k = KlingVideo()
    dossier = DOSSIER / "videos"
    dossier.mkdir(parents=True, exist_ok=True)
    taches_f = dossier / "taches.json"
    taches = json.loads(taches_f.read_text()) if taches_f.exists() else {}
    for nom, (_, mouvement) in SCENES.items():
        if (dossier / f"{nom}.mp4").exists():
            continue
        if nom not in taches:
            b64 = base64.b64encode((DOSSIER / "images" / f"{nom}.png").read_bytes()).decode()
            taches[nom] = k.creer(b64, mouvement, "9:16", 5)
            taches_f.write_text(json.dumps(taches, indent=1))
    for nom in SCENES:
        cible = dossier / f"{nom}.mp4"
        while not cible.exists():
            statut, url = k.resultat(taches[nom])
            if statut == "succeeded":
                telecharger(url, str(cible))
                _journal(f"kling {nom} prêt")
            else:
                time.sleep(20)


def _plan_site(sortie: Path, y0: int, y1: int, duree: float) -> None:
    """Le site qui défile : fenêtre 1080×1920 qui glisse de y0 à y1 dans la capture."""
    n = int(duree * 30)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(ECRAN),
                    "-vf", f"crop=1080:1920:0:'{y0}+({y1}-{y0})*min(n/{n},1)',fps=30",
                    "-frames:v", str(n), "-an", "-c:v", "libx264", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(sortie)], check=True)


def montage() -> Path:
    tmp = DOSSIER / "montage"
    tmp.mkdir(parents=True, exist_ok=True)
    morceaux, calques, t = [], [], 0.0
    for i, (plan, d, texte, style) in enumerate(TRAME):
        m = tmp / f"m{i}.mp4"
        if plan in SCENES:
            r._plan_video(DOSSIER / "videos" / f"{plan}.mp4", m, 0.0, d)
        else:
            _plan_site(m, *SITE[plan], d)
        morceaux.append(m)
        calques.append((t, t + d, texte, style))
        t += d
    # fin : le plan du matin repris, « commente NOËL » puis « ABONNE-TOI » (règle du 9 oct.)
    fin = tmp / "fin.mp4"
    r._plan_video(DOSSIER / "videos" / "matin.mp4", fin, 2.0, 3.5)
    morceaux.append(fin)
    calques.append((t, t + 1.5, "Commente NOËL\net je t'explique tout", "titre"))
    t += 3.5
    total = t
    calques.append((total - FIN_CTA, total, "ABONNE-TOI", "cta"))
    calques.append((0.0, total, "@alluxe.ia · Luna, personnage IA", "signature"))

    liste = tmp / "liste.txt"
    liste.write_text("".join(f"file '{m}'\n" for m in morceaux))
    brut = tmp / "brut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(liste),
                    "-c", "copy", str(brut)], check=True)
    from alluxe_ia.musique import ecrire_wav
    musique = tmp / "musique.wav"
    ecrire_wav(str(musique), total, graine=ID_REEL)

    entrees = ["-i", str(brut), "-i", str(musique)]
    filtres = [f"[1:a]volume=0.55,atrim=0:{total:.3f},afade=t=out:st={total - 1:.2f}:d=1[a]"]
    prec = "0:v"
    for j, (t0, t1, texte, style) in enumerate(calques):
        p = tmp / f"t{j}.png"
        _calque(texte, style).save(p)
        entrees += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(p)]
        filtres.append(f"[{prec}][{2 + j}:v]overlay=0:0:enable='between(t,{t0:.2f},{t1:.2f})'[v{j}]")
        prec = f"v{j}"
    final = RACINE / f"data/alluxe_ia/reels/{ID_REEL}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-filter_complex_threads", "1", *entrees,
                    "-filter_complex", ";".join(filtres), "-threads", "2",
                    "-map", f"[{prec}]", "-map", "[a]", "-t", f"{total:.3f}",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)], check=True)
    (DOSSIER / "legende.txt").write_text(LEGENDE)
    _journal(f"Reel prêt : {final} ({total:.1f} s)")
    return final


if __name__ == "__main__":
    etapes = {"images": images, "video": video, "montage": montage}
    for nom in (sys.argv[1:] or list(etapes)):
        etapes[nom]()
