"""Bande-annonce animée du livre « Les détectives maladroits ».

Toutes les images viennent de la couverture (couverture.jpg) : caméra qui
se déplace sur l'illustration, tremblements de panique, bulles de
dialogue, gyrophares, loupe. La musique est synthétisée ici même.

    pip install pillow numpy imageio-ffmpeg
    python3 fabriquer_video.py      ->  detectives_maladroits.mp4
"""
import math
import subprocess
import wave

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
POLICE = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

photo = Image.open("couverture.jpg").convert("RGB")
COUV = photo.crop((367, 163, 2284, 3247))          # la couverture seule
CW, CH = COUV.size

# Cadres de caméra dans la couverture (x0, y0, x1, y1)
TOUT = (0, 0, CW, CH)
FOND = Image.blend(Image.new("RGB", (W, H), (10, 15, 45)),
                   COUV.resize((W, H)).filter(ImageFilter.GaussianBlur(40)), 0.5)
TITRE = (60, 80, 1850, 960)
CLOCHE = (560, 1450, 1360, 2150)
FILLE = (0, 880, 820, 2200)
GARCON = (930, 830, 1860, 2200)
DUO = (0, 800, 1917, 2450)
AUTEUR = (560, 2560, 1360, 2860)


def police(t):
    return ImageFont.truetype(POLICE, t)


def lisse(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def melange(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def camera(cadre, tremble=0.0, t=0.0):
    """Remplit l'écran 9:16 avec le cadre demandé (recadré pour le ratio)."""
    x0, y0, x1, y1 = cadre
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    w, h = x1 - x0, y1 - y0
    if w / h > W / H:
        h = w * H / W
    else:
        w = h * W / H
    if tremble:
        cx += math.sin(t * 61) * tremble * w
        cy += math.cos(t * 47) * tremble * h
    # on garde le cadre dans la couverture tant qu'il y tient
    if w <= CW:
        cx = min(max(cx, w / 2), CW - w / 2)
    if h <= CH:
        cy = min(max(cy, h / 2), CH - h / 2)
    x0, y0 = cx - w / 2, cy - h / 2
    img = COUV.crop((int(x0), int(y0), int(x0 + w), int(y0 + h)))
    img = img.resize((W, H), Image.LANCZOS)
    if x0 < 0 or y0 < 0 or x0 + w > CW or y0 + h > CH:
        # au-delà de la couverture : fond flou plutôt que du noir
        img_fond = FOND.copy()
        e = W / w
        img_fond.paste(COUV.resize((int(CW * e), int(CH * e)), Image.LANCZOS),
                       (int(-x0 * e), int(-y0 * e)))
        img = img_fond
    return img


def fond_nuit(t):
    img = Image.new("RGB", (W, H), (12, 16, 40))
    d = ImageDraw.Draw(img)
    for i in range(0, H, 8):
        v = int(18 + 30 * i / H)
        d.rectangle((0, i, W, i + 8), fill=(v // 2, v // 2 + 4, v + 20))
    return img


def texte_centre(d, y, txt, taille, couleur=(255, 214, 64), contour=(60, 30, 0)):
    f = police(taille)
    lignes = txt.split("\n")
    for i, l in enumerate(lignes):
        b = d.textbbox((0, 0), l, font=f, stroke_width=6)
        x = (W - (b[2] - b[0])) / 2
        d.text((x, y + i * taille * 1.2), l, font=f, fill=couleur,
               stroke_width=6, stroke_fill=contour)


def bulle(img, txt, x, y, largeur, queue, n_car=None, taille=46):
    """Bulle de BD ; n_car fait apparaître le texte lettre par lettre."""
    if n_car is not None:
        txt = txt[:max(0, n_car)]
    f = police(taille)
    mots, lignes, cour = txt.split(" "), [], ""
    for m in mots:
        essai = (cour + " " + m).strip()
        if f.getlength(essai) > largeur - 60:
            lignes.append(cour)
            cour = m
        else:
            cour = essai
    lignes.append(cour)
    h = max(1, len(lignes)) * taille * 1.25 + 50
    calque = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(calque)
    d.polygon([(x + largeur * 0.3, y + h - 5), (x + largeur * 0.45, y + h - 5), queue],
              fill=(255, 255, 255, 245), outline=(20, 20, 20, 255), width=5)
    d.rounded_rectangle((x, y, x + largeur, y + h), 40,
                        fill=(255, 255, 255, 245), outline=(20, 20, 20, 255), width=6)
    d.rectangle((x + largeur * 0.3 + 4, y + h - 12, x + largeur * 0.45 - 4, y + h - 2),
                fill=(255, 255, 255, 245))
    for i, l in enumerate(lignes):
        d.text((x + 30, y + 25 + i * taille * 1.25), l, font=f, fill=(20, 20, 30))
    img.paste(calque, (0, 0), calque)


def gouttes(d, t, zone, n=6):
    """Gouttes de sueur qui tombent en boucle."""
    x0, y0, x1, y1 = zone
    for i in range(n):
        ph = (t * 1.3 + i / n) % 1
        x = x0 + (x1 - x0) * ((i * 0.37) % 1)
        y = y0 + (y1 - y0) * ph
        r = 14
        d.polygon([(x, y - r * 1.8), (x - r, y), (x + r, y)], fill=(170, 225, 255))
        d.ellipse((x - r, y - r, x + r, y + r), fill=(170, 225, 255), outline=(40, 90, 150), width=3)


def exclamations(d, t, points):
    f = police(130)
    for i, (x, y) in enumerate(points):
        s = abs(math.sin(t * 7 + i))
        d.text((x, y - s * 30), "!", font=f, fill=(255, 60, 60),
               stroke_width=7, stroke_fill=(255, 255, 255))


def fondu(img, t, duree, total):
    """Fondu au noir en entrée et en sortie de scène."""
    a = min(1, t / 0.35, (total - t) / 0.35)
    if a >= 1:
        return img
    return Image.blend(Image.new("RGB", img.size, (0, 0, 0)), img, max(0, a))


# ---------------------------------------------------------------- scènes
def s_intro(t, T):
    img = fond_nuit(t)
    d = ImageDraw.Draw(img, "RGBA")
    # projecteur qui balaie
    cx = W / 2 + math.sin(t * 1.8) * 350
    for r in range(420, 0, -30):
        d.ellipse((cx - r, 1100 - r * 0.7, cx + r, 1100 + r * 0.7),
                  fill=(255, 240, 180, 14))
    msg = "Paris. Minuit.\nUne affaire\nTOP SECRET..."
    n = int(t * 16)
    texte_centre(d, 520, msg[:n], 96, (255, 255, 255), (0, 0, 0))
    if t > 2.6:
        s = lisse((t - 2.6) / 0.5)
        f = police(int(60 + 40 * s))
        d.text((W / 2, 1500), "CLASSÉ", font=f, anchor="mm",
               fill=(230, 40, 40, int(255 * s)), stroke_width=4, stroke_fill=(120, 0, 0))
    return img


def s_titre(t, T):
    k = lisse(t / T)
    cadre = melange((-150, -300, CW + 150, CH + 300), TOUT, k)
    img = camera(cadre, 0.004 if t > T * 0.7 else 0, t)
    d = ImageDraw.Draw(img)
    if t > T * 0.6:
        exclamations(d, t, [(40, 1100), (960, 1050)])
    return img


def s_cloche(t, T):
    k = lisse(t / 2.0)
    img = camera(melange(DUO, CLOCHE, k))
    # halo qui pulse autour de la pièce à conviction
    halo = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(halo)
    p = 0.5 + 0.5 * math.sin(t * 5)
    d.ellipse((140, 520, 940, 1300), fill=(255, 120, 255, int(50 + 60 * p)))
    halo = halo.filter(ImageFilter.GaussianBlur(60))
    img.paste(halo, (0, 0), halo)
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(8):  # étincelles
        a = t * 2 + i * math.pi / 4
        x, y = 540 + math.cos(a) * 420, 900 + math.sin(a) * 380
        s = 18 + 10 * math.sin(t * 9 + i)
        d.polygon([(x, y - s), (x + s / 3, y), (x, y + s), (x - s / 3, y)], fill=(255, 255, 200))
        d.polygon([(x - s, y), (x, y + s / 3), (x + s, y), (x, y - s / 3)], fill=(255, 255, 200))
    if t > 1.6:
        d.rounded_rectangle((60, 1500, 1020, 1800), 30, fill=(20, 20, 50, 220))
        texte_centre(d, 1535, "PIÈCE À CONVICTION N°1", 60)
        n = int((t - 1.6) * 22)
        texte_centre(d, 1640, "Une culotte à pois... violette !"[:n], 50, (255, 255, 255), (0, 0, 0))
    return img


def s_fille(t, T):
    k = lisse(t / 1.2)
    img = camera(melange(CLOCHE, FILLE, k), 0.006 if t > 1.2 else 0, t)
    d = ImageDraw.Draw(img)
    gouttes(d, t, (560, 300, 880, 900), 4)
    if t > 1.2:
        bulle(img, "Par ma loupe ! C'est une affaire d'ÉTAT !", 80, 90, 900,
              (470, 720), int((t - 1.2) * 24), 58)
    return img


def s_garcon(t, T):
    k = lisse(t / 1.2)
    img = camera(melange(FILLE, GARCON, k), 0.007 if t > 1.2 else 0, t)
    d = ImageDraw.Draw(img)
    gouttes(d, t, (120, 250, 420, 900), 4)
    if t > 1.2:
        bulle(img, "Je note... culotte... violette... à pois... AU SECOURS !",
              90, 60, 900, (640, 560), int((t - 1.2) * 24), 54)
    return img


def s_duo(t, T):
    img = camera(DUO, 0.004, t)
    # gyrophares rouge / bleu
    c = (255, 30, 30) if int(t * 4) % 2 == 0 else (30, 80, 255)
    flash = Image.new("RGB", img.size, c)
    img = Image.blend(img, flash, 0.22 + 0.1 * math.sin(t * 25))
    d = ImageDraw.Draw(img, "RGBA")
    exclamations(d, t, [(20, 900), (990, 850)])
    # bandeau qui glisse
    x = W * (1 - lisse(t / 0.8))
    d.polygon([(x - 40, 1450), (x + W + 40, 1420), (x + W + 40, 1700), (x - 40, 1730)],
              fill=(200, 30, 70, 240))
    f = police(62)
    d.text((x + W / 2, 1520), "Quand la lingerie devient", font=f, anchor="mm",
           fill=(255, 255, 255), stroke_width=3, stroke_fill=(90, 0, 20))
    d.text((x + W / 2, 1620), "une affaire d'État !", font=police(80), anchor="mm",
           fill=(255, 225, 90), stroke_width=4, stroke_fill=(90, 0, 20))
    return img


def s_loupe(t, T):
    base = camera(DUO).filter(ImageFilter.GaussianBlur(3))
    base = Image.blend(Image.new("RGB", base.size, (0, 0, 0)), base, 0.55)
    # la loupe suit un 8 et grossit ce qu'elle survole
    lx = W / 2 + math.sin(t * 1.3) * 300
    ly = 960 + math.sin(t * 2.6) * 320
    R = 260
    net = camera(DUO)
    zoom = net.crop((int(lx - R / 2), int(ly - R / 2), int(lx + R / 2), int(ly + R / 2)))
    zoom = zoom.resize((2 * R, 2 * R), Image.LANCZOS)
    masque = Image.new("L", (2 * R, 2 * R), 0)
    ImageDraw.Draw(masque).ellipse((0, 0, 2 * R, 2 * R), fill=255)
    base.paste(zoom, (int(lx - R), int(ly - R)), masque)
    d = ImageDraw.Draw(base)
    d.ellipse((lx - R, ly - R, lx + R, ly + R), outline=(60, 60, 80), width=28)
    d.ellipse((lx - R + 10, ly - R + 10, lx + R - 10, ly + R - 10), outline=(170, 170, 200), width=6)
    a = math.radians(45)
    x1, y1 = lx + math.cos(a) * (R + 10), ly + math.sin(a) * (R + 10)
    d.line((x1, y1, x1 + 230, y1 + 230), fill=(90, 50, 20), width=60)
    texte_centre(d, 120, "Aucun indice ne\nleur échappe...", 80)
    texte_centre(d, 1700, "(ou presque)", 60, (255, 255, 255), (0, 0, 0))
    return base


def s_fin(t, T):
    img = fond_nuit(t)
    d = ImageDraw.Draw(img, "RGBA")
    for i in range(40):  # étoiles
        x, y = (i * 263) % W, (i * 587) % 1000
        s = 3 + 3 * abs(math.sin(t * 3 + i))
        d.ellipse((x - s, y - s, x + s, y + s), fill=(255, 255, 220))
    k = lisse(t / 1.0)
    lw = int(620 * (0.6 + 0.4 * k))
    livre = COUV.resize((lw, int(lw * CH / CW)), Image.LANCZOS)
    y = int(260 + math.sin(t * 2.2) * 18)
    ombre = Image.new("RGBA", (livre.width + 60, livre.height + 60), (0, 0, 0, 0))
    ImageDraw.Draw(ombre).rectangle((30, 30, livre.width + 30, livre.height + 30), fill=(0, 0, 0, 160))
    ombre = ombre.filter(ImageFilter.GaussianBlur(20))
    img.paste(ombre, ((W - livre.width) // 2 - 10, y), ombre)
    img.paste(livre, ((W - livre.width) // 2, y))
    if t > 1.0:
        texte_centre(d, 1330, "Les détectives\nmaladroits", 84)
        texte_centre(d, 1560, "de Basutiian Liam", 50, (255, 255, 255), (0, 0, 0))
    if t > 2.0:
        p = 1 + 0.06 * math.sin(t * 6)
        d.rounded_rectangle((W / 2 - 380 * p, 1680, W / 2 + 380 * p, 1800), 60, fill=(220, 40, 80))
        d.text((W / 2, 1740), "Disponible maintenant !", font=police(52), anchor="mm", fill=(255, 255, 255))
    return img


SCENES = [(s_intro, 4.0), (s_titre, 5.0), (s_cloche, 5.5), (s_fille, 5.5),
          (s_garcon, 6.0), (s_duo, 5.0), (s_loupe, 5.0), (s_fin, 6.0)]


# ---------------------------------------------------------------- musique
def musique(duree, sr=44100):
    n = int(duree * sr)
    son = np.zeros(n)
    tempo = 0.25  # croche à 120 bpm
    def note(f, deb, dur, vol, forme="pizz"):
        i0, k = int(deb * sr), int(dur * sr)
        if i0 >= n:
            return
        k = min(k, n - i0)
        tt = np.arange(k) / sr
        if forme == "pizz":
            s = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 9)
        else:
            s = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 4)
        son[i0:i0 + k] += vol * s
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)
    # thème « détective sur la pointe des pieds » en mi mineur
    basse = [40, 47, 43, 47, 40, 47, 45, 44]
    theme = [64, None, 67, 66, 64, None, 71, 70, 69, None, 67, 66, 64, 62, 64, None]
    pas = 0
    t = 0.0
    while t < duree:
        note(hz(basse[pas % 8]), t, 0.4, 0.35, "basse")
        m = theme[pas % 16]
        if m and (pas // 16) % 2 == 0 or (m and pas > 32):
            note(hz(m), t, 0.3, 0.22)
        if pas % 4 == 2:
            note(2000, t, 0.03, 0.05)  # petit « tic » de charleston
        t += tempo
        pas += 1
    # sirène pendant la scène du duo
    deb = sum(d for _, d in SCENES[:5])
    i0, i1 = int(deb * sr), int((deb + 5.0) * sr)
    tt = np.arange(i1 - i0) / sr
    f = 700 + 250 * np.sign(np.sin(2 * np.pi * 2 * tt))
    son[i0:i1] += 0.12 * np.sin(2 * np.pi * np.cumsum(f) / sr)
    # « whoosh » à chaque changement de scène
    t = 0
    for _, d in SCENES[:-1]:
        t += d
        i0 = int((t - 0.2) * sr)
        k = int(0.4 * sr)
        bruit = np.random.default_rng(1).standard_normal(k)
        env = np.sin(np.linspace(0, np.pi, k)) ** 2
        son[i0:i0 + k] += 0.15 * np.convolve(bruit, np.ones(20) / 20, "same") * env
    fin = int(0.8 * sr)
    son[-fin:] *= np.linspace(1, 0, fin)
    son /= np.max(np.abs(son)) * 1.1
    with wave.open("musique.wav", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((son * 32767).astype(np.int16).tobytes())


def main():
    total = sum(d for _, d in SCENES)
    musique(total)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", "musique.wav",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "22", "-preset", "medium",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart",
         "detectives_maladroits.mp4"],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for scene, duree in SCENES:
        for i in range(int(duree * FPS)):
            t = i / FPS
            img = fondu(scene(t, duree), t, duree, duree)
            proc.stdin.write(img.convert("RGB").tobytes())
    proc.stdin.close()
    proc.wait()
    print("OK :", total, "s")


if __name__ == "__main__":
    main()
