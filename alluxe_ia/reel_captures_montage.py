"""Montage du Reel « captures » de @alluxe.ia (6 oct. 2026, validé par l'opérateur).

    python3 -m alluxe_ia.reel_captures_montage   ->  data/alluxe_ia/reels/04-construit-par-ia.mp4

Les captures viennent de data/alluxe_ia/captures/ (hors git, comme tout data/) :
- x_Laboratoire.png, x_Agent.png : l'appli Alluxe Bot, ouverte dans un navigateur
  à partir d'une copie TEMPORAIRE (vérification d'identité sautée dans la copie
  seulement, copie supprimée ensuite : son paquet web contenait le compte de service) ;
- lab_propre.png : la même, rognée, la ligne qui nomme la plateforme floutée ;
- term/claude_*.png : RECONSTITUTION d'un écran Claude Code, avec le vrai code de
  ops/agent_outils.py (messages raccourcis) et le vrai résultat des tests (26 passed) ;
- term/robot.png : de vraies lignes du journal du robot, sans heures (deux jours mêlés).

Règles (CLAUDE.md) : le robot n'apparaît que comme histoire technique. Aucun montant,
aucun prix, aucun nom de crypto achetée, aucun lien ni nom de plateforme. Chaque
chiffre affiché est réel et daté (le tri : 2 oct., 22 h 25).
"""
import glob, math, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFont, ImageFilter
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
H = os.path.join(RACINE, 'data', 'alluxe_ia', 'captures') + '/'; P = os.path.join(RACINE, 'alluxe_ia', 'polices') + '/'
W, HT, FPS = 1080, 1920, 30
JAUNE, NOIR, BLANC = (255, 214, 64), (14, 16, 16), (255, 255, 255)
CREME, ENCRE, GRIS = (250, 247, 240), (17, 20, 19), (110, 118, 114)
F = lambda s: ImageFont.truetype(P + 'AtkinsonHyperlegible-Bold.ttf', s)
logo = Image.open(os.path.join(RACINE, 'docs', 'kit', 'logo-alluxe.png')).convert('RGBA')
claude = [Image.open(f).convert('RGB') for f in sorted(glob.glob(H + 'term/claude_*.png'))]
robot = Image.open(H + 'term/robot.png').convert('RGB')
lab = Image.open(H + 'lab_propre.png').convert('RGB')
agent = Image.open(H + 'x_Agent.png').convert('RGB').crop((0, 1150, 1080, 2338))


# --- Décor animé (couleurs d'alluxe.fr) : taches floues qui dérivent, trame de points, formes qui flottent ---
COULEURS = {"jaune": (255, 214, 64), "menthe": (92, 224, 198), "corail": (255, 128, 96),
            "lilas": (186, 168, 255), "ciel": (120, 190, 255)}
def _tache(couleur, r):
    s = Image.new("RGBA", (r * 2, r * 2), couleur + (0,))
    m = Image.new("L", (r * 2, r * 2), 0); ImageDraw.Draw(m).ellipse((r * 0.55, r * 0.55, r * 1.45, r * 1.45), fill=150)
    s.putalpha(m.filter(ImageFilter.GaussianBlur(r * 0.17))); return s
TACHES = {k: _tache(c, 560) for k, c in COULEURS.items()}
TRAME = Image.new("RGBA", (W + 60, HT + 60), (0, 0, 0, 0))
_dt = ImageDraw.Draw(TRAME)
for yy in range(0, HT + 60, 60):
    for xx in range(0, W + 60, 60): _dt.ellipse((xx, yy, xx + 6, yy + 6), fill=(17, 20, 19, 38))
def _forme(type_, couleur, r):
    s = Image.new("RGBA", (r * 2 + 20, r * 2 + 20), (0, 0, 0, 0)); d = ImageDraw.Draw(s); b = (10, 10, r * 2 + 10, r * 2 + 10)
    if type_ == "rond": d.ellipse(b, fill=couleur, outline=ENCRE, width=7)
    elif type_ == "carre": d.rounded_rectangle(b, r // 3, fill=couleur, outline=ENCRE, width=7)
    else:
        pts = [(r + 10 + (r if i % 2 == 0 else r * 0.45) * math.cos(math.pi / 2 + i * math.pi / 5),
                r + 10 - (r if i % 2 == 0 else r * 0.45) * math.sin(math.pi / 2 + i * math.pi / 5)) for i in range(10)]
        d.polygon(pts, fill=couleur, outline=ENCRE, width=7)
    return s
FORMES = [  # (type, couleur, rayon, x, y, vitesse, phase)
    ("rond", "menthe", 46, 0.08, 0.30, 1.0, 0.0), ("etoile", "jaune", 58, 0.90, 0.22, 0.8, 1.3),
    ("carre", "lilas", 40, 0.88, 0.86, 1.2, 2.1), ("rond", "corail", 32, 0.12, 0.90, 0.9, 3.0),
    ("etoile", "ciel", 40, 0.06, 0.62, 1.1, 4.2), ("carre", "jaune", 34, 0.93, 0.55, 0.7, 5.0)]
SPRITES = [_forme(ty, COULEURS[c], r) for ty, c, r, *_ in FORMES]
PALETTES = [("jaune", "menthe", "lilas"), ("corail", "jaune", "ciel"), ("menthe", "ciel", "jaune"),
            ("lilas", "corail", "jaune"), ("ciel", "menthe", "corail"), ("jaune", "lilas", "menthe"), ("corail", "lilas", "ciel")]
def decor(img, t, scene):
    pal = PALETTES[scene % len(PALETTES)]
    for i, nom in enumerate(pal):                       # taches de couleur qui dérivent
        a = t * (0.35 + 0.12 * i) + i * 2.1
        x = int(W * (0.15 + 0.7 * ((i * 0.37) % 1)) + 220 * math.cos(a)) - 560
        y = int(HT * (0.2 + 0.3 * i) + 260 * math.sin(a * 0.8)) - 560
        img.paste(TACHES[nom], (x, y), TACHES[nom])
    o = int(t * 18) % 60                                # trame qui glisse
    img.paste(TRAME, (-o, -o), TRAME)
    for (ty, c, r, fx, fy, v, ph), sp in zip(FORMES, SPRITES):   # formes qui flottent et tournent
        rot = sp.rotate(math.degrees(math.sin(t * v + ph)) * 0.6 + t * 25 * v, resample=Image.BICUBIC)
        x = int(W * fx + 24 * math.sin(t * v * 1.3 + ph)) - rot.width // 2
        y = int(HT * fy + 40 * math.cos(t * v + ph)) - rot.height // 2
        img.paste(rot, (x, y), rot)

def ease(x): x = max(0, min(1, x)); return 1 - (1 - x) ** 3

def texte(d, y, lignes, taille, couleur=BLANC, fond=None, t=1.0, x=60):
    f = F(taille); y0 = y
    for i, (l, surl) in enumerate(lignes):
        a = ease(t * 3 - i * 0.35)              # chaque ligne arrive un peu après
        if a <= 0: continue
        dx = int((1 - a) * 60); w = f.getlength(l)
        if surl: d.rounded_rectangle((x + dx - 14, y0 - 6, x + dx + w + 14, y0 + taille + 14), 14, fill=surl)
        elif fond: d.rounded_rectangle((x + dx - 14, y0 - 6, x + dx + w + 14, y0 + taille + 14), 14, fill=fond)
        if surl:
            d.text((x + dx, y0), l, font=f, fill=NOIR)
        else:                                   # blanc comme avant, lisible sur le décor : ombre + contour noir
            ep = max(2, taille // 32)
            d.text((x + dx + 4, y0 + 5), l, font=f, fill=ENCRE)
            d.text((x + dx, y0), l, font=f, fill=couleur, stroke_width=ep, stroke_fill=ENCRE)
        y0 += int(taille * 1.25)

def ecran(img, capture, y, haut, decal=0.0, zoom=1.0):
    """La capture dans un cadre de téléphone arrondi ; decal = défilement (0..1)."""
    larg = int(900 * zoom); r = larg / capture.width
    c = capture.resize((larg, int(capture.height * r)))
    vis = min(haut, c.height); oy = int((c.height - vis) * decal)
    c = c.crop((0, oy, larg, oy + vis))
    m = Image.new('L', c.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, c.width, c.height), 40, fill=255)
    x = (W - c.width) // 2
    dd = ImageDraw.Draw(img); dd.rounded_rectangle((x + 10, y + 14, x + c.width + 22, y + c.height + 26), 46, fill=JAUNE)
    dd.rounded_rectangle((x - 6, y - 6, x + c.width + 6, y + c.height + 6), 46, fill=ENCRE)
    img.paste(c, (x, y), m)

def mettre_logo(img, taille=150):
    l = logo.resize((taille, taille)); img.paste(l, (W - taille - 50, 70), l)

def etiquette(d, n, t, y=90):
    f = F(40); d.rounded_rectangle((60, y, 60 + 70, y + 70), 18, fill=JAUNE, outline=ENCRE, width=4); d.text((80, y + 8), str(n), font=f, fill=NOIR)

def legende(img, d, y, lignes, taille, u, n):
    """Titre en gros SUR la capture, posé sur un bandeau sombre translucide (lisible sur n'importe quel écran)."""
    a = ease(u * 4)
    if a <= 0: return
    f = F(taille); h = int(len(lignes) * taille * 1.25) + 70
    larg = int(max(f.getlength(l) for l, _ in lignes)) + 150
    voile = Image.new("L", img.size, 0)
    ImageDraw.Draw(voile).rounded_rectangle((36, y - 40, min(W - 36, 36 + larg), y - 40 + h), 34, fill=int(205 * a))
    img.paste(Image.new("RGB", img.size, ENCRE), (0, 0), voile)
    etiquette(d, n, u, y=y - 72)
    texte(d, y, lignes, taille, t=u * 4, x=70)

def image(t):
    img = Image.new('RGB', (W, HT), CREME)
    scene = sum(t >= s for s in (2.2, 5.4, 7.8, 10.4, 12.8, 15.2))
    if scene < 6: decor(img, t, scene)
    d = ImageDraw.Draw(img)
    if t < 2.2:                                   # 1. accroche : ça bouge dès la 1re image
        mettre_logo(img, 210)
        texte(d, 300, [("Je ne suis pas", None), ("développeur.", JAUNE)], 112, t=t / 0.9)
        if t > 0.9: texte(d, 590, [("Voici ce que l'IA", None), ("a construit pour moi :", None)], 70, t=(t - 0.9) / 0.8)
        ecran(img, robot, 830 + int((1 - ease(t * 2)) * 300), 1000, decal=0.15 + t * 0.12)
    elif t < 5.4:                                 # 2. Claude Code écrit le code
        u = (t - 2.2) / 3.2
        k = min(len(claude) - 1, int(u * 1.25 * (len(claude) - 1)))
        ecran(img, claude[k], 140, 1700, decal=1.0)
        legende(img, d, 1200, [("Claude écrit", None), ("le code.", JAUNE)], 118, u, 1)
    elif t < 7.8:                                 # 3. le robot
        u = (t - 5.4) / 2.4
        ecran(img, robot, 140, 1700, decal=u)
        legende(img, d, 1100, [("Un robot qui", None), ("surveille 194", None), ("marchés.", JAUNE)], 112, u, 2)
    elif t < 10.4:                                # 3b. le tri (moment réel : 2 oct., 22 h 25, moins d'une minute)
        u = (t - 7.8) / 2.6
        etiquette(d, 3, u); texte(d, 70, [("Il trie avant", None), ("d'acheter.", JAUNE)], 104, t=u * 4, x=165)
        etapes = [(220, "marchés regardés", (255, 255, 255)), (218, "refusés", (255, 128, 96)), (2, "achetés", JAUNE)]
        for i, (v, lib, c) in enumerate(etapes):
            a = ease((u - 0.08 - i * 0.22) * 3.2)
            if a <= 0: continue
            y = 420 + i * 390; n = int(v * a) if i < 2 else (v if a > 0.5 else 0)
            texte_l = F(140).getlength(str(v)) + 40 + F(62).getlength(lib) + 90   # le libellé tient toujours dans sa case
            larg = int(max(texte_l, 900 * v / 220) * a) if i < 2 else int(texte_l * a)
            larg = max(larg, 60)
            d.rounded_rectangle((90 + 8, y + 12, 90 + larg + 8, y + 282), 34, fill=ENCRE)
            d.rounded_rectangle((90, y, 90 + larg, y + 270), 34, fill=c, outline=ENCRE, width=6)
            if a > 0.92:
                d.text((130, y + 40), str(n), font=F(140), fill=ENCRE)
                d.text((130 + F(140).getlength(str(v)) + 40, y + 110), lib, font=F(62), fill=ENCRE)
        f = F(40); s = "moment réel · 2 oct., 22 h 25, en moins d'une minute"; lx = (W - f.getlength(s)) / 2
        d.rounded_rectangle((lx - 24, 1626, lx + f.getlength(s) + 24, 1700), 37, fill=CREME, outline=ENCRE, width=3)
        d.text((lx, 1640), s, font=f, fill=ENCRE)
    elif t < 12.8:                                # 4. le labo
        u = (t - 10.4) / 2.4
        ecran(img, lab, 160, 1400, zoom=1.0 + 0.06 * ease(u))
        legende(img, d, 1400, [("Un labo qui a testé", None), ("3 254 idées.", JAUNE)], 104, u, 4)
    elif t < 15.2:                                # 5. l'agent refuse
        u = (t - 12.8) / 2.4
        ecran(img, agent, 140, 1500, zoom=1.0 + 0.05 * ease(u))
        legende(img, d, 1180, [("Un agent IA qui", None), ("refuse ce qui est", None), ("dangereux.", JAUNE)], 104, u, 5)
    else:                                         # 6. fin
        u = (t - 15.2) / 1.4
        img.paste(Image.new('RGB', (W, HT), JAUNE)); d = ImageDraw.Draw(img)
        l = logo.resize((300, 300)); img.paste(l, ((W - 300) // 2, 420), l)
        f = F(96)
        for i, s in enumerate(["Je te montre", "comment."]):
            d.text(((W - f.getlength(s)) / 2, 820 + i * 115), s, font=f, fill=NOIR)
        f2 = F(60); s = "Abonne-toi : @alluxe.ia"
        d.rounded_rectangle(((W - f2.getlength(s)) / 2 - 30, 1130, (W + f2.getlength(s)) / 2 + 30, 1230), 50, fill=NOIR)
        d.text(((W - f2.getlength(s)) / 2, 1145), s, font=f2, fill=JAUNE)
    return img

DUREE = 16.6
os.makedirs(H + 'images', exist_ok=True)
for i in range(int(DUREE * FPS)):
    image(i / FPS).save(H + f'images/{i:04d}.jpg', quality=90)
from alluxe_ia.musique import ecrire_wav
ecrire_wav(H + 'musique.wav', DUREE, graine='captures')
try:
    import imageio_ffmpeg; ff = imageio_ffmpeg.get_ffmpeg_exe()
except Exception: ff = 'ffmpeg'
subprocess.run([ff, '-y', '-loglevel', 'error', '-framerate', str(FPS), '-i', H + 'images/%04d.jpg', '-i', H + 'musique.wav',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-c:a', 'aac', '-b:a', '128k', '-shortest',
                '-movflags', '+faststart', os.path.join(RACINE, 'data', 'alluxe_ia', 'reels', '04-construit-par-ia.mp4')], check=True)
print('ok', os.path.join(RACINE, 'data', 'alluxe_ia', 'reels', '04-construit-par-ia.mp4'))
