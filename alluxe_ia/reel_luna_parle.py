"""Reel 08 : Luna PARLE face caméra — « 3 prompts pour transformer ta photo » (11 oct. 2026).

Demande de l'opérateur, après le premier essai de lèvres synchronisées :
« les gestes sont mal synchronisés, essaie sur un Reel entier ». Le premier
essai réutilisait un clip tourné pour une autre scène (haussement d'épaules,
téléphone qui entre dans le cadre) : les gestes n'avaient rien à voir avec la
phrase. Ici le clip est tourné POUR la parole — Luna parle à la caméra, mains
hors du cadre — puis Kling cale ses lèvres sur la voix.

Sujet choisi sur les tendances du 11 oct. (data/alluxe_ia/tendances/) :
transformer ses propres photos avec ChatGPT est la plus grosse vague, sur
Instagram comme sur TikTok.

Chaîne, une étape par commande (chaque étape payée n'est jamais refaite :
les fichiers produits servent de cache) :

    python3 alluxe_ia/reel_luna_parle.py voix      # OpenAI gpt-4o-mini-tts
    python3 alluxe_ia/reel_luna_parle.py images    # gpt-image : Luna + avant + 3 transformations
    python3 alluxe_ia/reel_luna_parle.py video     # Kling 10 s, Luna parle face caméra
    python3 alluxe_ia/reel_luna_parle.py levres    # Kling lip-sync sur la voix
    python3 alluxe_ia/reel_luna_parle.py montage

Rien n'est publié par ce script.
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

from alluxe_ia.luna_tenues import avec_tenue  # noqa: E402
from alluxe_ia.reel_luna_ecrans import REFERENCE_LUNA, _calque, _journal, _multipart, _police  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

ID_REEL = "08-luna-photo-chatgpt"
DOSSIER = RACINE / "data/alluxe_ia/reel_luna_parle"
W, H = 1080, 1920

#: Le texte commun porte « black sweatshirt » : `avec_tenue` le remplace par
#: la tenue de CE Reel (jamais une des 5 dernières).
LUNA = (
    "Vertical smartphone selfie photo, ultra realistic, shot on a high-end phone in "
    "soft daylight. The young woman is EXACTLY the woman of the reference portrait: "
    "same face, platinum blonde long wavy hair with slightly darker roots, grey-green "
    "eyes, golden natural skin with real pores, one single small beauty mark above the "
    "left side of her upper lip, black sweatshirt. "
    "No text, no captions, no stickers, no watermark. Natural skin, no beauty filter."
)

SCENE_PARLE = (
    " She holds the phone at arm's length, framed from mid-chest up, looking straight "
    "into the lens with a warm complicit smile, mouth slightly open as if about to "
    "speak. Cosy small student apartment behind her, plants and a window, soft "
    "natural light. Both hands are out of the frame."
)

#: la photo « avant » : banale, comme celles qu'on poste sans réfléchir
SCENE_AVANT = (
    " Ordinary unedited casual phone photo taken by a friend: she sits at a small "
    "café terrace table in Lyon with a coffee, slightly flat light, a bit of clutter "
    "in the background, average framing. Natural, not professional."
)

#: (clé, titre à l'écran, prompt montré à l'écran et en légende, texte pour l'image)
TRANSFOS = [
    ("1_studio", "PORTRAIT STUDIO",
     "Transforme cette photo en portrait studio professionnel : fond uni, lumière "
     "douce, objectif 85 mm. Garde mon visage identique.",
     "Transform this photo into a professional studio portrait of the same woman: plain "
     "warm grey seamless backdrop, soft key light, 85 mm lens look, shallow depth of "
     "field, same clothes, same face exactly. Elegant and natural, fully clothed."),
    ("2_magazine", "COUVERTURE DE MAGAZINE",
     "Fais de cette photo la couverture d'un magazine de mode, avec un grand titre en "
     "haut. Garde mon visage identique.",
     "Turn this photo into a fashion magazine cover featuring the same woman, same face "
     "exactly, same clothes, confident pose. Big bold masthead at the top reading "
     "ALLUXE, two short cover lines in French. Clean editorial layout, fully clothed, "
     "tasteful."),
    ("3_drone", "VUE DU CIEL",
     "Montre la même scène vue d'un drone, très haut au-dessus de moi, style "
     "cinéma.",
     "Show the very same scene from a drone high above: top-down cinematic aerial "
     "shot of the café terrace and the street in Lyon, the same woman small at her "
     "table looking up and waving, golden hour light. Photorealistic."),
]

#: ce que dit Luna. Accroche et fin sont dites FACE CAMÉRA (lèvres
#: synchronisées) ; les trois du milieu en voix off sur les images.
VOIX = {
    "accroche": "Ta photo est banale ? Regarde ce que ChatGPT en fait.",
    "1_studio": "Un : le portrait studio. Tu mets ta photo, tu colles ce prompt.",
    "2_magazine": "Deux : ta propre couverture de magazine.",
    "3_drone": "Trois : la même photo… vue du ciel.",
    "fin": "Les prompts sont dans la légende. Abonne-toi !",
}
CONSIGNE_VOIX = ("Jeune femme française de 22 ans, voix naturelle et complice, souriante, "
                 "débit rapide et énergique comme une story Instagram, accent français standard.")

CLIP = 10.0          # durée du clip Kling où elle parle
DEBUT_ACCROCHE = 0.2
FIN_CTA = 2.0        # « ABONNE-TOI » sur les 2 dernières secondes (règle du 9 oct.)

LEGENDE = (
    "3 prompts pour transformer UNE photo banale avec ChatGPT 📸👇\n\n"
    + "\n\n".join(f"{i}. {titre.capitalize()} :\n« {prompt} »"
                  for i, (_, titre, prompt, _) in enumerate(TRANSFOS, 1))
    + "\n\nComment faire : ouvre ChatGPT, ajoute ta photo, colle le prompt.\n\n"
    "💾 Enregistre ce Reel pour garder les 3 prompts.\n"
    "👉 Abonne-toi : demain, 3 autres.\n"
    "📎 Les 12 prompts du kit, gratuits : lien dans ma bio\n\n"
    "Luna est un personnage créé avec l'IA.\n"
    "#chatgpt #ia #intelligenceartificielle #astuceia #photo #prompt #iafrance"
)


def _duree(fichier: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(fichier)], capture_output=True, text=True,
                       check=True)
    return float(r.stdout.strip())


# ------------------------------------------------------------------ voix
def voix() -> None:
    sortie = DOSSIER / "voix"
    sortie.mkdir(parents=True, exist_ok=True)
    cle = os.environ["OPENAI_API_KEY"]
    for nom, texte in VOIX.items():
        cible = sortie / f"{nom}.mp3"
        if cible.exists():
            continue
        corps = {"model": "gpt-4o-mini-tts", "voice": "coral", "input": texte,
                 "response_format": "mp3", "instructions": CONSIGNE_VOIX}
        req = urllib.request.Request("https://api.openai.com/v1/audio/speech",
                                     data=json.dumps(corps).encode(),
                                     headers={"Authorization": f"Bearer {cle}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            cible.write_bytes(r.read())
        _journal(f"voix {nom} : {_duree(cible):.2f} s")
    # La piste que Kling va lire : accroche au début, fin calée au bout du clip.
    acc, fin = _duree(sortie / "accroche.mp3"), _duree(sortie / "fin.mp3")
    debut_fin = CLIP - fin - 0.25
    if debut_fin < DEBUT_ACCROCHE + acc + 0.6:
        raise SystemExit(f"accroche ({acc:.1f} s) + fin ({fin:.1f} s) ne tiennent pas "
                         f"dans {CLIP:.0f} s : raccourcir le texte")
    (sortie / "calage.json").write_text(json.dumps({"debut_fin": debut_fin}))
    subprocess.run(["ffmpeg", "-v", "error", "-y",
                    "-i", str(sortie / "accroche.mp3"), "-i", str(sortie / "fin.mp3"),
                    "-filter_complex",
                    f"[0:a]adelay={int(DEBUT_ACCROCHE * 1000)}:all=1[a];"
                    f"[1:a]adelay={int(debut_fin * 1000)}:all=1[b];"
                    "[a][b]amix=inputs=2:normalize=0,apad",
                    "-t", f"{CLIP - 0.1:.2f}", "-ar", "44100", "-b:a", "160k",
                    str(sortie / "face_camera.mp3")], check=True)
    _journal(f"piste face caméra : accroche 0,2 s → {DEBUT_ACCROCHE + acc:.1f} s, "
             f"fin {debut_fin:.1f} s → {debut_fin + fin:.1f} s")


# ------------------------------------------------------------------ images
def _image(nom: str, texte: str, refs: list[tuple[str, Path]]) -> None:
    from luna.budget import Depenses
    cible = DOSSIER / "images" / f"{nom}.png"
    if cible.exists():
        return
    cible.parent.mkdir(parents=True, exist_ok=True)
    Depenses().reserver(float(os.getenv("LUNA_COUT_IMAGE_EUR", "0.07")),
                        f"image openai reel 08 {nom}")
    corps, ctype = _multipart({"model": os.getenv("LUNA_IMAGE_MODELE_OPENAI", "gpt-image-2"),
                               "prompt": texte, "size": "1024x1536", "n": "1",
                               "quality": "high"}, refs)
    req = urllib.request.Request("https://api.openai.com/v1/images/edits", data=corps,
                                 method="POST",
                                 headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                                          "Content-Type": ctype})
    _journal(f"image {nom}…")
    with urllib.request.urlopen(req, timeout=600) as r:
        rep = json.loads(r.read())
    cible.write_bytes(base64.b64decode(rep["data"][0]["b64_json"]))
    _journal(f"image {nom} ok")


def images() -> None:
    base = avec_tenue(LUNA, ID_REEL)
    _image("0_parle", base + SCENE_PARLE, [("image[]", REFERENCE_LUNA)])
    _image("0_avant", base + SCENE_AVANT, [("image[]", REFERENCE_LUNA)])
    avant = DOSSIER / "images" / "0_avant.png"
    for cle, _, _, texte in TRANSFOS:
        _image(cle, texte + " The woman is EXACTLY the woman of the reference photo.",
               [("image[]", avant)])


# ------------------------------------------------------------------ vidéo + lèvres
def video() -> None:
    from luna.media import KlingVideo, telecharger
    k = KlingVideo()
    cible = DOSSIER / "videos" / "parle.mp4"
    if cible.exists():
        return
    cible.parent.mkdir(parents=True, exist_ok=True)
    taches_f = DOSSIER / "videos" / "taches.json"
    taches = json.loads(taches_f.read_text()) if taches_f.exists() else {}
    if "parle" not in taches:
        b64 = base64.b64encode((DOSSIER / "images" / "0_parle.png").read_bytes()).decode()
        taches["parle"] = k.creer(
            b64,
            "Vertical selfie video. The woman talks to the camera naturally, like "
            "recording an Instagram story: small head movements, gentle nods, "
            "expressive eyebrows, natural blinking, warm smile between sentences. Her "
            "hands stay out of the frame the whole time. No waving, no pointing, no "
            "phone or object entering the frame. Very slight handheld motion. Same "
            "face throughout, no morphing.",
            "9:16", int(CLIP))
        taches_f.write_text(json.dumps(taches, indent=1))
    while True:
        statut, url = k.resultat(taches["parle"])
        if statut == "succeeded":
            telecharger(url, str(cible))
            _journal("kling parle prêt")
            return
        time.sleep(20)


def levres() -> None:
    from luna.budget import Depenses
    from luna.media import KlingVideo, MediaErreur, telecharger
    k = KlingVideo()
    cible = DOSSIER / "videos" / "parle_levres.mp4"
    if cible.exists():
        return
    taches_f = DOSSIER / "videos" / "taches.json"
    taches = json.loads(taches_f.read_text())
    if "levres" not in taches:
        src = k._appel("GET", f"/v1/videos/image2video/{taches['parle']}")
        vid = src["task_result"]["videos"][0]["id"]   # id de la VIDÉO, pas de la tâche
        Depenses().reserver(0.30, "lip-sync kling reel 08")
        audio = base64.b64encode((DOSSIER / "voix" / "face_camera.mp3").read_bytes()).decode()
        rep = k._appel("POST", "/v1/videos/lip-sync", {"input": {
            "video_id": vid, "mode": "audio2video", "audio_type": "file", "audio_file": audio}})
        taches["levres"] = rep["task_id"]
        taches_f.write_text(json.dumps(taches, indent=1))
    while True:
        r = k._appel("GET", f"/v1/videos/lip-sync/{taches['levres']}")
        statut = r.get("task_status")
        if statut == "succeed":
            telecharger(r["task_result"]["videos"][0]["url"], str(cible))
            _journal("lèvres prêtes")
            return
        if statut == "failed":
            raise MediaErreur(f"lip-sync échoué : {r.get('task_status_msg')}")
        time.sleep(10)


# ------------------------------------------------------------------ montage
def _texte_prompt(prompt: str) -> Image.Image:
    """Le prompt lisible en bas d'écran : c'est lui que les gens enregistrent."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    f = _police(44, 600)
    mots, lignes, ligne = f"« {prompt} »".split(), [], ""
    for m in mots:
        essai = (ligne + " " + m).strip()
        if d.textlength(essai, font=f) > W - 160:
            lignes.append(ligne)
            ligne = m
        else:
            ligne = essai
    lignes.append(ligne)
    texte = "\n".join(lignes)
    x0, y0, x1, y1 = d.multiline_textbbox((80, 1330), texte, font=f, spacing=10)
    d.rounded_rectangle((x0 - 30, y0 - 26, x1 + 30, y1 + 30), 22, fill=(18, 18, 20, 225))
    d.multiline_text((80, 1330), texte, font=f, fill="white", spacing=10)
    return im


def _plan_image(source: Path, sortie: Path, duree: float) -> None:
    """Une image fixe, en lent zoom avant, 9:16 plein cadre."""
    n = int(duree * 30)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(source),
                    "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                           f"zoompan=z='1+0.06*on/{n}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                           f":d={n}:s=1080x1920:fps=30",
                    "-t", f"{duree:.3f}", "-an", "-c:v", "libx264", "-crf", "17",
                    "-pix_fmt", "yuv420p", str(sortie)], check=True)


def _plan_video(source: Path, sortie: Path, debut: float, duree: float) -> None:
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{debut:.3f}", "-i", str(source),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,"
                           "crop=1080:1920,fps=30,tpad=stop_mode=clone:stop_duration=2",
                    "-t", f"{duree:.3f}", "-an", "-c:v", "libx264", "-crf", "17",
                    "-pix_fmt", "yuv420p", str(sortie)], check=True)


def montage() -> Path:
    tmp = DOSSIER / "montage"
    tmp.mkdir(parents=True, exist_ok=True)
    v, img = DOSSIER / "voix", DOSSIER / "images"
    parle = DOSSIER / "videos" / "parle_levres.mp4"
    debut_fin = json.loads((v / "calage.json").read_text())["debut_fin"]
    acc = _duree(v / "accroche.mp3")

    # (fichier, début source, durée, voix posée à t + décalage, calques)
    plans, voix_posees, calques, t = [], [], [], 0.0
    d_acc = DEBUT_ACCROCHE + acc + 0.35
    plans.append(("video", parle, 0.0, d_acc))
    calques.append((0.0, d_acc, "TA PHOTO\n+ CHATGPT =", "titre"))
    t = d_acc
    plans.append(("image", img / "0_avant.png", 0.0, 1.6))
    calques.append((t, t + 1.6, "AVANT", "rouge"))
    t += 1.6
    for i, (cle, titre, prompt, _) in enumerate(TRANSFOS, 1):
        d = max(_duree(v / f"{cle}.mp3") + 1.4, 4.2)
        plans.append(("image", img / f"{cle}.png", 0.0, d))
        voix_posees.append((v / f"{cle}.mp3", t + 0.2))
        calques.append((t, t + d, f"{i}  {titre}", "titre"))
        calques.append((t, t + d, ("prompt", prompt), ""))
        t += d
    # la fin face caméra : on reprend le clip un peu avant que la voix démarre
    entree_fin = debut_fin - 0.3
    d_fin = CLIP - entree_fin
    plans.append(("video", parle, entree_fin, d_fin))
    t_fin = t
    t += d_fin
    total = t
    calques.append((total - FIN_CTA, total, "ABONNE-TOI", "cta"))
    calques.append((0.0, total, "@alluxe.ia · Luna, personnage IA", "signature"))

    morceaux = []
    for i, (genre, src, debut, d) in enumerate(plans):
        m = tmp / f"m{i}.mp4"
        (_plan_video(src, m, debut, d) if genre == "video" else _plan_image(src, m, d))
        morceaux.append(m)
    liste = tmp / "liste.txt"
    liste.write_text("".join(f"file '{m}'\n" for m in morceaux))
    brut = tmp / "brut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(liste), "-c", "copy", str(brut)], check=True)

    # Le son : la piste face caméra telle que Kling l'a synchronisée (accroche
    # et fin), les trois voix off, et une musique douce dessous.
    from alluxe_ia.musique import ecrire_wav
    musique = tmp / "musique.wav"
    ecrire_wav(str(musique), total, graine=ID_REEL)
    face = v / "face_camera.mp3"
    entrees = ["-i", str(brut), "-i", str(musique),
               "-i", str(face), "-i", str(face)]
    filtres = [
        "[1:a]volume=0.10[mus]",
        # accroche : 0 → d_acc, au même instant que dans le clip
        f"[2:a]atrim=0:{d_acc:.3f},asetpts=PTS-STARTPTS[acc]",
        # fin : reprise à entree_fin dans le clip, posée à t_fin dans le Reel
        f"[3:a]atrim={entree_fin:.3f},asetpts=PTS-STARTPTS,"
        f"adelay={int(t_fin * 1000)}:all=1[fin]",
    ]
    noms = ["[mus]", "[acc]", "[fin]"]
    for j, (fichier, quand) in enumerate(voix_posees):
        entrees += ["-i", str(fichier)]
        filtres.append(f"[{4 + j}:a]adelay={int(quand * 1000)}:all=1[o{j}]")
        noms.append(f"[o{j}]")
    filtres.append(f"{''.join(noms)}amix=inputs={len(noms)}:normalize=0,"
                   f"atrim=0:{total:.3f},afade=t=out:st={total - 0.5:.2f}:d=0.5[a]")

    base_calques = len(entrees) // 2
    prec = "0:v"
    for j, (t0, t1, texte, style) in enumerate(calques):
        p = tmp / f"t{j}.png"
        (_texte_prompt(texte[1]) if isinstance(texte, tuple) else _calque(texte, style)).save(p)
        entrees += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(p)]
        filtres.append(f"[{prec}][{base_calques + j}:v]overlay=0:0:"
                       f"enable='between(t,{t0:.2f},{t1:.2f})'[v{j}]")
        prec = f"v{j}"
    final = RACINE / f"data/alluxe_ia/reels/{ID_REEL}.mp4"
    # Threads limités : sans ça, ffmpeg a été tué faute de mémoire (11 oct.,
    # code 137) à côté des robots de trading qui tournent sur le VPS.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-filter_complex_threads", "1",
                    *entrees,
                    "-filter_complex", ";".join(filtres), "-threads", "2",
                    "-map", f"[{prec}]", "-map", "[a]", "-t", f"{total:.3f}",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)],
                   check=True)
    (DOSSIER / "legende.txt").write_text(LEGENDE)
    _journal(f"Reel prêt : {final} ({total:.1f} s)")
    return final


if __name__ == "__main__":
    etapes = {"voix": voix, "images": images, "video": video, "levres": levres,
              "montage": montage}
    for nom in (sys.argv[1:] or list(etapes)):
        etapes[nom]()
