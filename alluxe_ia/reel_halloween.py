"""Reels 11-13 : série HALLOWEEN, format court (13 oct. 2026).

Pourquoi ce format. Les statistiques du 13 oct. (ops/stats_reseaux.py) :
70 à 93 % des gens quittent nos Reels avant 3 s sur Instagram, 2 à 4 s
regardées sur TikTok pour des vidéos de 16 à 30 s. Les comptes qui
grandissent accrochent dès la 1re seconde. D'où, pour ces trois-là :
  - la 1re image EST l'accroche (le résultat, ou Luna qui parle déjà),
    texte de moins de 12 mots à l'écran dès l'image 0 ;
  - 8 à 11 s, une seule idée, la valeur avant la fin ;
  - musique « qui accroche fort, moins fort que la voix » (l'opérateur, 13 oct.) :
    la Danse macabre de Saint-Saëns, enregistrement de Kevin MacLeod, CC BY 4.0
    — utilisable sur Instagram, TikTok ET YouTube, à condition de créditer
    (ligne ajoutée à chaque légende). Pas de morceau commercial : sur TikTok et
    YouTube il serait muté ou revendiqué, et la bibliothèque Instagram ne
    couvre qu'Instagram.

Économie : UN seul clip Kling de Luna dans un décor d'Halloween, et trois
synchronisations des lèvres sur trois voix différentes (~2,70 € au lieu
de ~5 €). Même décor sur les trois : c'est une série, ça se reconnaît.

    python3 alluxe_ia/reel_halloween.py voix images video levres montage

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

from alluxe_ia.reel_luna_ecrans import REFERENCE_LUNA, _calque, _journal, _multipart  # noqa: E402
from alluxe_ia.reel_luna_parle import (LUNA, _duree, _plan_image, _plan_video,  # noqa: E402
                                       _texte_prompt)
from alluxe_ia.reel_luna_vlog import CONSIGNE_VOIX, VOIX_MOTEUR  # noqa: E402

DOSSIER = RACINE / "data/alluxe_ia/reel_halloween"
CLIP = 10.0
FIN_CTA = 1.4

SCENE_PARLE = (
    " She holds the phone at arm's length, framed from mid-chest up, looking straight "
    "into the lens with a playful mischievous smile, mouth slightly open as if about to "
    "speak. Cosy apartment at dusk decorated for Halloween behind her: carved glowing "
    "pumpkins, candles, warm orange fairy lights, a window with a purple evening sky. "
    "Both hands are out of the frame."
)

#: images partagées : (nom, texte, avec la photo de référence de Luna ?)
IMAGES = [
    ("vampire", "Elegant vampire portrait of the same woman: pale porcelain skin, deep red "
     "lipstick, two subtle small fangs, dark Victorian high-collar velvet dress, candlelit "
     "gothic room, cinematic lighting, same face exactly. Tasteful, not gory, fully "
     "clothed. Photorealistic.", True),
    ("sorciere", "The same woman as a beautiful witch: black pointed hat, long dark cape, "
     "standing in a misty forest at night with glowing lanterns and pumpkins, cinematic, "
     "same face exactly. Tasteful, fully clothed. Photorealistic.", True),
    ("placard", "Ordinary smartphone photo of an open bedroom wardrobe with everyday "
     "clothes: black jeans, a black turtleneck, a white shirt, a striped top, a red scarf, "
     "a hair headband on the shelf. Slightly messy, flat indoor light, no person, no text.",
     False),
    ("chat", "Mirror selfie of the same woman in a simple DIY black cat Halloween costume "
     "made from everyday clothes: black turtleneck, black jeans, cat ears made from a "
     "headband, little whiskers drawn with eyeliner. Hallway with small Halloween "
     "decorations, playful smile, same face exactly. Fully clothed. Photorealistic.",
     True),
    ("nuit", "Dark bedroom at night, seen from the bed: on the nightstand a smartphone "
     "lies face up, its screen glowing and showing a single chat bubble that reads "
     "\"Bonne nuit.\" Moonlight through the curtains, eerie quiet atmosphere, "
     "cinematic, photorealistic. No person.", False),
]

PROMPT_PHOTO = ("Transforme cette photo en portrait de vampire élégant, ambiance Halloween, "
                "lumière de bougies. Garde mon visage identique.")
PROMPT_COSTUME = ("Voici mon placard. Propose-moi 3 costumes d'Halloween faisables ce soir "
                  "avec uniquement ce que j'ai déjà.")
PROMPT_HISTOIRE = "Écris l'histoire d'horreur la plus flippante possible en deux phrases."

#: Chaque Reel : la voix (une seule prise, pour un débit naturel) et sa consigne.
REELS = {
    "11-halloween-photo": {
        "voix": "Ça, c'est moi… en vampire ! Une photo, un prompt. Envoie-le à ton pote !",
        "consigne": CONSIGNE_VOIX,
        "legende": (
            "Ta photo version Halloween avec ChatGPT 🎃🧛‍♀️\n\n"
            f"Le prompt (copie-le) :\n« {PROMPT_PHOTO} »\n\n"
            "Remplace « vampire » par sorcière, zombie, fantôme… et ajoute ta photo.\n\n"
            "👉 Envoie-le à la personne avec qui tu fêtes Halloween.\n"
            "💾 Enregistre pour le 31.\n\n"
            "Luna est un personnage créé avec l'IA.\n"
            "#halloween #chatgpt #ia #intelligenceartificielle #prompt #halloween2026 "
            "#astuceia #iafrance"),
    },
    "12-halloween-costume": {
        "voix": "Pas d'costume ? Tu prends ton placard en photo, et ChatGPT t'en trouve trois !",
        "consigne": CONSIGNE_VOIX,
        "legende": (
            "Pas de costume pour Halloween ? Ton placard suffit 🎃\n\n"
            f"Le prompt (avec la photo de ton placard) :\n« {PROMPT_COSTUME} »\n\n"
            "Résultat testé : un chat noir avec un col roulé, un jean et un serre-tête.\n\n"
            "💾 Enregistre pour le 31.\n"
            "👉 Envoie-le à celui ou celle qui s'y prend toujours au dernier moment.\n\n"
            "Luna est un personnage créé avec l'IA.\n"
            "#halloween #costumehalloween #chatgpt #ia #astuce #diy #halloween2026 #iafrance"),
    },
    "13-halloween-histoire": {
        "voix": "Écrite par une IA… « Hier soir, mon IA m'a dit bonne nuit. Je ne lui avais "
                "jamais dit que j'allais dormir. »",
        "consigne": (CONSIGNE_VOIX + " Ici, ton : « Écrite par une IA » dit vite, complice, "
                     "puis la suite chuchotée et inquiétante, sans traîner. N'ajoute AUCUN mot, "
                     "aucune didascalie, aucune introduction."),
        "legende": (
            "Histoire d'horreur en 2 phrases, écrite par une IA 👻\n\n"
            "Ton tour : écris la tienne en commentaire 👇 La plus flippante sera lue par "
            "Luna.\n\n"
            f"Le prompt pour en générer :\n« {PROMPT_HISTOIRE} »\n\n"
            "Luna est un personnage créé avec l'IA.\n"
            "#halloween #histoiredhorreur #ia #chatgpt #creepy #halloween2026 #iafrance"),
    },
}


# ------------------------------------------------------------------ voix
#: 13 oct. : coral PUIS gpt-audio « marin » refusées (« trop ordinateur », « elle va pas »).
#: Choix de l'opérateur parmi 6 essais ElevenLabs via Runway : « la 1, elle est
#: rigolote » = Ella ; puis, le même jour : « la voix 6, légèrement moins vite, elle
#: parle super vite » = Rina, ralentie par ffmpeg (atempo : même hauteur de voix).
#: Essais : data/alluxe_ia/essais_voix_runway/.
VOIX_RUNWAY = "Rina"
VITESSE = 0.9


def _dire(texte: str, consigne: str, cible: Path) -> None:
    """La voix de Luna : ElevenLabs (eleven_multilingual_v2) par l'API Runway, déjà
    payée — pas de compte de plus. `consigne` est ignorée : ElevenLabs n'en prend
    pas, le ton passe par la ponctuation du texte."""
    import urllib.error
    entetes = {"Authorization": f"Bearer {os.environ['RUNWAYML_API_SECRET']}",
               "X-Runway-Version": "2024-11-06", "Content-Type": "application/json"}

    def appel(methode: str, chemin: str, corps: dict | None = None) -> dict:
        req = urllib.request.Request("https://api.dev.runwayml.com" + chemin, method=methode,
                                     data=json.dumps(corps).encode() if corps else None,
                                     headers=entetes)
        with urllib.request.urlopen(req, timeout=60) as rep:
            return json.load(rep)

    tache = appel("POST", "/v1/text_to_speech", {
        "model": "eleven_multilingual_v2", "promptText": texte,
        "voice": {"type": "runway-preset", "presetId": VOIX_RUNWAY}})["id"]
    while True:
        r = appel("GET", f"/v1/tasks/{tache}")
        if r.get("status") == "SUCCEEDED":
            brut = cible.with_suffix(".brut.mp3")
            urllib.request.urlretrieve(r["output"][0], str(brut))
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(brut), "-af",
                            f"atempo={VITESSE}", "-b:a", "192k", str(cible)], check=True)
            brut.unlink()
            _journal(f"voix {VOIX_RUNWAY} ×{VITESSE} : {texte[:60]}")
            return
        if r.get("status") in ("FAILED", "CANCELLED"):
            raise SystemExit(f"voix Runway échouée : {r.get('failure')}")
        time.sleep(3)


def voix() -> None:
    sortie = DOSSIER / "voix"
    sortie.mkdir(parents=True, exist_ok=True)
    for id_reel, r in REELS.items():
        cible = sortie / f"{id_reel}.mp3"
        if not cible.exists():
            _dire(r["voix"], r["consigne"], cible)
        d = _duree(cible)
        _journal(f"voix {id_reel} : {d:.2f} s")
        if d > CLIP - FIN_CTA - 0.5:
            raise SystemExit(f"{id_reel} : {d:.1f} s de voix, ne tient pas dans le clip "
                             f"de {CLIP:.0f} s — raccourcir le texte")
        # La piste que Kling synchronise : la voix dès 0,1 s, du silence jusqu'au bout.
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(cible), "-af",
                        "adelay=100:all=1,apad", "-t", f"{CLIP - 0.1:.2f}", "-ar", "44100",
                        "-b:a", "160k", str(sortie / f"{id_reel}_piste.mp3")], check=True)


# ------------------------------------------------------------------ images
def _image(nom: str, texte: str, avec_ref: bool) -> None:
    from luna.budget import Depenses
    cible = DOSSIER / "images" / f"{nom}.png"
    if cible.exists():
        return
    cible.parent.mkdir(parents=True, exist_ok=True)
    Depenses().reserver(float(os.getenv("LUNA_COUT_IMAGE_EUR", "0.07")),
                        f"image openai halloween {nom}")
    modele = os.getenv("LUNA_IMAGE_MODELE_OPENAI", "gpt-image-2")
    entetes = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    if avec_ref:
        corps, ctype = _multipart({"model": modele, "prompt": texte, "size": "1024x1536",
                                   "n": "1", "quality": "high"},
                                  [("image[]", REFERENCE_LUNA)])
        url = "https://api.openai.com/v1/images/edits"
    else:
        corps, ctype = json.dumps({"model": modele, "prompt": texte, "size": "1024x1536",
                                   "n": 1, "quality": "high"}).encode(), "application/json"
        url = "https://api.openai.com/v1/images/generations"
    req = urllib.request.Request(url, data=corps, method="POST",
                                 headers={**entetes, "Content-Type": ctype})
    _journal(f"image {nom}…")
    with urllib.request.urlopen(req, timeout=600) as rep:
        donnees = json.loads(rep.read())
    cible.write_bytes(base64.b64decode(donnees["data"][0]["b64_json"]))
    _journal(f"image {nom} ok")


def images() -> None:
    base = LUNA.replace("black sweatshirt", "black knit sweater with a small orange "
                        "pumpkin brooch")
    _image("0_parle", base + SCENE_PARLE, True)
    for nom, texte, avec_ref in IMAGES:
        if avec_ref:
            texte += " The woman is EXACTLY the woman of the reference portrait."
        _image(nom, texte, avec_ref)


# ------------------------------------------------------------------ vidéo + lèvres
def _taches() -> tuple[Path, dict]:
    f = DOSSIER / "videos" / "taches.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    return f, (json.loads(f.read_text()) if f.exists() else {})


def video() -> None:
    from luna.media import KlingVideo, telecharger
    k = KlingVideo()
    cible = DOSSIER / "videos" / "parle.mp4"
    if cible.exists():
        return
    f, taches = _taches()
    if "parle" not in taches:
        b64 = base64.b64encode((DOSSIER / "images" / "0_parle.png").read_bytes()).decode()
        taches["parle"] = k.creer(
            b64,
            "Vertical selfie video. The woman talks to the camera naturally, like "
            "recording an Instagram story: small head movements, gentle nods, "
            "expressive eyebrows, natural blinking, playful smile between sentences. "
            "Candle flames flicker softly behind her. Her hands stay out of the frame "
            "the whole time. No waving, no pointing, no object entering the frame. Very "
            "slight handheld motion. Same face throughout, no morphing.",
            "9:16", int(CLIP))
        f.write_text(json.dumps(taches, indent=1))
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
    f, taches = _taches()
    src = k._appel("GET", f"/v1/videos/image2video/{taches['parle']}")
    vid = src["task_result"]["videos"][0]["id"]   # id de la VIDÉO, pas de la tâche
    for id_reel in REELS:
        cle = f"levres:{id_reel}"
        if cle not in taches:
            Depenses().reserver(0.30, f"lip-sync kling {id_reel}")
            audio = base64.b64encode(
                (DOSSIER / "voix" / f"{id_reel}_piste.mp3").read_bytes()).decode()
            rep = k._appel("POST", "/v1/videos/lip-sync", {"input": {
                "video_id": vid, "mode": "audio2video", "audio_type": "file",
                "audio_file": audio}})
            taches[cle] = rep["task_id"]
            f.write_text(json.dumps(taches, indent=1))
    for id_reel in REELS:
        cible = DOSSIER / "videos" / f"{id_reel}.mp4"
        while not cible.exists():
            r = k._appel("GET", f"/v1/videos/lip-sync/{taches[f'levres:{id_reel}']}")
            statut = r.get("task_status")
            if statut == "succeed":
                telecharger(r["task_result"]["videos"][0]["url"], str(cible))
                _journal(f"lèvres prêtes : {id_reel}")
            elif statut == "failed":
                raise MediaErreur(f"lip-sync {id_reel} échoué : {r.get('task_status_msg')}")
            else:
                time.sleep(10)


# ------------------------------------------------------------------ montage
def _plans(id_reel: str, total: float) -> tuple[list, list]:
    """(plans, calques) de chaque Reel. Un plan « clip » reprend le clip
    synchronisé AU MÊME INSTANT que dans le Reel : la voix reste sur les lèvres."""
    img = DOSSIER / "images"
    fin = total - FIN_CTA
    if id_reel == "11-halloween-photo":
        plans = [("image", img / "vampire.png", 0.0, 2.0), ("clip", None, 2.0, 1.4),
                 ("image", img / "sorciere.png", 3.4, 1.2), ("clip", None, 4.6, total - 4.6)]
        calques = [(0.0, 2.0, "MOI,\nVERSION HALLOWEEN", "titre"),
                   (3.4, 4.6, "OU EN SORCIÈRE", "rouge"),
                   (2.0, fin, ("prompt", PROMPT_PHOTO), "")]
    elif id_reel == "12-halloween-costume":
        plans = [("clip", None, 0.0, 2.0), ("image", img / "placard.png", 2.0, 2.0),
                 ("image", img / "chat.png", 4.0, fin - 4.0), ("clip", None, fin, total - fin)]
        calques = [(0.0, 2.0, "PAS DE COSTUME ?\nDEMANDE À L'IA", "titre"),
                   (2.0, 4.0, ("prompt", PROMPT_COSTUME), ""),
                   (4.0, fin, "RÉSULTAT", "rouge")]
    else:
        plans = [("clip", None, 0.0, 2.0), ("image", img / "nuit.png", 2.0, total - 2.0)]
        calques = [(0.0, 2.0, "HISTOIRE D'HORREUR\nÉCRITE PAR UNE IA", "titre"),
                   (2.0, fin, "« Hier soir, mon IA\nm'a dit bonne nuit.\n\n"
                              "Je ne lui avais jamais dit\nque j'allais dormir. »", "bas")]
    cta = "COMMENTE LA TIENNE" if id_reel == "13-halloween-histoire" else "ABONNE-TOI"
    calques += [(fin, total, cta, "cta"),
                (0.0, total, "@alluxe.ia · Luna, personnage IA", "signature")]
    return plans, calques


def _monter(id_reel: str) -> Path:
    tmp = DOSSIER / "montage" / id_reel
    tmp.mkdir(parents=True, exist_ok=True)
    clip = DOSSIER / "videos" / f"{id_reel}.mp4"
    voix_f = DOSSIER / "voix" / f"{id_reel}.mp3"
    # au moins 7 s : le plan « résultat » du 12 doit rester lisible même si la voix est courte
    total = round(min(CLIP - 0.1, max(7.0, 0.1 + _duree(voix_f) + FIN_CTA + 0.2)), 2)
    plans, calques = _plans(id_reel, total)

    morceaux = []
    for i, (genre, src, debut, d) in enumerate(plans):
        m = tmp / f"m{i}.mp4"
        (_plan_video(clip, m, debut, d) if genre == "clip" else _plan_image(src, m, d))
        morceaux.append(m)
    liste = tmp / "liste.txt"
    liste.write_text("".join(f"file '{m}'\n" for m in morceaux))
    brut = tmp / "brut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(liste), "-c", "copy", str(brut)], check=True)

    entrees = ["-i", str(brut), "-i", str(voix_f)]
    filtres = [f"[1:a]adelay=100:all=1,apad,atrim=0:{total:.3f},"
               f"afade=t=out:st={total - 0.4:.2f}:d=0.4[a]"]
    prec = "0:v"
    for j, (t0, t1, texte, style) in enumerate(calques):
        p = tmp / f"t{j}.png"
        (_texte_prompt(texte[1]) if isinstance(texte, tuple) else _calque(texte, style)).save(p)
        entrees += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(p)]
        filtres.append(f"[{prec}][{2 + j}:v]overlay=0:0:"
                       f"enable='between(t,{t0:.2f},{t1:.2f})'[v{j}]")
        prec = f"v{j}"
    final = RACINE / f"data/alluxe_ia/reels/{id_reel}.mp4"
    # Threads limités : ffmpeg tué faute de mémoire le 11 oct. (robots sur le VPS).
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-filter_complex_threads", "1", *entrees,
                    "-filter_complex", ";".join(filtres), "-threads", "2",
                    "-map", f"[{prec}]", "-map", "[a]", "-t", f"{total:.3f}",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)],
                   check=True)
    Path(f"{final}.legende.txt").write_text(REELS[id_reel]["legende"])
    _journal(f"Reel prêt : {final.name} ({total:.1f} s)")
    return final


MUSIQUE = RACINE / "data/alluxe_ia/musiques/danse_macabre_kevin_macleod.mp3"
CREDIT = ("Musique : Danse Macabre — Kevin MacLeod (incompetech.com), "
          "licence CC BY 4.0")
#: passage du morceau pour chaque Reel (s) : les plus énergiques, mesurés au RMS
PASSAGE = {"11-halloween-photo": 344.0, "12-halloween-costume": 311.0,
           "13-halloween-histoire": 290.0}


def _musique(final: Path, id_reel: str) -> None:
    """Pose la musique SOUS la voix : -26 LUFS contre une voix autour de -18, et
    elle s'efface encore quand Luna parle (sidechain). Puis UN gain fixe pour
    viser -14 LUFS, la norme des trois plateformes. Pas de loudnorm sur le
    mélange : dynamique, il remontait la musique dès que la voix s'arrêtait
    (constaté le 13 oct. : musique seule à 3 dB de la voix)."""
    import re
    tmp = final.with_name(final.stem + "-sans-musique.mp4")
    final.replace(tmp)
    total = _duree(tmp)
    melange = final.with_suffix(".melange.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp),
                    "-ss", f"{PASSAGE[id_reel]:.2f}", "-t", f"{total:.3f}", "-i", str(MUSIQUE),
                    "-filter_complex",
                    # aresample obligatoire : loudnorm sort en 192 kHz, et sans
                    # ré-échantillonnage la musique disparaissait à la fin de la voix.
                    "[0:a]aresample=44100,loudnorm=I=-18:TP=-2,aresample=44100,"
                    "asplit=2[voix][cle];"
                    f"[1:a]loudnorm=I=-26:TP=-5,aresample=44100,afade=t=in:d=0.15,"
                    f"afade=t=out:st={total - 0.6:.2f}:d=0.6[mus];"
                    "[mus][cle]sidechaincompress=threshold=0.03:ratio=3:attack=20:release=300[mus2];"
                    "[voix][mus2]amix=inputs=2:normalize=0:duration=first[a]",
                    "-map", "[a]", str(melange)], check=True)
    mesure = subprocess.run(["ffmpeg", "-i", str(melange), "-af", "ebur128", "-f", "null", "-"],
                            capture_output=True, text=True).stderr
    niveau = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", mesure)[-1])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(tmp), "-i", str(melange),
                    "-af", f"volume={-14 - niveau:.2f}dB,alimiter=limit=0.84",
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(final)],
                   check=True)
    tmp.unlink()
    melange.unlink()


def montage() -> None:
    for id_reel in REELS:
        final = _monter(id_reel)
        _musique(final, id_reel)
        Path(f"{final}.legende.txt").write_text(REELS[id_reel]["legende"] + "\n\n" + CREDIT)


if __name__ == "__main__":
    etapes = {"voix": voix, "images": images, "video": video, "levres": levres,
              "montage": montage}
    for nom in (sys.argv[1:] or list(etapes)):
        etapes[nom]()
