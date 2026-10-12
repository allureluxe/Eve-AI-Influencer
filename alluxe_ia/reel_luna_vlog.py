"""Reel 10 : Luna en VLOG, sans parler — « une boutique de Noël en une nuit » (12 oct. 2026).

L'opérateur, après le Reel 09 : « la voix sonne ordinateur, pas réelle, et je n'aime pas
trop ce style 3 photos, essaie autre chose ». D'où un format sans voix : une histoire
racontée en texte à l'écran (POV / vlog), deux plans Kling de Luna, et le VRAI site
alluxe.fr/apercu/noel qui défile (capture du navigateur, gratuite). 73 % des top vidéos
de la niche utilisent le son original ; ici la musique est composée et intégrée (TikTok),
Instagram peut poser un son tendance par-dessus à la publication.

    python3 alluxe_ia/reel_luna_vlog.py images video voix levres montage

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
#: ABONNE-TOI sur les dernières secondes. 1,2 s ici (et non 2) : la fin ne dure que 2,5 s
#: (brief du 12 oct.) et « Commente NOËL » doit rester lisible avant — il est prioritaire.
FIN_CTA = 1.2
#: Une réplique tient dans SON plan (moins 0,1 s), accélération maximale tolérée.
#: Le brief disait « 2,5 s par réplique » ; la phrase des produits (12 mots) demande 4,4 s
#: même sans silences, x1,78 pour 2,5 s : voix de dessin animé. Elle prend donc ses 4 s de plan.
MARGE_PLAN = 0.1
ACCELERATION_MAX = 1.3

SCENES = {
    # 12 oct., v6 — l'opérateur : « commence par Luna, pas par une image : Luna qui parle
    # directement et montre le site sur un iPad ». Clip tourné POUR la parole, lèvres
    # synchronisées ensuite sur la 1re réplique (levres()). L'écran porte le VRAI
    # avant/après de la boutique (ecran/avant_apres.png, donné en référence).
    "ipad": (" Morning in her cosy Lyon living room, soft daylight, a decorated Christmas tree "
             "behind her. She stands facing the camera and holds an iPad with both hands at chest "
             "height, its screen turned towards the camera. The iPad screen shows EXACTLY the second "
             "reference image (a split before/after photo: a man and a girl on the left, the same "
             "family in Christmas sweaters in front of a Christmas tree on the right). She looks "
             "straight into the camera, mouth slightly open as if starting to speak, excited smile. "
             "Vertical phone photo, natural.",
             "Vertical handheld video. The woman talks to the camera with excitement, like an "
             "Instagram story, holding the iPad steady with both hands at chest height, screen "
             "facing the camera; small head movements, expressive eyebrows, natural blinking. The "
             "iPad and its screen stay still and unchanged. No pointing, no other object. Same "
             "face throughout, no morphing."),
    "nuit": (" Night scene in her small cosy Lyon apartment: she sits at a desk in front of an "
             "open laptop, warm Christmas fairy lights on the wall behind her, a mug of tea. She "
             "looks up at the camera with a mischievous, excited smile, as if she just had a "
             "crazy idea. Vertical phone photo, natural.",
             "Vertical handheld video at night. The woman looks at the camera with an excited, "
             "mischievous smile, then turns back to her laptop and starts typing quickly. Fairy "
             "lights twinkle softly. Natural small movements. Same face throughout."),
    "matin": (" Morning in the same apartment, soft daylight through the window, a small "
              "decorated Christmas tree in the background, she holds a big mug of coffee, standing next to the desk with the open laptop, "
              "looking proud and amazed, tired eyes but a big smile. Vertical phone photo.",
              "Vertical handheld video, morning light. The woman takes a sip of coffee, looks at "
              "the laptop screen, then back at the camera with a proud, amazed smile and a small "
              "shrug as if to say 'I did it'. Same face throughout, no morphing."),
}

#: (début y, fin y) dans la capture du site, en px — repérés sur la capture du 12 oct.
SITE = {"tete": (0, 250), "avant_apres": (2390, 2420), "produits": (8200, 12000)}
#: décalage vertical du texte, par plan : sur « ipad » il couvrait les yeux de Luna,
#: il passe sous l'iPad (le visage doit rester visible, c'est elle qui parle).
DECALAGE_TEXTE = {"ipad": 1200}
#: bande du haut recouverte de la couleur du fond, par plan : le titre du site
#: (« Une photo prise au téléphone suffit ») se mêlait au texte de la 1re image.
MASQUE = {"avant_apres": (270, "0x9b141a")}

#: la trame : (plan, durée VISÉE, texte à l'écran, style du texte). Pas d'emoji à l'écran :
#: la police des calques ne les a pas (carrés vides au rendu du 12 oct.).
#: 12 oct., 3e version, sur les stats réelles (autre session) : sur TikTok on regarde 1,6 à
#: 3,8 s en moyenne et 10-27 % restent à 3 s. Donc le RÉSULTAT d'abord (avant/après dès la
#: 1re image), le plan « tete » retiré, 15-17 s visés. Un plan s'allonge si sa réplique
#: est plus longue que sa durée visée (calage dans voix()).
TRAME = [
    ("ipad", 1.8, "Boutique créée en 1 nuit.\nSans savoir coder.", "titre"),
    # 12 oct., v7 — l'opérateur : « montre l'image normale et, comme un scanner qui passe
    # dessus, fais découvrir la nouvelle image générée ». Coupe sur la pause après
    # « …prise au téléphone, » (1,7-1,9 s) : le scanner passe sur « et l'IA en fait ça ».
    ("scanner", 2.0, "", "titre"),
    ("nuit", 2.5, "23h. Je n'ai jamais codé.", "titre"),
    ("produits", 4.0, "Affiches, toiles, mugs,\npyjamas, papier cadeau…", "titre"),
    ("matin", 3.0, "8h. La boutique est en ligne.", "titre"),
]

#: Voix OFF de Luna, dès 0,0 s. VOIX_PLAN : le plan (index dans TRAME, + la fin) où démarre
#: chaque réplique ; elle a jusqu'au début de la suivante (la 1re couvre iPad + scanner).
VOIX_OFF = [
    "Regarde… une photo prise au téléphone, et l'IA en fait ça.",
    "Hier soir, j'sais pas coder… alors j'ai tout demandé à l'IA.",
    "Affiches, toiles, mugs, pyjamas… même du papier cadeau avec vos têtes.",
    "Huit heures du mat'… la boutique est en ligne.",
    "Commente Noël, j'te raconte tout.",
]
#: 12 oct. : « une voix plus jeune et réaliste, encore une voix d'ordinateur sans émotion
#: ni accent ». On passe de gpt-4o-mini-tts (lecture) à gpt-audio-1.5 (voix de conversation,
#: bien plus expressive). Essais comparés : data/alluxe_ia/reel_luna_vlog/essais_voix/.
VOIX_MOTEUR = ("gpt-audio-1.5", "marin")
CONSIGNE_VOIX = (
    "Tu es Luna, 20 ans, une jeune Française de Lyon qui fait des vidéos TikTok. Voix JEUNE, pétillante, "
    "très expressive et sincère : tu es surexcitée de montrer à ta meilleure copine un truc incroyable, "
    "tu souris en parlant, petit rire dans la voix, intonations qui montent et descendent, vraies respirations, "
    "DÉBIT RAPIDE de TikTok : tu enchaînes les mots sans longues pauses. Accent français de France, naturel, français parlé de tous les jours. "
    "Jamais monotone, jamais voix de pub.")
VOIX_PLAN = [0, 2, 3, 4, 5]
#: plafond imposé à une réplique : la 1re garde 2,9 s, la vitesse sur laquelle Kling a
#: synchronisé les lèvres du plan iPad (videos/ipad_levres.mp4). La changer = les refaire.
PLAFOND_FIXE = {0: 2.9}
FIN = 2.5          # dernier plan : « commente NOËL » dit, puis ABONNE-TOI sur les FIN_CTA dernières s

LEGENDE = (
    "Boutique de Noël créée avec l'IA en une nuit, sans coder 🎄\n\n"
    "Le principe : tu envoies une photo de ta famille, de ton couple ou de tes enfants, "
    "et l'IA en fait un portrait de Noël imprimé sur une affiche, une toile, un mug ou des cartes.\n\n"
    "💬 Commente NOËL et je t'explique comment je l'ai fait.\n"
    "👉 Abonne-toi : je montre tout, étape par étape.\n\n"
    "Luna est un personnage créé avec l'IA.\n"
    "#noel #ia #intelligenceartificielle #cadeaudenoel #cadeaupersonnalise #portraitdenoel "
    "#chatgpt #entrepreneur #iafrance"
)


#: 12 oct. : l'opérateur — « à la fin avec son café, habille-la un peu mieux, un pyjama
#: plus chic ». Le plan du matin a SA tenue (elle s'est changée pour la nuit) ; ample et
#: boutonné, voir la mise en garde de `luna_tenues` sur les tenues moulantes.
TENUE_SCENE = {
    "ipad": "elegant loose deep burgundy silk-satin pyjama set: long-sleeved button-up shirt "
            "with a notched collar and thin cream piping, buttoned up to the collar, matching "
            "wide-leg trousers; chic, cosy, Christmas-morning look",
    "matin": "elegant loose deep burgundy silk-satin pyjama set: long-sleeved button-up shirt "
             "with a notched collar and thin cream piping, buttoned up to the collar, matching "
             "wide-leg trousers; chic, cosy, Christmas-morning look",
}


def images() -> None:
    base = r.avec_tenue(r.LUNA, ID_REEL)
    for nom, (scene, _) in SCENES.items():
        texte = r.LUNA.replace("black sweatshirt", TENUE_SCENE[nom]) if nom in TENUE_SCENE else base
        refs = [("image[]", r.REFERENCE_LUNA)]
        if nom == "ipad":
            refs.append(("image[]", DOSSIER / "ecran" / "avant_apres.png"))
        r._image(nom, texte + scene, refs)


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


def _dire(texte: str, cible: Path) -> None:
    import base64
    import urllib.request
    modele, voix_ = VOIX_MOTEUR
    entete = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}", "Content-Type": "application/json"}
    if modele.startswith("gpt-audio"):
        corps = {"model": modele, "modalities": ["text", "audio"], "audio": {"voice": voix_, "format": "mp3"},
                 "messages": [{"role": "system", "content": CONSIGNE_VOIX + " Tu es comédienne voix off : tu lis "
                               "EXACTEMENT le texte donné, mot pour mot, sans rien ajouter ni répondre."},
                              {"role": "user", "content": "Lis ce texte :\n" + texte}]}
        req = urllib.request.Request("https://api.openai.com/v1/chat/completions",
                                     data=json.dumps(corps).encode(), headers=entete)
        with urllib.request.urlopen(req, timeout=120) as rep:
            audio = json.load(rep)["choices"][0]["message"]["audio"]
        cible.write_bytes(base64.b64decode(audio["data"]))
        _journal(f"voix lue : {audio.get('transcript', '')[:80]}")
    else:
        corps = {"model": modele, "voice": voix_, "input": texte, "response_format": "mp3",
                 "instructions": CONSIGNE_VOIX}
        req = urllib.request.Request("https://api.openai.com/v1/audio/speech",
                                     data=json.dumps(corps).encode(), headers=entete)
        with urllib.request.urlopen(req, timeout=120) as rep:
            cible.write_bytes(rep.read())


def voix() -> None:
    """Une réplique par fichier, puis une piste unique ; la durée de chaque plan en découle."""
    from alluxe_ia.reel_luna_parle import _duree
    dossier = DOSSIER / "voix"
    dossier.mkdir(parents=True, exist_ok=True)
    marque = "-".join(VOIX_MOTEUR)
    for i, texte in enumerate(VOIX_OFF):
        cible = dossier / f"{i}-{marque}.mp3"
        if not cible.exists():
            _dire(texte, cible)
        _journal(f"voix {i} : {_duree(cible):.2f} s")
    # Resserrage : silences de plus de 0,12 s ramenés à 0,08 s, puis accélération douce
    # si la réplique dépasse son plan. Les plans gardent les durées du brief.
    durees = [d for _, d, _, _ in TRAME] + [FIN]
    total = sum(durees)
    departs = [sum(durees[:k]) for k in range(len(durees))]
    debuts = [departs[p] for p in VOIX_PLAN]
    nettes = []
    for i in range(len(VOIX_OFF)):
        suivant = debuts[i + 1] if i + 1 < len(debuts) else total
        plafond = PLAFOND_FIXE.get(i, suivant - debuts[i] - MARGE_PLAN)
        brut, net = dossier / f"{i}-{marque}.mp3", dossier / f"{i}-{marque}-net.wav"
        coupe = ("silenceremove=start_periods=1:start_threshold=-40dB:stop_periods=-1:"
                 "stop_duration=0.12:stop_threshold=-40dB:stop_silence=0.08")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(brut), "-af", coupe, str(net)], check=True)
        l = _duree(net)
        if l > plafond:
            tempo = l / plafond
            if tempo > ACCELERATION_MAX:
                raise SystemExit(f"réplique {i} : {l:.2f} s après coupe, il faudrait x{tempo:.2f} : raccourcir le texte")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(brut), "-af", f"{coupe},atempo={tempo:.3f}",
                            str(net)], check=True)
            _journal(f"voix {i} : {l:.2f} s -> x{tempo:.2f}")
        nettes.append(net)
        _journal(f"voix {i} nette : {_duree(net):.2f} s")
    entrees = sum((["-i", str(n)] for n in nettes), [])
    f = ";".join(f"[{i}:a]adelay={int(d * 1000)}:all=1[v{i}]" for i, d in enumerate(debuts))
    f += ";" + "".join(f"[v{i}]" for i in range(len(debuts))) + f"amix=inputs={len(debuts)}:normalize=0,"
    # « dans la pièce » : on coupe le très grave et le très aigu, petite réverbération de chambre
    f += "highpass=f=90,lowpass=f=10500,aecho=0.85:0.6:28|47:0.10|0.06,apad"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entrees, "-filter_complex", f, "-t", f"{total:.3f}",
                    "-ar", "44100", "-ac", "2", str(dossier / "off.wav")], check=True)
    (dossier / "calage.json").write_text(json.dumps({"durees": durees, "debuts": debuts}))
    _journal("plans : " + ", ".join(f"{d:.1f}" for d in durees) + f" → {total:.1f} s")


def levres() -> None:
    """Kling lip-sync du plan « ipad » sur la 1re réplique (même audio que le mixage final)."""
    from luna.budget import Depenses
    from luna.media import KlingVideo, MediaErreur, telecharger
    k = KlingVideo()
    cible = DOSSIER / "videos" / "ipad_levres.mp4"
    if cible.exists():
        return
    taches_f = DOSSIER / "videos" / "taches.json"
    taches = json.loads(taches_f.read_text())
    if "ipad_levres" not in taches:
        src = k._appel("GET", f"/v1/videos/image2video/{taches['ipad']}")
        vid = src["task_result"]["videos"][0]["id"]   # id de la VIDÉO, pas de la tâche
        replique = DOSSIER / "voix" / f"0-{'-'.join(VOIX_MOTEUR)}-net.wav"
        mp3 = DOSSIER / "voix" / "ipad_levres.mp3"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(replique), "-ar", "44100",
                        "-b:a", "160k", str(mp3)], check=True)
        Depenses().reserver(0.30, "lip-sync kling reel 10")
        rep = k._appel("POST", "/v1/videos/lip-sync", {"input": {
            "video_id": vid, "mode": "audio2video", "audio_type": "file",
            "audio_file": base64.b64encode(mp3.read_bytes()).decode()}})
        taches["ipad_levres"] = rep["task_id"]
        taches_f.write_text(json.dumps(taches, indent=1))
    while True:
        rep = k._appel("GET", f"/v1/videos/lip-sync/{taches['ipad_levres']}")
        statut = rep.get("task_status")
        if statut == "succeed":
            telecharger(rep["task_result"]["videos"][0]["url"], str(cible))
            _journal("lèvres ipad prêtes")
            return
        if statut == "failed":
            raise MediaErreur(f"lip-sync échoué : {rep.get('task_status_msg')}")
        time.sleep(10)


def _plan_scanner(sortie: Path, duree: float) -> None:
    """La photo de famille au téléphone, puis une ligne de scanner qui descend et révèle le
    portrait de Noël généré (les deux images de la boutique : docs/kit/noel/)."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    from alluxe_ia.reel_luna_ecrans import _police
    W, H, C, fps = 1080, 1920, 960, 30
    avant = np.asarray(Image.open(RACINE / "docs/kit/noel/avant-famille.jpg").convert("RGB").resize((C, C)), float)
    apres_img = Image.open(RACINE / "docs/kit/noel/apres-famille.jpg").convert("RGB")
    x0, y0 = (W - C) // 2, (H - C) // 2 - 20
    # fond : dégradé rouge nuit -> rouge, quelques flocons
    fond = Image.new("RGB", (W, H))
    yy = np.linspace(0, 1, H)[:, None, None]
    fond = np.broadcast_to((1 - yy) * np.array([110, 15, 18]) + yy * np.array([163, 21, 27]), (H, W, 3)).copy()
    rng = np.random.default_rng(10)
    for _ in range(90):
        x, y, rr = rng.integers(0, W), rng.integers(0, H), rng.integers(2, 5)
        fond[max(0, y - rr):y + rr, max(0, x - rr):x + rr] = fond[max(0, y - rr):y + rr, max(0, x - rr):x + rr] * 0.5 + 127
    masque = Image.new("L", (C, C), 0)
    ImageDraw.Draw(masque).rounded_rectangle((0, 0, C - 1, C - 1), 36, fill=255)
    masque = np.asarray(masque, float)[:, :, None] / 255
    police = _police(54, 800)

    def etiquette(im: Image.Image, texte: str) -> None:
        d = ImageDraw.Draw(im)
        b = d.textbbox((W // 2, y0 - 40), texte, font=police, anchor="mb")
        d.rounded_rectangle((b[0] - 28, b[1] - 16, b[2] + 28, b[3] + 18), 30, fill=(255, 250, 243))
        d.text((W // 2, y0 - 40), texte, font=police, fill=(163, 21, 27), anchor="mb")

    debut, balayage = 0.1, 0.85                    # le scanner passe pendant « et l'IA en fait ça »
    n = int(duree * fps)
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-an", "-c:v", "libx264",
                             "-crf", "18", "-pix_fmt", "yuv420p", str(sortie)], stdin=subprocess.PIPE)
    for k in range(n):
        t = k / fps
        a = min(1.0, max(0.0, (t - debut) / balayage))
        a = a * a * (3 - 2 * a)                    # départ et arrivée en douceur
        ligne = int(a * C)
        zoom = 1 + 0.04 * max(0.0, (t - debut - balayage) / max(0.01, duree - debut - balayage))
        cz = int(C * zoom)
        apres = np.asarray(apres_img.resize((cz, cz)), float)
        o = (cz - C) // 2
        apres = apres[o:o + C, o:o + C]
        carte = avant.copy()
        carte[:ligne] = apres[:ligne]
        if 0 < ligne < C:                          # lueur dorée sous la ligne + trait blanc
            h = min(90, ligne)
            lueur = np.linspace(0, 1, h)[:, None, None] ** 2
            carte[ligne - h:ligne] = carte[ligne - h:ligne] * (1 - 0.55 * lueur) + 0.55 * lueur * np.array([255, 214, 120])
            carte[max(0, ligne - 4):ligne + 4] = [255, 255, 245]
        image = fond.copy()
        zone = image[y0:y0 + C, x0:x0 + C]
        image[y0:y0 + C, x0:x0 + C] = zone * (1 - masque) + carte * masque
        im = Image.fromarray(image.clip(0, 255).astype("uint8"))
        ImageDraw.Draw(im).rounded_rectangle((x0 - 8, y0 - 8, x0 + C + 8, y0 + C + 8), 42,
                                             outline=(216, 169, 69), width=8)
        etiquette(im, "Ta photo au téléphone" if a < 0.5 else "Ton portrait de Noël par l'IA")
        proc.stdin.write(im.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError("ffmpeg scanner")


def _plan_site(sortie: Path, y0: int, y1: int, duree: float, masque: tuple | None = None) -> None:
    """Le site qui défile : fenêtre 1080×1920 qui glisse de y0 à y1 dans la capture."""
    n = int(duree * 30)
    cache = f",drawbox=x=0:y=0:w=1080:h={masque[0]}:color={masque[1]}:t=fill" if masque else ""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(ECRAN),
                    "-vf", f"crop=1080:1920:0:'{y0}+({y1}-{y0})*min(n/{n},1)',fps=30{cache}",
                    "-frames:v", str(n), "-an", "-c:v", "libx264", "-crf", "18",
                    "-pix_fmt", "yuv420p", str(sortie)], check=True)


def montage() -> Path:
    tmp = DOSSIER / "montage"
    tmp.mkdir(parents=True, exist_ok=True)
    durees = json.loads((DOSSIER / "voix" / "calage.json").read_text())["durees"]
    morceaux, calques, t = [], [], 0.0
    for i, ((plan, _, texte, style), d) in enumerate(zip(TRAME, durees)):
        m = tmp / f"m{i}.mp4"
        if plan in SCENES:
            levres_ = DOSSIER / "videos" / f"{plan}_levres.mp4"
            r._plan_video(levres_ if levres_.exists() else DOSSIER / "videos" / f"{plan}.mp4", m, 0.0, d)
        elif plan == "scanner":
            _plan_scanner(m, d)
        else:
            _plan_site(m, *SITE[plan], d, MASQUE.get(plan))
        morceaux.append(m)
        if texte:
            calques.append((t, t + d, texte, style, DECALAGE_TEXTE.get(plan, 0)))
        t += d
    # fin : le plan du matin repris, « commente NOËL » puis « ABONNE-TOI » (règle du 9 oct.)
    fin = tmp / "fin.mp4"
    d_fin = durees[-1]
    r._plan_video(DOSSIER / "videos" / "matin.mp4", fin, 1.5, d_fin)
    morceaux.append(fin)
    total = t + d_fin
    calques.append((t, total - FIN_CTA, "Commente NOËL\net je t'explique tout", "titre", 0))
    calques.append((total - FIN_CTA, total, "ABONNE-TOI", "cta", 0))
    calques.append((0.0, total, "@alluxe.ia · Luna, personnage IA", "signature", 0))

    liste = tmp / "liste.txt"
    liste.write_text("".join(f"file '{m}'\n" for m in morceaux))
    brut = tmp / "brut.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(liste),
                    "-c", "copy", str(brut)], check=True)
    from alluxe_ia.musique import ecrire_wav
    musique = tmp / "musique.wav"
    ecrire_wav(str(musique), total, graine=ID_REEL, style="noel")
    off = DOSSIER / "voix" / "off.wav"

    entrees = ["-i", str(brut), "-i", str(musique), "-i", str(off)]
    # la musique s'efface sous la voix (compression déclenchée par la voix), puis on mélange
    filtres = [f"[2:a]asplit=2[vx][vs]",
               # 12 oct. : l'opérateur trouve la musique trop forte sous la voix -> 0,5 -> 0,2,
               # et elle s'efface davantage quand Luna parle (ratio 6 -> 12)
               f"[1:a]volume=0.2,atrim=0:{total:.3f}[m]",
               "[m][vs]sidechaincompress=threshold=0.02:ratio=12:attack=20:release=500[md]",
               f"[vx]volume=2.0[vv]",
               f"[md][vv]amix=inputs=2:normalize=0,afade=t=out:st={total - 1:.2f}:d=1,"
               "loudnorm=I=-14:TP=-1.5[a]"]
    prec = "0:v"
    for j, (t0, t1, texte, style, dy) in enumerate(calques):
        p = tmp / f"t{j}.png"
        _calque(texte, style).save(p)
        entrees += ["-loop", "1", "-t", f"{total:.3f}", "-i", str(p)]
        filtres.append(f"[{prec}][{3 + j}:v]overlay=0:{dy}:enable='between(t,{t0:.2f},{t1:.2f})'[v{j}]")
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
    etapes = {"images": images, "video": video, "voix": voix, "levres": levres, "montage": montage}
    for nom in (sys.argv[1:] or list(etapes)):
        etapes[nom]()
