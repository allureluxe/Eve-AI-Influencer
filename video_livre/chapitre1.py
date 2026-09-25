"""Dessin animé du chapitre 1 : « Deux catastrophes se rencontrent ».

Tout est dessiné ici même en vectoriel (cairo) : personnages articulés,
décors, objets, bulles, bruitages et musique. Bastien et Lucie gardent
les couleurs de la couverture (blond / roux bouclé, yeux bleus) ; la
fin rejoint la couverture, dix ans plus tard.

    pip install pycairo pillow numpy imageio-ffmpeg
    python3 chapitre1.py            ->  chapitre1_dessin_anime.mp4
    python3 chapitre1.py --apercu   ->  une image par scène (apercu_*.png)
"""
import math
import random
import subprocess
import sys
import wave

import cairo
import imageio_ffmpeg
import numpy as np

W, H, FPS = 1920, 1080, 24
SOL = 900
OUT = (0.15, 0.09, 0.06)
POLICE = "DejaVu Sans"


# ------------------------------------------------------------ outils
def c(h, a=1.0):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (a,)


def fonce(col, k=0.78):
    return (col[0] * k, col[1] * k, col[2] * k, col[3])


def lisse(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def prog(t, a, b):
    return lisse((t - a) / (b - a)) if b > a else float(t >= a)


def lin(t, a, b):
    return min(max((t - a) / (b - a), 0.0), 1.0)


def rebond(x):
    x = min(max(x, 0.0), 1.0)
    s = 1.9
    x -= 1
    return max(0.001, x * x * ((s + 1) * x + s) + 1)


def mix(a, b, k):
    return a + (b - a) * k


def police(ctx, taille, gras=True):
    ctx.select_font_face(POLICE, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if gras else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(taille)


def remplir(ctx, col, lw=6, trait=OUT):
    ctx.set_source_rgba(*col)
    if lw:
        ctx.fill_preserve()
        ctx.set_source_rgba(*trait)
        ctx.set_line_width(lw)
        ctx.stroke()
    else:
        ctx.fill()


def rrect(ctx, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    ctx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    ctx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    ctx.close_path()


def ellipse(ctx, x, y, rx, ry):
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(max(rx, 0.01), max(ry, 0.01))
    ctx.arc(0, 0, 1, 0, 2 * math.pi)
    ctx.restore()


def texte(ctx, s, x, y, taille, col=(1, 1, 1, 1), contour=None, lw=6, centre=True, gras=True):
    police(ctx, taille, gras)
    e = ctx.text_extents(s)
    if centre:
        x -= e.x_advance / 2
    ctx.move_to(x, y)
    ctx.text_path(s)
    if contour:
        ctx.set_source_rgba(*contour)
        ctx.set_line_width(lw)
        ctx.set_line_join(cairo.LINE_JOIN_ROUND)
        ctx.stroke_preserve()
    ctx.set_source_rgba(*col)
    ctx.fill()


def couper(ctx, s, largeur):
    mots, lignes, cour = s.split(" "), [], ""
    for m in mots:
        essai = (cour + " " + m).strip()
        if cour and ctx.text_extents(essai).x_advance > largeur:
            lignes.append(cour)
            cour = m
        else:
            cour = essai
    lignes.append(cour)
    return lignes


# ------------------------------------------------------------ personnages
PERSOS = {
    "bastien": dict(peau=c("f6c89f"), cheveux=c("f2c14e"), coiffure="pics", haut=c("3a7bd5"),
                    bas=c("4a4f5c"), chaussures=c("d64541"), yeux=c("2e86de"), sac=c("4c9a2a"),
                    lacets=True),
    "lucie": dict(peau=c("f7cfa8"), cheveux=c("a4471f"), coiffure="boucles", haut=c("e8a33d"),
                  bas=c("2d4a7a"), chaussures=c("fafafa"), yeux=c("2e86de")),
    "surveillant": dict(peau=c("e8b58f"), cheveux=c("777777"), coiffure="chauve", haut=c("6d4c41"),
                        bas=c("3e2723"), chaussures=c("222222"), yeux=c("5d4037"), moustache=True,
                        lunettes=True, taille=1.1),
    "prof": dict(peau=c("d9a066"), cheveux=c("2d1b0e"), coiffure="casquette", haut=c("c0392b"),
                 bas=c("c0392b"), chaussures=c("ffffff"), yeux=c("5d4037"), sifflet=True, taille=1.1),
}
_r = random.Random(4)
for i, (hc, top, cf) in enumerate([("3b2a1a", "8e44ad", "court"), ("111111", "16a085", "boucles"),
                                   ("d35400", "2c3e50", "court"), ("f1c40f", "e84393", "long"),
                                   ("5d4037", "27ae60", "court")]):
    PERSOS[f"eleve{i}"] = dict(peau=c(_r.choice(["f6c89f", "e0ac69", "c68642", "8d5524", "ffdbac"])),
                               cheveux=c(hc), coiffure=cf, haut=c(top), bas=c("34495e"),
                               chaussures=c("ecf0f1"), yeux=c("4e342e"), taille=0.95)


def P(**k):
    d = dict(lean=0.0, hl=0.05, kl=0.0, hr=-0.05, kr=0.0, sl=0.12, el=0.2, sr=-0.1, er=0.2,
             drop=0.0, tete=0.0, dy=0.0)
    d.update(k)
    return d


def p_debout(t, ph=0.0):
    return P(lean=0.02 * math.sin(t * 2 + ph), sl=0.15 + 0.03 * math.sin(t * 2 + ph))


def p_marche(t, v=1.0):
    s = math.sin(t * 7 * v)
    return P(hl=0.45 * s, kl=-0.5 * max(0, -s), hr=-0.45 * s, kr=-0.5 * max(0, s),
             sl=-0.45 * s, sr=0.45 * s, el=0.3, er=0.3, dy=-6 * abs(s))


def p_course(t, v=1.0):
    w = t * 12 * v
    s = math.sin(w)
    return P(lean=0.28, hl=0.95 * s, kl=-0.3 - 1.1 * max(0, -s), hr=-0.95 * s, kr=-0.3 - 1.1 * max(0, s),
             sl=-1.0 * s, sr=1.0 * s, el=1.5, er=1.5, dy=-18 * abs(math.cos(w)))


def p_moulin(t):
    return P(lean=-0.35, sl=t * 17, sr=t * 17 + math.pi, el=0.1, er=0.1,
             hl=1.0, kl=-0.2, hr=-0.15, kr=0)


def p_accroupi():
    return P(drop=100, hl=1.2, kl=-2.2, hr=1.1, kr=-2.1, lean=0.35, sl=0.5, sr=0.7, el=0.6, er=0.5)


def p_assis():
    return P(drop=95, hl=1.57, kl=-1.57, hr=1.5, kr=-1.5, sl=0.5, sr=0.6, el=0.6, er=0.5)


def p_assis_sol():
    return P(drop=172, hl=1.5, kl=0.0, hr=1.45, kr=0.0, lean=0.05, sl=-0.5, sr=-0.4, el=0.0, er=0.0)


def p_allonge(t=0):
    return P(sl=2.9, sr=2.7, el=0.1, er=0.1, hl=0.1, hr=-0.1)


def p_grimpe(t=0):
    return P(sl=3.05, sr=2.95, el=0.05, er=0.05, hl=0.35 + 0.1 * math.sin(t * 6), kl=-0.6,
             hr=-0.1, kr=-0.3)


def p_rire(t):
    return P(lean=-0.08 + 0.09 * math.sin(t * 16), sl=0.45, sr=0.5, el=1.7, er=1.7, dy=-4 * abs(math.sin(t * 16)))


def p_tete_mains(t):
    return P(lean=0.15, sl=2.55, sr=2.55, el=1.95, er=1.95, tete=0.15)


def fondu_pose(a, b, k):
    return {x: mix(a[x], b[x], k) for x in a}


def membre(ctx, pts, larg, col):
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    for lw, cc in ((larg + 9, OUT), (larg, col)):
        ctx.move_to(*pts[0])
        for p in pts[1:]:
            ctx.line_to(*p)
        ctx.set_source_rgba(*cc)
        ctx.set_line_width(lw)
        ctx.stroke()


def seg(p, a, l):
    return (p[0] + l * math.sin(a), p[1] + l * math.cos(a))


def dessiner_cheveux_arriere(ctx, d, r):
    if d["coiffure"] in ("boucles", "long"):
        for i in range(14):
            a = math.pi * 0.55 + i * 0.16
            rr = r * (1.02 + 0.08 * math.sin(i * 2.3))
            x, y = -12 + math.cos(a) * rr * 0.95, math.sin(a) * rr * 0.9 - 8
            ctx.arc(x, y, 30 if d["coiffure"] == "boucles" else 34, 0, 2 * math.pi)
            ctx.close_path()
        if d["coiffure"] == "boucles":
            for i in range(6):
                ctx.arc(-70 + 8 * math.sin(i), 20 + i * 22, 28, 0, 2 * math.pi)
                ctx.close_path()
        remplir(ctx, d["cheveux"], 5)


def dessiner_cheveux_avant(ctx, d, r):
    col = d["cheveux"]
    f = d["coiffure"]
    if f == "pics":
        ctx.move_to(-r * 0.98, 5)
        n = 9
        for i in range(n + 1):
            a = math.pi * 1.02 + i * (math.pi * 0.98 / n)
            rr = r * (1.3 if i % 2 else 0.98)
            ctx.line_to(math.cos(a) * rr, math.sin(a) * rr)
        ctx.line_to(r * 0.95, -18)
        ctx.line_to(60, -35)
        ctx.line_to(40, -18)
        ctx.line_to(22, -40)
        ctx.line_to(0, -22)
        ctx.line_to(-30, -45)
        ctx.line_to(-60, -10)
        ctx.close_path()
        remplir(ctx, col, 5)
    elif f == "boucles":
        for i in range(11):
            a = math.pi * 1.05 + i * 0.105 * math.pi
            ctx.arc(math.cos(a) * r * 0.92, math.sin(a) * r * 0.92, 27, 0, 2 * math.pi)
            ctx.close_path()
        ctx.arc(-40, -52, 30, 0, 2 * math.pi)
        ctx.close_path()
        ctx.arc(10, -60, 28, 0, 2 * math.pi)
        ctx.close_path()
        remplir(ctx, col, 5)
    elif f == "court":
        ctx.arc(0, -8, r * 1.03, math.pi * 1.0, math.pi * 1.95)
        ctx.line_to(40, -40)
        ctx.line_to(-r, -10)
        ctx.close_path()
        remplir(ctx, col, 5)
    elif f == "long":
        ctx.arc(0, -8, r * 1.06, math.pi * 0.95, math.pi * 1.97)
        ctx.line_to(30, -35)
        ctx.line_to(-r, 0)
        ctx.close_path()
        remplir(ctx, col, 5)
    elif f == "chauve":
        ctx.arc(-25, 0, r * 1.0, math.pi * 0.7, math.pi * 1.05)
        ctx.line_to(-r * 0.7, 20)
        ctx.close_path()
        remplir(ctx, col, 4)
    elif f == "casquette":
        ctx.arc(0, -10, r * 1.02, math.pi, 2 * math.pi)
        ctx.close_path()
        remplir(ctx, c("1f3a93"), 5)
        rrect(ctx, 20, -22, 110, 20, 8)
        remplir(ctx, c("1f3a93"), 5)


def chapeau(ctx, r):
    ctx.save()
    ctx.translate(0, -r * 0.55)
    ellipse(ctx, 0, 0, r * 1.55, r * 0.28)
    remplir(ctx, c("8d6e3f"), 5)
    ctx.move_to(-r * 0.85, 0)
    ctx.curve_to(-r * 0.9, -r * 0.9, r * 0.9, -r * 0.9, r * 0.85, 0)
    ctx.close_path()
    remplir(ctx, c("a07c48"), 5)
    ctx.rectangle(-r * 0.86, -r * 0.3, r * 1.72, r * 0.22)
    remplir(ctx, c("5a3d1e"), 3)
    ctx.restore()


def visage(ctx, d, expr, parle, t, look, rouge, graine):
    r = 85
    cligne = ((t + graine * 1.3) % 3.9) < 0.13 and expr not in ("panique", "surpris", "crie")
    grand = expr in ("panique", "surpris", "crie")
    for ex in (8, 52):
        if expr in ("rire", "content") or cligne:
            ctx.set_source_rgba(*OUT)
            ctx.set_line_width(5)
            ctx.arc(ex, -4, 14, math.pi * 1.1, math.pi * 1.9) if not cligne else (
                ctx.move_to(ex - 14, -4), ctx.line_to(ex + 14, -4))
            ctx.stroke()
            continue
        ry = 27 if grand else 22
        ellipse(ctx, ex, -6, 17 if not grand else 20, ry)
        remplir(ctx, (1, 1, 1, 1), 4)
        ir = 9 if grand else 12
        ix, iy = ex + 4 + look[0], -4 + look[1]
        ctx.arc(ix, iy, ir, 0, 2 * math.pi)
        ctx.set_source_rgba(*d["yeux"])
        ctx.fill()
        ctx.arc(ix, iy, ir * 0.5, 0, 2 * math.pi)
        ctx.set_source_rgba(0.05, 0.05, 0.1, 1)
        ctx.fill()
        ctx.arc(ix - 3, iy - 4, 3, 0, 2 * math.pi)
        ctx.set_source_rgba(1, 1, 1, 1)
        ctx.fill()
    # sourcils
    ctx.set_source_rgba(*fonce(d["cheveux"], 0.6))
    ctx.set_line_width(6)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for ex, sgn in ((8, -1), (52, 1)):
        hy = -38 if grand else -32
        if expr in ("triste", "gene"):
            ctx.move_to(ex - 13, hy + 4 * sgn * -1 - 2)
            ctx.line_to(ex + 13, hy - 4 * sgn * -1 - 2)
        elif expr == "fache":
            ctx.move_to(ex - 13, hy - 4 * sgn)
            ctx.line_to(ex + 13, hy + 4 * sgn)
        else:
            ctx.move_to(ex - 13, hy + 2)
            ctx.line_to(ex + 13, hy - 1)
        ctx.stroke()
    if d.get("lunettes"):
        ctx.set_source_rgba(*OUT)
        ctx.set_line_width(4)
        for ex in (8, 52):
            ctx.arc(ex + 2, -5, 21, 0, 2 * math.pi)
            ctx.stroke()
        ctx.move_to(22, -8)
        ctx.line_to(38, -8)
        ctx.stroke()
    # joues
    if rouge > 0:
        for ex in (-6, 66):
            ellipse(ctx, ex, 24, 16, 9)
            ctx.set_source_rgba(0.95, 0.3, 0.3, 0.55 * rouge)
            ctx.fill()
    # nez
    ctx.arc(76, 16, 10, 0, 2 * math.pi)
    remplir(ctx, fonce(d["peau"], 0.9), 4)
    if d.get("moustache"):
        ctx.move_to(40, 36)
        ctx.curve_to(55, 22, 80, 22, 92, 38)
        ctx.curve_to(78, 32, 60, 34, 40, 36)
        remplir(ctx, c("5d4037"), 3)
    # bouche
    mx, my = 50, 50
    ouv = 0
    if parle:
        ouv = 0.25 + 0.75 * abs(math.sin(t * 17 + graine))
    if expr in ("rire", "crie", "panique") or ouv > 0.3 or expr == "surpris":
        o = {"rire": 1.0, "crie": 1.1, "panique": 0.9, "surpris": 0.7}.get(expr, 0)
        o = max(o, ouv)
        ctx.save()
        ctx.translate(mx, my)
        if expr == "panique":
            ctx.move_to(-22, -4)
            ctx.curve_to(-10, -14, 12, -14, 24, -6)
            ctx.line_to(20, 16 * o)
            ctx.curve_to(8, 22 * o, -10, 22 * o, -20, 14 * o)
            ctx.close_path()
        elif expr == "rire":
            ctx.move_to(-24, -6)
            ctx.line_to(24, -6)
            ctx.curve_to(22, 28, -22, 28, -24, -6)
            ctx.close_path()
        else:
            ellipse(ctx, 0, 2, 13 + 4 * o, 5 + 14 * o)
        remplir(ctx, c("7b1f1f"), 4)
        ctx.restore()
    elif expr in ("sourire", "content"):
        ctx.set_source_rgba(*OUT)
        ctx.set_line_width(5)
        ctx.arc(mx, my - 14, 18, math.pi * 0.2, math.pi * 0.8)
        ctx.stroke()
    elif expr in ("triste", "gene"):
        ctx.set_source_rgba(*OUT)
        ctx.set_line_width(5)
        if expr == "gene":
            ctx.move_to(mx - 16, my)
            ctx.curve_to(mx - 8, my - 6, mx, my + 6, mx + 8, my)
            ctx.curve_to(mx + 12, my - 4, mx + 16, my, mx + 18, my - 2)
        else:
            ctx.arc_negative(mx, my + 16, 16, -math.pi * 0.2, -math.pi * 0.8)
        ctx.stroke()
    else:
        ctx.set_source_rgba(*OUT)
        ctx.set_line_width(5)
        ctx.move_to(mx - 12, my)
        ctx.line_to(mx + 12, my)
        ctx.stroke()


def perso(ctx, nom, x, y, sc=1.0, dir=1, rot=0.0, pose=None, expr="neutre", parle=False, t=0.0,
          look=(0, 0), rouge=0.0, sueur=False, chap=False, lacets_t=None, poussiere=False):
    """Dessine un personnage pieds en (x, y). Rend les points utiles en coordonnées écran."""
    d = PERSOS[nom]
    pose = pose or p_debout(t)
    graine = sum(map(ord, nom)) % 7
    sc = sc * d.get("taille", 1.0)
    ctx.save()
    ctx.translate(x, y + pose["dy"] * sc)
    ctx.rotate(rot * dir)
    ctx.scale(sc * dir, sc)
    hanche = (0, -190 + pose["drop"])
    lean = pose["lean"]
    epaule = (hanche[0] + 150 * math.sin(lean), hanche[1] - 150 * math.cos(lean))
    ta = lean * 0.6 + pose["tete"]
    tete = (epaule[0] + 100 * math.sin(ta), epaule[1] - 100 * math.cos(ta))
    pts = {}

    def bras(s, e, col):
        a = seg(epaule, s, 78)
        b = seg(a, s + e, 72)
        membre(ctx, [epaule, a, b], 26, col)
        ctx.arc(b[0], b[1], 16, 0, 2 * math.pi)
        remplir(ctx, d["peau"], 5)
        return b

    def jambe(h, k, col):
        a = seg(hanche, h, 96)
        b = seg(a, h + k, 96)
        membre(ctx, [hanche, a, b], 34, col)
        ang = h + k
        ctx.save()
        ctx.translate(*b)
        ctx.rotate(-ang)
        ellipse(ctx, 16, 6, 34, 17)
        remplir(ctx, d["chaussures"], 5)
        ctx.rectangle(-18, 10, 68, 7)
        ctx.set_source_rgba(1, 1, 1, 0.9)
        ctx.fill()
        if d.get("lacets") and lacets_t is not None:
            ctx.set_source_rgba(1, 1, 1, 1)
            ctx.set_line_width(4)
            for k2 in (0, 1):
                ctx.move_to(14, -8)
                ctx.curve_to(-10, 8 + 14 * math.sin(lacets_t * 20 + k2 * 2),
                             -26, 20 + 8 * k2, -44 - 6 * k2, 16 + 10 * math.sin(lacets_t * 15 + k2))
                ctx.stroke()
        ctx.restore()
        return b

    # sac à dos
    if d.get("sac"):
        ctx.save()
        ctx.translate(*hanche)
        ctx.rotate(-lean)
        rrect(ctx, -110, -150, 70, 115, 18)
        remplir(ctx, d["sac"], 5)
        ctx.restore()
    pts["main_g"] = bras(pose["sl"], pose["el"], fonce(d["haut"]))
    jambe(pose["hl"], pose["kl"], fonce(d["bas"]))
    jambe(pose["hr"], pose["kr"], d["bas"])
    # buste
    ctx.save()
    ctx.translate(*hanche)
    ctx.rotate(-lean)
    rrect(ctx, -58, -165, 116, 185, 34)
    remplir(ctx, d["haut"], 6)
    ctx.move_to(-20, -160)
    ctx.line_to(0, -130)
    ctx.line_to(20, -160)
    ctx.set_source_rgba(1, 1, 1, 0.85)
    ctx.set_line_width(7)
    ctx.stroke()
    if nom == "bastien":
        rrect(ctx, -30, -60, 60, 32, 10)
        ctx.set_source_rgba(*fonce(d["haut"], 0.85))
        ctx.fill()
    if d.get("sifflet"):
        ctx.set_source_rgba(0.9, 0.9, 0.9, 1)
        ctx.set_line_width(3)
        ctx.move_to(-20, -160)
        ctx.line_to(20, -90)
        ctx.line_to(20, -160)
        ctx.stroke()
        rrect(ctx, 10, -95, 26, 14, 5)
        remplir(ctx, c("bdc3c7"), 3)
    if poussiere:
        rr = random.Random(graine)
        for _ in range(9):
            ctx.arc(rr.uniform(-50, 50), rr.uniform(-150, 10), rr.uniform(5, 11), 0, 2 * math.pi)
            ctx.set_source_rgba(0.55, 0.42, 0.28, 0.6)
            ctx.fill()
    ctx.restore()
    # tête
    ctx.save()
    ctx.translate(*tete)
    ctx.rotate(-ta)
    dessiner_cheveux_arriere(ctx, d, 85)
    ellipse(ctx, -18, 8, 18, 22)
    remplir(ctx, d["peau"], 5)
    ctx.arc(0, 0, 85, 0, 2 * math.pi)
    remplir(ctx, d["peau"], 6)
    dessiner_cheveux_avant(ctx, d, 85)
    visage(ctx, d, expr, parle, t, look, rouge, graine)
    if sueur:
        yy = -20 + (t * 60) % 60
        ctx.move_to(-45, yy - 22)
        ctx.curve_to(-35, yy - 5, -30, yy + 8, -45, yy + 10)
        ctx.curve_to(-60, yy + 8, -55, yy - 5, -45, yy - 22)
        remplir(ctx, c("a8dcff"), 3, c("2e6da4"))
    if chap:
        chapeau(ctx, 85)
    pts["tete"] = ctx.user_to_device(0, 0)
    pts["haut"] = ctx.user_to_device(0, -95)
    ctx.restore()
    pts["main_d"] = bras(pose["sr"], pose["er"], d["haut"])
    pts["main_g"] = ctx.user_to_device(*pts["main_g"])
    pts["main_d"] = ctx.user_to_device(*pts["main_d"])
    ctx.restore()
    return pts


# ------------------------------------------------------------ objets
def cahier(ctx, x, y, rot, col):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    rrect(ctx, -36, -26, 72, 52, 5)
    remplir(ctx, col, 4)
    for i in range(3):
        ctx.rectangle(-26, -12 + i * 10, 50, 3)
        ctx.set_source_rgba(1, 1, 1, 0.7)
        ctx.fill()
    ctx.restore()


def stylo(ctx, x, y, rot, col):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    rrect(ctx, -30, -5, 60, 10, 4)
    remplir(ctx, col, 3)
    ctx.move_to(30, -5)
    ctx.line_to(42, 0)
    ctx.line_to(30, 5)
    remplir(ctx, c("f5deb3"), 2)
    ctx.restore()


def pomme(ctx, x, y, rot, r=24):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.save()
    ctx.rectangle(-100, -100, 200, 200)
    ctx.arc(r * 1.05, -r * 0.1, r * 0.55, 0, 2 * math.pi)
    ctx.set_fill_rule(cairo.FILL_RULE_EVEN_ODD)
    ctx.clip()
    ctx.arc(0, 0, r, 0, 2 * math.pi)
    remplir(ctx, c("d62c2c"), 4)
    ctx.restore()
    ctx.move_to(0, -r)
    ctx.line_to(3, -r - 12)
    ctx.set_source_rgba(*OUT)
    ctx.set_line_width(4)
    ctx.stroke()
    ellipse(ctx, 10, -r - 10, 9, 5)
    remplir(ctx, c("27ae60"), 2)
    ctx.restore()


def calecon(ctx, x, y, rot, s=1.0):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.scale(s, s)
    ctx.move_to(-45, -30)
    ctx.line_to(45, -30)
    ctx.line_to(50, 25)
    ctx.line_to(12, 28)
    ctx.line_to(0, 5)
    ctx.line_to(-12, 28)
    ctx.line_to(-50, 25)
    ctx.close_path()
    remplir(ctx, c("e74c3c"), 4)
    ctx.rectangle(-45, -30, 90, 10)
    remplir(ctx, (1, 1, 1, 1), 3)
    for hx, hy in ((-28, 2), (26, 4), (0, -8)):
        ctx.move_to(hx, hy + 6)
        ctx.curve_to(hx - 12, hy - 4, hx - 4, hy - 12, hx, hy - 4)
        ctx.curve_to(hx + 4, hy - 12, hx + 12, hy - 4, hx, hy + 6)
        ctx.set_source_rgba(1, 1, 1, 1)
        ctx.fill()
    ctx.restore()


def plateau(ctx, x, y, rot):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    rrect(ctx, -60, -8, 120, 16, 5)
    remplir(ctx, c("95a5a6"), 4)
    ctx.arc(-25, -22, 16, 0, 2 * math.pi)
    remplir(ctx, c("f39c12"), 3)
    ctx.arc(22, -20, 13, 0, 2 * math.pi)
    remplir(ctx, c("27ae60"), 3)
    ctx.restore()


def haie(ctx, x, y, rot=0.0):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    for px in (-70, 70):
        ctx.rectangle(px - 5, -130, 10, 130)
        remplir(ctx, c("dddddd"), 3)
    for i in range(6):
        ctx.rectangle(-80 + i * 26.7, -140, 26.7, 22)
        ctx.set_source_rgba(*(c("e74c3c") if i % 2 == 0 else (1, 1, 1, 1)))
        ctx.fill()
    ctx.rectangle(-80, -140, 160, 22)
    ctx.set_source_rgba(*OUT)
    ctx.set_line_width(4)
    ctx.stroke()
    ctx.restore()


def plot(ctx, x, y, rot=0.0):
    ctx.save()
    ctx.translate(x, y)
    ctx.rotate(rot)
    ctx.move_to(-28, 0)
    ctx.line_to(0, -70)
    ctx.line_to(28, 0)
    ctx.close_path()
    remplir(ctx, c("f39c12"), 4)
    ctx.rectangle(-17, -38, 34, 10)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.fill()
    rrect(ctx, -38, -6, 76, 10, 3)
    remplir(ctx, c("e67e22"), 3)
    ctx.restore()


def banc(ctx, x, y, larg):
    for px in (x + 30, x + larg - 30):
        ctx.rectangle(px - 8, y, 16, SOL - y)
        remplir(ctx, c("5d4037"), 4)
    rrect(ctx, x, y - 22, larg, 26, 6)
    remplir(ctx, c("a0522d"), 5)
    rrect(ctx, x + 10, y - 90, larg - 20, 22, 6)
    remplir(ctx, c("8b4513"), 5)
    for px in (x + 40, x + larg - 40):
        ctx.rectangle(px - 6, y - 90, 12, 70)
        remplir(ctx, c("5d4037"), 3)


def boum(ctx, x, y, t, mot="BAM !", taille=110):
    if t < 0 or t > 0.9:
        return
    k = rebond(t / 0.18)
    a = 1 - lin(t, 0.65, 0.9)
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(k, k)
    ctx.rotate(-0.12)
    n = 14
    for i in range(2 * n + 1):
        ang = i * math.pi / n
        rr = 190 if i % 2 == 0 else 120
        ctx.line_to(math.cos(ang) * rr * 1.25, math.sin(ang) * rr * 0.8)
    ctx.close_path()
    ctx.push_group()
    remplir(ctx, c("ffe135"), 7, c("e03a1e"))
    texte(ctx, mot, 0, taille * 0.35, taille, c("e03a1e"), (1, 1, 1, 1), 10)
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)
    ctx.restore()


# ------------------------------------------------------------ texte à l'écran
def bulle(ctx, txt, tip, dt, taille=36, larg=640, cri=None):
    if dt < 0:
        return
    police(ctx, taille)
    lignes = couper(ctx, txt, larg)
    lh = taille * 1.28
    w = max(ctx.text_extents(l).x_advance for l in lignes) + 64
    h = len(lignes) * lh + 36
    x = min(max(tip[0] - w / 2, 20), W - 20 - w)
    y = max(tip[1] - h - 60, 16)
    if cri is None:
        cri = txt.upper() == txt and any(ch.isalpha() for ch in txt)
    k = rebond(dt / 0.25)
    ctx.save()
    ctx.translate(tip[0], tip[1])
    ctx.scale(k, k)
    ctx.translate(-tip[0], -tip[1])
    bx = min(max(tip[0], x + 50), x + w - 50)
    ctx.move_to(bx - 22, y + h - 4)
    ctx.line_to(tip[0], tip[1] - 10)
    ctx.line_to(bx + 22, y + h - 4)
    if cri:
        pts = []
        per = 2 * (w + h)
        n = int(per / 34)
        for i in range(n):
            s = i / n * per
            if s < w:
                px, py = x + s, y
            elif s < w + h:
                px, py = x + w, y + s - w
            elif s < 2 * w + h:
                px, py = x + w - (s - w - h), y + h
            else:
                px, py = x, y + h - (s - 2 * w - h)
            cx, cy = x + w / 2, y + h / 2
            f = 1.0 if i % 2 == 0 else 0.86
            pts.append((cx + (px - cx) * (1.08 if f == 1 else 0.96), cy + (py - cy) * (1.18 if f == 1 else 0.96)))
        ctx.new_sub_path()
        for p in pts:
            ctx.line_to(*p)
        ctx.close_path()
    else:
        rrect(ctx, x, y, w, h, 34)
    ctx.set_fill_rule(cairo.FILL_RULE_WINDING)
    remplir(ctx, (1, 1, 1, 1), 5)
    n = int(dt * 34)
    police(ctx, taille)
    ctx.set_source_rgba(0.1, 0.1, 0.15, 1)
    for i, l in enumerate(lignes):
        part = l[:max(0, n)]
        n -= len(l) + 1
        ctx.move_to(x + 32, y + 18 + taille + i * lh - 4)
        ctx.show_text(part)
    ctx.restore()


def legende(ctx, txt, dt, duree):
    if dt < 0 or dt > duree:
        return
    a = min(1, dt / 0.3, (duree - dt) / 0.3)
    police(ctx, 40, gras=False)
    lignes = couper(ctx, txt, 1500)
    lh = 52
    h = len(lignes) * lh + 36
    ctx.push_group()
    rrect(ctx, 150, H - 40 - h, W - 300, h, 18)
    ctx.set_source_rgba(0.08, 0.06, 0.12, 0.8)
    ctx.fill()
    police(ctx, 40, gras=False)
    for i, l in enumerate(lignes):
        e = ctx.text_extents(l)
        ctx.move_to(W / 2 - e.x_advance / 2, H - 40 - h + 18 + 40 + i * lh)
        ctx.set_source_rgba(1, 0.97, 0.85, 1)
        ctx.show_text(l)
    ctx.pop_group_to_source()
    ctx.paint_with_alpha(a)


class Script:
    """Dialogues et légendes d'une scène, enchaînés automatiquement."""

    def __init__(self):
        self.dial, self.leg, self.sfx = [], [], []

    def dit(self, t0, qui, txt, duree=None):
        d = duree or max(1.7, 0.9 + len(txt) / 15)
        self.dial.append((t0, t0 + d, qui, txt))
        self.sfx.append((t0, "pop"))
        return t0 + d

    def suite(self, t0, repliques, pause=0.15):
        t = t0
        for r in repliques:
            t = self.dit(t, *r) + pause
        return t

    def raconte(self, t0, txt, duree=None):
        d = duree or max(2.5, 1.2 + len(txt) / 17)
        self.leg.append((t0, t0 + d, txt))
        return t0 + d

    def parle(self, qui, t):
        return any(q == qui and a <= t < a + len(x) / 34 + 0.35 for a, b, q, x in self.dial)

    def dessiner(self, ctx, t, tetes):
        for a, b, q, x in self.dial:
            if a <= t < b and q in tetes:
                bulle(ctx, x, tetes[q], t - a)
        for a, b, x in self.leg:
            legende(ctx, x, t - a, b - a)


# ------------------------------------------------------------ décors
def degrade(ctx, c1, c2, y0=0, y1=H):
    g = cairo.LinearGradient(0, y0, 0, y1)
    g.add_color_stop_rgba(0, *c1)
    g.add_color_stop_rgba(1, *c2)
    ctx.rectangle(0, y0, W, y1 - y0)
    ctx.set_source(g)
    ctx.fill()


def nuage(ctx, x, y, s):
    for dx, dy, r in ((0, 0, 40), (45, -18, 50), (95, 0, 40), (45, 12, 42)):
        ctx.arc(x + dx * s, y + dy * s, r * s, 0, 2 * math.pi)
        ctx.close_path()
    ctx.set_source_rgba(1, 1, 1, 0.95)
    ctx.fill()


def arbre(ctx, x, y, s=1.0, col=c("3f8f3a")):
    ctx.rectangle(x - 18 * s, y - 180 * s, 36 * s, 180 * s)
    remplir(ctx, c("6d4c41"), 5)
    for dx, dy, r in ((0, -260, 110), (-80, -200, 80), (80, -200, 85), (0, -330, 80)):
        ctx.arc(x + dx * s, y + dy * s, r * s, 0, 2 * math.pi)
        ctx.close_path()
    remplir(ctx, col, 5)


def fond_lycee(ctx, t):
    degrade(ctx, c("6ec3f4"), c("dff4ff"), 0, SOL)
    ctx.arc(1650, 160, 70, 0, 2 * math.pi)
    ctx.set_source_rgba(*c("ffe066"))
    ctx.fill()
    for i, (x0, y0, s) in enumerate(((100, 140, 1.0), (700, 90, 0.8), (1300, 200, 1.1))):
        nuage(ctx, (x0 + t * 25 * (i + 1)) % (W + 300) - 150, y0, s)
    arbre(ctx, 130, SOL, 1.1)
    arbre(ctx, 1790, SOL, 1.0, c("4caf50"))
    ctx.rectangle(0, SOL, W, H - SOL)
    ctx.set_source_rgba(*c("7bc043"))
    ctx.fill()
    ctx.move_to(820, H)
    ctx.line_to(900, SOL)
    ctx.line_to(1020, SOL)
    ctx.line_to(1100, H)
    ctx.set_source_rgba(*c("c8c2b4"))
    ctx.fill()
    ctx.rectangle(300, 300, 1320, SOL - 300)
    remplir(ctx, c("f1d9a7"), 7)
    ctx.move_to(270, 305)
    ctx.line_to(960, 170)
    ctx.line_to(1650, 305)
    ctx.close_path()
    remplir(ctx, c("b0503a"), 7)
    for col in range(6):
        for row in range(3):
            if row == 2 and col in (2, 3):
                continue
            x = 360 + col * 205
            y = 360 + row * 170
            ctx.rectangle(x, y, 130, 110)
            remplir(ctx, c("9fd3f5"), 6)
            ctx.move_to(x + 65, y)
            ctx.line_to(x + 65, y + 110)
            ctx.stroke()
    ctx.rectangle(880, 700, 160, 200)
    remplir(ctx, c("7b4a2a"), 6)
    rrect(ctx, 700, 610, 520, 70, 10)
    remplir(ctx, c("c0392b"), 6)
    texte(ctx, "LYCÉE JEAN MOULIN", 960, 660, 40, (1, 1, 1, 1))


def fond_couloir(ctx, camx):
    ctx.rectangle(0, 0, W, 640)
    ctx.set_source_rgba(*c("f5e6c8"))
    ctx.fill()
    ctx.rectangle(0, 640, W, SOL - 640)
    ctx.set_source_rgba(*c("5d9c7c"))
    ctx.fill()
    ctx.rectangle(0, 632, W, 12)
    ctx.set_source_rgba(*c("3f7a5c"))
    ctx.fill()
    for i in range(-2, 16):
        x = i * 160 - (camx % 160)
        ctx.rectangle(x, SOL, 80, H - SOL)
        ctx.set_source_rgba(*c("d9d2c5"))
        ctx.fill()
        ctx.rectangle(x + 80, SOL, 80, H - SOL)
        ctx.set_source_rgba(*c("bfb6a6"))
        ctx.fill()
    for i in range(-1, 14):
        x = i * 900 - camx
        if x < -900 or x > W + 50:
            continue
        # porte de classe
        ctx.rectangle(x + 40, 340, 210, SOL - 340)
        remplir(ctx, c("b5651d"), 6)
        ctx.rectangle(x + 80, 380, 130, 120)
        remplir(ctx, c("cfe9f7"), 5)
        ctx.arc(x + 220, 640, 10, 0, 2 * math.pi)
        remplir(ctx, c("f1c40f"), 3)
        rrect(ctx, x + 70, 280, 150, 44, 6)
        remplir(ctx, (1, 1, 1, 1), 4)
        texte(ctx, f"Salle {10 + i}", x + 145, 313, 26, c("333333"))
        # casiers
        for j in range(4):
            lx = x + 330 + j * 130
            ctx.rectangle(lx, 380, 120, SOL - 380)
            remplir(ctx, c("2f6fb5"), 5)
            for k in range(4):
                ctx.rectangle(lx + 30, 410 + k * 14, 60, 5)
                ctx.set_source_rgba(0, 0, 0, 0.35)
                ctx.fill()
            ctx.rectangle(lx + 95, 600, 10, 30)
            ctx.set_source_rgba(0.9, 0.9, 0.9, 1)
            ctx.fill()
        # affiche
        rrect(ctx, x + 380, 150, 220, 160, 6)
        remplir(ctx, c("fff3b0"), 4)
        texte(ctx, "CLUB", x + 490, 205, 30, c("c0392b"))
        texte(ctx, "THÉÂTRE", x + 490, 250, 30, c("c0392b"))
    for i in range(-1, 8):
        x = i * 450 - (camx * 1.0) % 450
        rrect(ctx, x + 100, 20, 260, 26, 10)
        ctx.set_source_rgba(1, 1, 0.9, 1)
        ctx.fill()


def fond_terrain(ctx, t):
    degrade(ctx, c("79c7f2"), c("e3f6ff"), 0, 640)
    for i, (x0, y0, s) in enumerate(((150, 120, 0.9), (900, 80, 0.7), (1500, 160, 1.0))):
        nuage(ctx, (x0 + t * 18 * (i + 1)) % (W + 300) - 150, y0, s)
    ctx.rectangle(0, 470, W, 180)
    ctx.set_source_rgba(*c("c9a27e"))
    ctx.fill()
    ctx.rectangle(60, 380, 520, 200)
    remplir(ctx, c("e9d3a6"), 6)
    texte(ctx, "GYMNASE", 320, 450, 40, c("8e5a2b"))
    for x in range(700, 1900, 60):
        ctx.rectangle(x, 560, 8, 90)
        ctx.set_source_rgba(0.5, 0.5, 0.55, 1)
        ctx.fill()
    ctx.rectangle(700, 560, 1220, 6)
    ctx.fill()
    ctx.rectangle(0, 640, W, H - 640)
    ctx.set_source_rgba(*c("6ab04c"))
    ctx.fill()
    for i in range(8):
        ctx.rectangle(0, 640 + i * 60, W, 30)
        ctx.set_source_rgba(1, 1, 1, 0.06)
        ctx.fill()
    ctx.rectangle(0, SOL + 10, W, 6)
    ctx.set_source_rgba(1, 1, 1, 0.8)
    ctx.fill()


def portique(ctx, x):
    for px in (x - 150, x + 150):
        ctx.rectangle(px - 10, 110, 20, SOL - 110)
        remplir(ctx, c("7f8c8d"), 5)
    ctx.rectangle(x - 170, 100, 340, 22)
    remplir(ctx, c("95a5a6"), 5)


def corde(ctx, x, ang, long=700):
    fin = seg((x, 120), ang, long)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for lw, col in ((22, OUT), (14, c("c8a165"))):
        ctx.move_to(x, 120)
        ctx.line_to(*fin)
        ctx.set_source_rgba(*col)
        ctx.set_line_width(lw)
        ctx.stroke()
    for k in range(1, 7):
        p = seg((x, 120), ang, long * k / 7)
        ctx.arc(p[0], p[1], 11, 0, 2 * math.pi)
        remplir(ctx, c("a57c43"), 3)


def fond_cour(ctx, t, soir=0.0):
    ciel_haut = tuple(mix(a, b, soir) for a, b in zip(c("7cc6f2"), c("3b2f6b")))
    ciel_bas = tuple(mix(a, b, soir) for a, b in zip(c("e2f5ff"), c("ff9f68")))
    degrade(ctx, ciel_haut, ciel_bas, 0, 700)
    ctx.arc(1500, mix(150, 560, soir), 80, 0, 2 * math.pi)
    ctx.set_source_rgba(*(c("ffe066") if soir < 0.5 else c("ffcf5c")))
    ctx.fill()
    ctx.rectangle(0, 420, W, 280)
    ctx.set_source_rgba(*tuple(mix(a, b, soir) for a, b in zip(c("e8cf9c"), c("8a5a6b"))))
    ctx.fill()
    for col in range(9):
        ctx.rectangle(60 + col * 210, 470, 110, 90)
        ctx.set_source_rgba(*tuple(mix(a, b, soir) for a, b in zip(c("9fd3f5"), c("ffd27a"))))
        ctx.fill()
    ctx.rectangle(0, 690, W, H - 690)
    ctx.set_source_rgba(*tuple(mix(a, b, soir) for a, b in zip(c("cfc6b5"), c("a07a70"))))
    ctx.fill()
    arbre(ctx, 260, SOL - 40, 1.25, tuple(mix(a, b, soir) for a, b in zip(c("3f8f3a"), c("5b4a3a"))))


def fond_bd(ctx, col1, col2):
    degrade(ctx, col1, col2)
    ctx.set_source_rgba(1, 1, 1, 0.08)
    for yy in range(0, H, 36):
        for xx in range(0, W, 36):
            ctx.arc(xx + (yy // 36 % 2) * 18, yy, 6, 0, 2 * math.pi)
            ctx.fill()


def cadre_bd(ctx, x, y, w, h, apparition, dessin, titre):
    if apparition <= 0:
        return
    k = rebond(apparition / 0.35)
    ctx.save()
    ctx.translate(x + w / 2, y + h / 2)
    ctx.scale(k, k)
    ctx.rotate(0.02 * math.sin(x))
    ctx.translate(-w / 2, -h / 2)
    ctx.rectangle(8, 12, w, h)
    ctx.set_source_rgba(0, 0, 0, 0.35)
    ctx.fill()
    ctx.rectangle(0, 0, w, h)
    ctx.set_source_rgba(1, 1, 1, 1)
    ctx.fill()
    ctx.save()
    ctx.rectangle(0, 0, w, h)
    ctx.clip()
    dessin(ctx, w, h, apparition)
    ctx.restore()
    ctx.rectangle(0, 0, w, h)
    ctx.set_source_rgba(*OUT)
    ctx.set_line_width(8)
    ctx.stroke()
    rrect(ctx, 20, h - 80, w - 40, 60, 12)
    remplir(ctx, c("ffe135"), 5)
    texte(ctx, titre, w / 2, h - 38, 32, c("222222"))
    ctx.restore()


# ------------------------------------------------------------ scènes
SCENES = []


def scene(duree):
    def deco(f):
        SCENES.append([f, duree, Script()])
        return f
    return deco


def rires(ctx, t, pts):
    for i, (x, y) in enumerate(pts):
        a = 0.6 + 0.4 * math.sin(t * 9 + i)
        texte(ctx, "HA HA !", x, y - 30 * abs(math.sin(t * 8 + i)), 44,
              (1, 0.5, 0.1, a), (1, 1, 1, a), 6)


# 0 — titre
@scene(7.0)
def s_titre(ctx, t, S):
    fond_bd(ctx, c("1e2a78"), c("3c55c7"))
    k = rebond((t - 0.3) / 0.5)
    ctx.save()
    ctx.translate(W / 2, 330)
    ctx.scale(k, k)
    texte(ctx, "Les détectives", 0, -40, 120, c("ffd84d"), c("7a3b00"), 14)
    texte(ctx, "maladroits", 0, 110, 150, c("ffb22e"), c("7a3b00"), 16)
    ctx.restore()
    if t > 1.4:
        k2 = rebond((t - 1.4) / 0.4)
        ctx.save()
        ctx.translate(W / 2, 560)
        ctx.scale(k2, k2)
        rrect(ctx, -680, -55, 1360, 110, 20)
        remplir(ctx, c("c2185b"), 6)
        texte(ctx, "Chapitre 1 — Deux catastrophes se rencontrent", 0, 16, 46, (1, 1, 1, 1))
        ctx.restore()
    y0 = H + 520 - 540 * prog(t, 2.0, 2.6)
    perso(ctx, "bastien", 190, y0, 0.95, 1, pose=P(sl=2.7 + 0.4 * math.sin(t * 9), el=0.4),
          expr="sourire", t=t)
    y1 = H + 520 - 540 * prog(t, 2.4, 3.0)
    perso(ctx, "lucie", 1730, y1, 0.95, -1, pose=P(sl=2.7 + 0.4 * math.sin(t * 9 + 1), el=0.4),
          expr="content", t=t)


# 1 — le lycée
@scene(7.0)
def s_lycee(ctx, t, S):
    z = 1 + 0.05 * t / 7
    ctx.save()
    ctx.translate(W / 2, H / 2)
    ctx.scale(z, z)
    ctx.translate(-W / 2, -H / 2)
    fond_lycee(ctx, t)
    ctx.restore()
    k = rebond((t - 0.4) / 0.4)
    ctx.save()
    ctx.translate(W / 2, 110)
    ctx.scale(k, k)
    rrect(ctx, -520, -60, 1040, 120, 20)
    remplir(ctx, c("1e2a78", 0.9), 6)
    texte(ctx, "Il y a 10 ans — Lycée Jean Moulin — Septembre", 0, 16, 44, (1, 1, 1, 1))
    ctx.restore()


SCENES[-1][2].sfx += [(0.5, "cloche")]


# 2 — le retard
@scene(12.0)
def s_retard(ctx, t, S):
    fond_bd(ctx, c("f39c12"), c("e74c3c"))

    def reveil(ctx, w, h, a):
        degrade(ctx, c("dfe6e9"), c("b2bec3"), 0, h)
        cx, cy = w / 2, h / 2 - 40
        sh = 6 * math.sin(a * 60)
        for s in (-1, 1):
            ctx.arc(cx + s * 70 + sh, cy - 90, 34, 0, 2 * math.pi)
            remplir(ctx, c("f1c40f"), 5)
        ctx.arc(cx + sh, cy, 110, 0, 2 * math.pi)
        remplir(ctx, c("e74c3c"), 7)
        ctx.arc(cx + sh, cy, 85, 0, 2 * math.pi)
        remplir(ctx, (1, 1, 1, 1), 5)
        ctx.set_line_width(8)
        ctx.set_source_rgba(*OUT)
        ctx.move_to(cx + sh, cy)
        ctx.line_to(cx + sh, cy - 60)
        ctx.move_to(cx + sh, cy)
        ctx.line_to(cx + sh + 45, cy + 20)
        ctx.stroke()
        texte(ctx, "OFF", cx + 150, cy - 120, 50, c("c0392b"), (1, 1, 1, 1), 6)

    def chaussures(ctx, w, h, a):
        degrade(ctx, c("ffeaa7"), c("fdcb6e"), 0, h)
        ctx.save()
        ctx.translate(w / 2 - 60, h / 2)
        ctx.rotate(-0.2)
        ellipse(ctx, 0, 0, 90, 40)
        remplir(ctx, c("d64541"), 6)
        ctx.restore()
        ellipse(ctx, w / 2 + 110, h / 2 + 30, 60, 26)
        remplir(ctx, (1, 1, 1, 1), 5)
        for i, (qx, qy) in enumerate(((120, 110), (w - 110, 140), (w / 2, 80))):
            texte(ctx, "?", qx, qy + 10 * math.sin(a * 6 + i), 90, c("6c5ce7"), (1, 1, 1, 1), 8)

    def bus(ctx, w, h, a):
        degrade(ctx, c("81ecec"), c("dff9fb"), 0, h)
        ctx.rectangle(0, h - 170, w, 170)
        ctx.set_source_rgba(*c("636e72"))
        ctx.fill()
        bx = 120 + a * 160
        rrect(ctx, bx, h - 360, 380, 190, 20)
        remplir(ctx, c("fdcb6e"), 6)
        for i in range(4):
            ctx.rectangle(bx + 30 + i * 85, h - 330, 65, 60)
            remplir(ctx, c("74b9ff"), 4)
        for wx in (bx + 80, bx + 300):
            ctx.arc(wx, h - 170, 36, 0, 2 * math.pi)
            remplir(ctx, c("2d3436"), 5)
        for i in range(3):
            ctx.arc(bx - 30 - i * 40, h - 200 + i * 10, 22 + i * 8, 0, 2 * math.pi)
            ctx.set_source_rgba(0.8, 0.8, 0.8, 0.6)
            ctx.fill()
        perso(ctx, "bastien", 60 + a * 60, h - 140, 0.42, 1, pose=p_course(a * 3), expr="panique", t=a * 3)

    cadre_bd(ctx, 110, 150, 520, 560, t - 3.0, reveil, "Réveil oublié")
    cadre_bd(ctx, 700, 150, 520, 560, t - 5.2, chaussures, "Chaussures introuvables")
    cadre_bd(ctx, 1290, 150, 520, 560, t - 7.4, bus, "Bus raté")
    S.dessiner(ctx, t, {})


SCENES[-1][2].raconte(0.2, "Bastien était en retard. Encore.", 2.6)
SCENES[-1][2].raconte(3.0, "Ce n'était même pas sa faute cette fois. Enfin... pas complètement.", 2.2)
SCENES[-1][2].raconte(5.2, "Il avait oublié de mettre son réveil. Et ensuite, il n'avait pas trouvé ses chaussures.", 2.2)
SCENES[-1][2].raconte(7.4, "Et ENSUITE, il avait raté le bus.", 4.4)
SCENES[-1][2].sfx += [(3.0, "pop"), (5.2, "pop"), (7.4, "pop"), (7.6, "whoosh")]


def pos_course(t, depart, v0, v1, t_acc):
    if t < t_acc:
        return depart + v0 * t
    return depart + v0 * t_acc + v1 * (t - t_acc) + 120 * (t - t_acc) ** 2


# 3 — la course dans le couloir
@scene(10.0)
def s_couloir(ctx, t, S):
    bx = pos_course(t, -150, 330, 480, 6.2)
    camx = max(0, bx - 900)
    fond_couloir(ctx, camx)
    sv = 1350 - camx
    pts_s = perso(ctx, "surveillant", sv, SOL, 0.95, -1, pose=p_debout(t) if not (1.8 < t < 5.2) else
                  P(sr=1.9 + 0.3 * math.sin(t * 12), er=0.3), expr="fache" if 1.8 < t < 5.2 else "neutre",
                  parle=S.parle("surveillant", t), t=t)
    v = 1.0 if t < 6.2 else 1.5
    pb = perso(ctx, "bastien", bx - camx, SOL, 0.95, 1, pose=p_course(t, v), expr="panique", t=t,
               sueur=True, lacets_t=t)
    rr = random.Random(int(t * 3))
    for i in range(3):
        ph = (t * 1.7 + i / 3) % 1
        px = bx - camx - 150 - ph * 300
        py = SOL - 330 + ph * 250 + 30 * math.sin(t * 5 + i)
        ctx.save()
        ctx.translate(px, py)
        ctx.rotate(t * 4 + i)
        ctx.rectangle(-26, -18, 52, 36)
        remplir(ctx, (1, 1, 1, 1), 3)
        ctx.restore()
    S.dessiner(ctx, t, {"surveillant": pts_s["haut"], "bastien": pb["haut"]})


SC = SCENES[-1]
SC[2] = Script()
SC[2].raconte(0.2, "Il courait dans les couloirs du lycée comme un dératé, son sac à dos à moitié ouvert et ses lacets défaits.", 4.2)
SC[2].dit(2.0, "surveillant", "RALENTISSEZ DANS LES COULOIRS !", 3.0)
SC[2].raconte(6.0, "Bastien accéléra. Mauvaise idée.", 3.8)
SC[2].sfx += [(0.0, "course")]


# 4 — la chute
CHUTE_X = 1060


@scene(13.0)
def s_chute(ctx, t, S):
    camx = 0
    fond_couloir(ctx, 1500)
    eleves = [("eleve0", 250, 1), ("eleve1", 430, 1), ("eleve3", 1620, -1), ("eleve4", 1790, -1)]
    tetes = {}
    for nom, ex, dr in eleves:
        rit = t > 5.2
        p = p_rire(t + ex) if rit else p_debout(t, ex)
        tetes[nom] = perso(ctx, nom, ex, SOL, 0.85, dr, pose=p, expr="rire" if rit else "neutre",
                           t=t, parle=S.parle(nom, t))["haut"]
    # Bastien : course, moulin, chute, à plat, se relève à genoux
    if t < 0.9:
        x = 760 + 260 * t / 0.9
        pb = perso(ctx, "bastien", x, SOL, 0.95, 1, pose=p_course(t * 0.6), expr="panique", t=t, lacets_t=t)
    elif t < 2.5:
        k = (t - 0.9) / 1.6
        x = 994 + 60 * k
        pb = perso(ctx, "bastien", x, SOL - 20 * math.sin(k * math.pi), 0.95, 1, pose=p_moulin(t),
                   expr="panique", t=t, sueur=True, lacets_t=t)
    elif t < 2.85:
        k = lisse((t - 2.5) / 0.35)
        pb = perso(ctx, "bastien", CHUTE_X - 30, SOL - 40 * k, 0.95, 1, rot=math.pi / 2 * k,
                   pose=fondu_pose(p_moulin(t), p_allonge(), k), expr="panique", t=t)
    elif t < 9.5:
        pb = perso(ctx, "bastien", CHUTE_X - 30, SOL - 40, 0.95, 1, rot=math.pi / 2, pose=p_allonge(),
                   expr="gene" if t > 4.5 else "panique", t=t, rouge=lin(t, 5.0, 6.0))
    else:
        k = lisse((t - 9.5) / 0.6)
        pb = perso(ctx, "bastien", CHUTE_X + 100 * (1 - k) + 60 * k, SOL, 0.95, 1,
                   rot=math.pi / 2 * (1 - k), pose=fondu_pose(p_allonge(), p_accroupi(), k),
                   expr="gene", t=t, rouge=1.0)
    # affaires qui explosent
    if t > 2.85:
        k = lisse((t - 2.85) / 0.9)
        dep = (CHUTE_X + 60, SOL - 120)
        objs = [("cahier", 620, SOL - 20, c("e84393")), ("cahier", 1440, SOL - 18, c("00b894")),
                ("cahier", 880, SOL - 15, c("0984e3")), ("stylo", 720, SOL - 8, c("6c5ce7")),
                ("stylo", 1330, SOL - 8, c("d63031")), ("stylo", 1520, SOL - 6, c("fdcb6e"))]
        for i, (typ, ex, ey, col) in enumerate(objs):
            x = mix(dep[0], ex, k)
            y = mix(dep[1], ey, k) - 260 * math.sin(k * math.pi) * (0.6 + 0.2 * i % 3)
            r = k * (3 + i)
            (cahier if typ == "cahier" else stylo)(ctx, x, y, r, col)
        kp = lisse((t - 2.85) / 1.4)
        pomme(ctx, mix(dep[0], 1330, kp), mix(dep[1], SOL - 24, kp) - 200 * math.sin(kp * math.pi), kp * 9)
        if t < 9.8:
            kc = lisse((t - 3.0) / 1.2)
            tete = (CHUTE_X - 30 + 450 * 0.95, SOL - 40 - 30)
            calecon(ctx, mix(dep[0], tete[0], kc), mix(dep[1], tete[1] - 60, kc) - 420 * math.sin(kc * math.pi),
                    kc * 6.3, 1.1)
        else:
            kc = lisse((t - 9.8) / 0.7)
            calecon(ctx, mix(pb["tete"][0], pb["main_d"][0], kc), mix(pb["tete"][1] - 60, pb["main_d"][1], kc),
                    0, 1.1 * (1 - 0.7 * kc))
    boum(ctx, CHUTE_X + 200, SOL - 260, t - 2.85)
    if 5.2 < t < 12.5:
        rires(ctx, t, [(340, 420), (1700, 420)])
    tetes["bastien"] = pb["haut"]
    S.dessiner(ctx, t, tetes)


SC = SCENES[-1]
SC[2] = Script()
SC[2].raconte(0.3, "Son pied gauche se prit dans son lacet droit. Il trébucha, agita les bras comme un moulin à vent...", 2.5)
SC[2].raconte(3.0, "BAM. Ses affaires explosèrent partout. Cahiers, stylos, une pomme à moitié mangée...", 3.0)
SC[2].raconte(6.1, "... et le caleçon de rechange qu'il gardait « au cas où » depuis la semaine dernière.", 3.4)
SC[2].dit(6.4, "eleve3", "Bravo champion !", 2.6)
SC[2].raconte(9.6, "Bastien, le visage cramoisi, fourra le caleçon tout au fond de son sac.", 3.3)
SC[2].sfx += [(2.85, "bam"), (1.0, "whoosh"), (5.3, "rire"), (9.4, "rire")]


# 5 — la rencontre
@scene(0)
def s_rencontre(ctx, t, S):
    fond_couloir(ctx, 1500)
    for nom, ex, dr in [("eleve0", 250, 1), ("eleve4", 1790, -1)]:
        perso(ctx, nom, ex, SOL, 0.85, dr, pose=p_debout(t, ex), t=t)
    pomme(ctx, 1330, SOL - 24, 9)
    for typ, ex, ey, col, r in [("cahier", 620, SOL - 20, c("e84393"), 0.3), ("stylo", 720, SOL - 8, c("6c5ce7"), 1.2)]:
        (cahier if typ == "cahier" else stylo)(ctx, ex, ey, r, col)
    pb = perso(ctx, "bastien", 900, SOL, 0.95, 1, pose=p_accroupi(), expr="gene" if t < 12 else "sourire",
               parle=S.parle("bastien", t), t=t, rouge=max(0, 1 - t / 8), look=(3, 0))
    if t < 2.2:
        k = t / 2.2
        pl = perso(ctx, "lucie", mix(1950, 1250, k), SOL, 0.95, -1, pose=p_marche(t), expr="sourire", t=t)
    else:
        k = lisse((t - 2.2) / 0.5)
        pose = fondu_pose(p_debout(t), p_accroupi(), k)
        if 2.8 < t < 6.4:
            pose["sr"], pose["er"] = 1.25, 0.1
        pl = perso(ctx, "lucie", 1250, SOL, 0.95, -1, pose=pose,
                   expr="content" if S.parle("lucie", t) is False and t > 10 else "sourire",
                   parle=S.parle("lucie", t), t=t)
        if 2.8 < t < 6.8:
            k2 = lin(t, 5.6, 6.4)
            m = (mix(pl["main_d"][0], pb["main_d"][0], k2), mix(pl["main_d"][1], pb["main_d"][1], k2))
            stylo(ctx, m[0], m[1], 2.6, c("fdcb6e"))
    S.dessiner(ctx, t, {"bastien": pb["haut"], "lucie": pl["haut"]})


SC = SCENES[-1]
S5 = Script()
S5.raconte(0.2, "C'est à ce moment précis qu'une fille s'accroupit à côté de lui pour l'aider.", 3.0)
fin = S5.suite(3.0, [("lucie", "Tiens, t'as échappé celui-là."),
                     ("bastien", "Merci..."),
                     ("lucie", "Première fois que tu tombes aujourd'hui ou c'est un nouveau record ?"),
                     ("bastien", "Très drôle."),
                     ("lucie", "Je m'appelle Lucie. T'es nouveau ?"),
                     ("bastien", "Bastien. Et ouais, je viens d'arriver."),
                     ("lucie", "Bienvenue au lycée Jean Moulin, le temple de l'humiliation publique.")])
SC[1], SC[2] = fin + 0.6, S5


# 6 — la pomme
@scene(14.0)
def s_pomme(ctx, t, S):
    fond_couloir(ctx, 1500)
    for nom, ex, dr in [("eleve0", 250, 1), ("eleve4", 1790, -1)]:
        rit = t > 3.2
        perso(ctx, nom, ex, SOL, 0.85, dr, pose=p_rire(t) if rit else p_debout(t, ex),
              expr="rire" if rit else "surpris", t=t)
    # la pomme glisse
    if t < 1.9:
        pomme(ctx, 1330, SOL - 24, 9)
    else:
        k = lisse((t - 1.9) / 0.8)
        pomme(ctx, mix(1330, 1700, k), SOL - 24, 9 + k * 12)
    if t < 1.2:
        k = lisse(t / 0.6)
        pb = perso(ctx, "bastien", 900, SOL, 0.95, 1, pose=p_accroupi(), expr="sourire", t=t)
        pose_l = fondu_pose(p_accroupi(), P(sr=1.3, er=0.1), k)
        pl = perso(ctx, "lucie", 1250, SOL, 0.95, -1, pose=pose_l, expr="sourire", t=t)
    elif t < 2.2:
        k = lisse((t - 1.2) / 0.5)
        pb = perso(ctx, "bastien", 900, SOL, 0.95, 1, pose=fondu_pose(p_accroupi(), P(sr=1.4, er=0.0, lean=0.2), k),
                   expr="sourire", t=t)
        kk = lin(t, 1.9, 2.2)
        pl = perso(ctx, "lucie", 1250 + 40 * kk, SOL, 0.95, -1, pose=p_moulin(t) if t > 1.9 else P(sr=1.3, er=0.1),
                   expr="panique" if t > 1.9 else "sourire", t=t)
    elif t < 2.7:
        k = lisse((t - 2.2) / 0.5)
        pb = perso(ctx, "bastien", 900, SOL - 40 * k, 0.95, 1, rot=-math.pi / 2 * k,
                   pose=fondu_pose(P(sr=1.4), p_allonge(), k), expr="panique", t=t)
        pl = perso(ctx, "lucie", 1290, SOL - 70 * k, 0.95, -1, rot=math.pi / 2 * k * 0.95,
                   pose=fondu_pose(p_moulin(t), p_allonge(), k), expr="panique", t=t)
    else:
        rit = t > 9.3
        pb = perso(ctx, "bastien", 900, SOL - 40 + (4 * math.sin(t * 20) if rit else 0), 0.95, 1,
                   rot=-math.pi / 2, pose=p_allonge(),
                   expr="rire" if rit else "gene", parle=S.parle("bastien", t), t=t)
        pl = perso(ctx, "lucie", 1290, SOL - 70 + (4 * math.sin(t * 20 + 1) if rit else 0), 0.95, -1,
                   rot=math.pi / 2 * 0.95, pose=p_allonge(),
                   expr="rire" if rit else "gene", parle=S.parle("lucie", t), t=t)
    boum(ctx, 1000, SOL - 300, t - 2.7)
    if 3.2 < t < 6.5:
        rires(ctx, t, [(300, 430), (1720, 430)])
    S.dessiner(ctx, t, {"bastien": (pb["haut"][0] - 30, pb["haut"][1] - 60),
                        "lucie": (pl["haut"][0] + 80, pl["haut"][1] - 90)})


SC = SCENES[-1]
SC[2] = Script()
SC[2].raconte(0.3, "Elle se releva et tendit la main pour l'aider. Bastien l'attrapa.", 1.8)
SC[2].raconte(2.2, "Et c'est là qu'elle glissa. Sur la pomme qu'il avait fait tomber.", 3.5)
SC[2].dit(6.0, "lucie", "Bon début.", 1.7)
SC[2].dit(7.7, "bastien", "Ouais. Magnifique.", 1.8)
SC[2].raconte(9.6, "Ils se regardèrent. Et éclatèrent de rire.", 4.0)
SC[2].sfx += [(1.9, "boing"), (2.7, "bam"), (3.3, "rire"), (9.4, "rire2")]


# 7 — les bulletins
BULLETINS = [
    ("BASTIEN MERCIER", c("3a7bd5"), [
        ("Mathématiques", "7/20", "« Semble perdu dès qu'on dépasse l'addition. »"),
        ("Français", "9/20", "« Créatif mais distrait. Dissertation rendue avec une tache de chocolat. »"),
        ("EPS", "5/20", "« A réussi à se prendre le ballon dans la figure 4 fois en un seul match. »"),
        ("Anglais", "8/20", "« Confond 'beach' et 'bitch'. Situation embarrassante pendant l'oral. »"),
    ], "Sympathique mais... maladroit. Dans tous les sens du terme."),
    ("LUCIE MOREAU", c("e8a33d"), [
        ("Mathématiques", "6/20", "« De l'énergie mais aucune logique mathématique. »"),
        ("Français", "10/20", "« Participe beaucoup. Malheureusement, souvent hors sujet. »"),
        ("EPS", "4/20", "« A fait tomber trois personnes pendant un relais. Record du lycée. »"),
        ("Anglais", "7/20", "« Prononciation catastrophique. Compensation par l'enthousiasme. »"),
    ], "Dynamique et sociable, mais gagnerait à être plus... coordonnée."),
]


@scene(19.0)
def s_bulletins(ctx, t, S):
    degrade(ctx, c("a0522d"), c("6d3a1c"))
    for i in range(12):
        ctx.rectangle(0, i * 95, W, 3)
        ctx.set_source_rgba(0, 0, 0, 0.12)
        ctx.fill()
    for idx, (nom, col, lignes, appr) in enumerate(BULLETINS):
        t0 = idx * 9.5
        dt = t - t0
        if dt < 0 or dt > 9.8:
            continue
        x_off = -W * (1 - lisse(dt / 0.6)) + W * lisse((dt - 9.0) / 0.6)
        ctx.save()
        ctx.translate(W / 2 + x_off, H / 2)
        ctx.rotate(-0.02 if idx == 0 else 0.015)
        ctx.rectangle(-770 + 12, -500 + 14, 1540, 1000)
        ctx.set_source_rgba(0, 0, 0, 0.35)
        ctx.fill()
        ctx.rectangle(-770, -500, 1540, 1000)
        remplir(ctx, c("fdfaf1"), 6)
        ctx.rectangle(-770, -500, 1540, 120)
        ctx.set_source_rgba(*col)
        ctx.fill()
        texte(ctx, "BULLETIN SCOLAIRE — " + nom, 0, -448, 50, (1, 1, 1, 1))
        texte(ctx, "Trimestre 1 — Seconde 3", 0, -400, 28, (1, 1, 1, 0.9), gras=False)
        for i, (mat, note, com) in enumerate(lignes):
            if dt < 1.0 + i * 1.5:
                continue
            y = -310 + i * 150
            texte(ctx, mat, -720, y, 40, c("2d3436"), centre=False)
            texte(ctx, note, 600, y, 52, c("d63031"), centre=False)
            police(ctx, 31, gras=False)
            ctx.set_source_rgba(0.3, 0.3, 0.35, 1)
            for j, l in enumerate(couper(ctx, com, 1250)):
                ctx.move_to(-720, y + 46 + j * 38)
                ctx.show_text(l)
        if dt > 7.0:
            texte(ctx, "Appréciation : « " + appr + " »", 0, 400, 32, c("2d3436"))
        if dt > 7.8:
            k = rebond((dt - 7.8) / 0.3)
            ctx.save()
            ctx.translate(430, 190)
            ctx.rotate(-0.25)
            ctx.scale(k, k)
            rrect(ctx, -250, -60, 500, 120, 14)
            ctx.set_source_rgba(0.85, 0.1, 0.1, 0.85)
            ctx.set_line_width(10)
            ctx.stroke()
            texte(ctx, "MALADROIT", 0, 25, 70, (0.85, 0.1, 0.1, 0.85))
            ctx.restore()
        ctx.restore()


SCENES[-1][2] = Script()
SCENES[-1][2].sfx += [(0.1, "whoosh"), (7.8, "tampon"), (9.6, "whoosh"), (17.3, "tampon")]


# 8 — synchronisés
@scene(15.0)
def s_synchro(ctx, t, S):
    fond_bd(ctx, c("6c5ce7"), c("a29bfe"))

    def cantine(ctx, w, h, a):
        degrade(ctx, c("ffeaa7"), c("fab1a0"), 0, h)
        for i, (nom, x, dr) in enumerate((("bastien", w * 0.3, 1), ("lucie", w * 0.7, -1))):
            perso(ctx, nom, x, h - 110, 0.5, dr, pose=P(sl=2.6, sr=2.4, el=0.3, er=0.3, lean=-0.2),
                  expr="panique", t=a)
            k = min(a / 0.8, 1)
            plateau(ctx, x + dr * 60 * k, h - 400 - 80 * math.sin(k * math.pi), k * 5 * dr)

    def retard(ctx, w, h, a):
        degrade(ctx, c("dfe6e9"), c("b2bec3"), 0, h)
        ctx.arc(w / 2, 120, 70, 0, 2 * math.pi)
        remplir(ctx, (1, 1, 1, 1), 6)
        ctx.set_line_width(7)
        ctx.move_to(w / 2, 120)
        ctx.line_to(w / 2, 70)
        ctx.move_to(w / 2, 120)
        ctx.line_to(w / 2 + 40 * math.cos(a * 3), 120 + 40 * math.sin(a * 3))
        ctx.stroke()
        perso(ctx, "lucie", w * 0.28 + a * 30, h - 110, 0.5, 1, pose=p_course(a), expr="panique", t=a)
        perso(ctx, "bastien", w * 0.62 + a * 30, h - 110, 0.5, 1, pose=p_course(a + 0.2), expr="panique", t=a)

    def salle(ctx, w, h, a):
        degrade(ctx, c("f5e6c8"), c("e0cfa8"), 0, h)
        ctx.rectangle(w / 2 - 90, 150, 180, h - 260)
        remplir(ctx, c("b5651d"), 6)
        rrect(ctx, w / 2 - 130, 90, 260, 50, 6)
        remplir(ctx, (1, 1, 1, 1), 4)
        texte(ctx, "SALLE DES PROFS", w / 2, 125, 26, c("c0392b"))
        perso(ctx, "bastien", w * 0.2, h - 110, 0.5, 1, expr="surpris", t=a)
        perso(ctx, "lucie", w * 0.8, h - 110, 0.5, -1, expr="surpris", t=a)
        for i, qx in enumerate((w * 0.2, w * 0.8)):
            texte(ctx, "?", qx, 250 + 10 * math.sin(a * 6 + i), 80, c("6c5ce7"), (1, 1, 1, 1), 8)

    cadre_bd(ctx, 110, 120, 520, 600, t - 3.0, cantine, "Le plateau")
    cadre_bd(ctx, 700, 120, 520, 600, t - 6.3, retard, "Le retard")
    cadre_bd(ctx, 1290, 120, 520, 600, t - 9.6, salle, "La mauvaise salle")
    S.dessiner(ctx, t, {})


SC = SCENES[-1]
SC[2] = Script()
SC[2].raconte(0.2, "Les semaines passèrent. Bastien et Lucie se retrouvaient constamment dans les mêmes situations embarrassantes.", 2.8)
SC[2].raconte(3.0, "Bastien renversait son plateau à la cantine. Lucie aussi.", 3.2)
SC[2].raconte(6.3, "Lucie arrivait en retard en cours. Bastien aussi.", 3.2)
SC[2].raconte(9.6, "Bastien se trompait de salle. Lucie également.", 2.6)
SC[2].raconte(12.3, "C'était comme s'ils étaient synchronisés dans leur capacité à tout rater.", 2.7)
SC[2].sfx += [(3.2, "bam"), (6.5, "whoosh"), (9.8, "boing")]


# 9 — le cours d'EPS
HAIE_X, PLOT_X, CORDE_X = 820, 1010, 1560


@scene(48.0)
def s_eps(ctx, t, S):
    fond_terrain(ctx, t)
    portique(ctx, CORDE_X)
    # balancement de la corde
    ang = 0.0
    if 25.6 < t < 31.0:
        ang = 0.35 * math.sin((t - 25.6) * 3.2) * min(1, (t - 25.6) / 0.8)
    corde(ctx, CORDE_X, ang)
    haie(ctx, HAIE_X, SOL + 10, -1.3 * lisse((t - 12.4) / 0.3) if t > 12.4 else 0)
    plot(ctx, PLOT_X, SOL + 10, 1.4 * lisse((t - 14.2) / 0.3) if t > 14.2 else 0)
    tetes = {}
    # le prof
    if t < 37.5:
        pp = perso(ctx, "prof", 180, SOL + 20, 0.95, 1,
                   pose=P(sr=1.2 + 0.2 * math.sin(t * 6), er=0.4) if S.parle("prof", t) else p_debout(t),
                   expr="fache" if t < 7 else "surpris", parle=S.parle("prof", t), t=t)
    else:
        pp = perso(ctx, "prof", 180, SOL + 20, 0.95, 1,
                   pose=p_tete_mains(t) if not S.parle("prof", t) or t < 39 else P(sr=1.2, er=0.4),
                   expr="triste", parle=S.parle("prof", t), t=t)
    tetes["prof"] = pp["haut"]
    # --- Bastien
    if t < 10.4:
        pb = perso(ctx, "bastien", 420, SOL + 20, 0.9, -1, expr="gene" if t > 6 else "neutre",
                   parle=S.parle("bastien", t), t=t, look=(-2, 0))
    elif t < 12.0:
        x = mix(420, 700, (t - 10.4) / 1.6)
        pb = perso(ctx, "bastien", x, SOL + 20, 0.9, 1, pose=p_course(t), expr="panique", t=t)
    elif t < 12.8:
        k = (t - 12.0) / 0.8
        x = mix(700, 960, k)
        y = SOL + 20 - 170 * math.sin(k * math.pi)
        rot = math.pi / 2 * lisse((k - 0.4) / 0.6)
        pb = perso(ctx, "bastien", x, y - 30 * lisse((k - 0.4) / 0.6), 0.9, 1, rot=rot,
                   pose=fondu_pose(P(hl=1.2, kl=-0.3, hr=-0.6, kr=-1.2, sl=2.5, sr=2.2), p_allonge(), lisse(k)),
                   expr="panique", t=t)
    elif t < 19.0:
        pb = perso(ctx, "bastien", 960, SOL - 10, 0.9, 1, rot=math.pi / 2, pose=p_allonge(),
                   expr="panique" if t < 16.4 else "gene", parle=S.parle("bastien", t), t=t)
    elif t < 19.8:
        k = lisse((t - 19.0) / 0.8)
        pb = perso(ctx, "bastien", 960 + 50 * k, SOL + 20 - 30 * (1 - k), 0.9, 1, rot=math.pi / 2 * (1 - k),
                   pose=fondu_pose(p_allonge(), p_debout(t), k), expr="gene", t=t, poussiere=True)
    elif t < 21.5:
        x = mix(1010, CORDE_X - 90, (t - 19.8) / 1.7)
        pb = perso(ctx, "bastien", x, SOL + 20, 0.9, 1, pose=p_marche(t), expr="gene", t=t, poussiere=True)
    elif t < 23.6:
        # grimpe de trente centimètres... et glisse
        mont = 70 * lisse((t - 21.5) / 1.2) * (1 - lisse((t - 22.9) / 0.4))
        pb = perso(ctx, "bastien", CORDE_X - 30, SOL + 20 - mont, 0.9, 1, pose=p_grimpe(t),
                   expr="panique", t=t, sueur=True, poussiere=True)
    elif t < 31.3:
        pb = perso(ctx, "bastien", CORDE_X - 170, SOL + 20, 0.9, 1,
                   pose=P(sl=2.6 + 0.3 * math.sin(t * 8), sr=2.4, el=0.3, er=0.3) if t > 26 else p_debout(t),
                   expr="panique" if t > 26 else "neutre", parle=S.parle("bastien", t), t=t, look=(4, -8),
                   poussiere=True)
    else:
        k = lisse((t - 31.3) / 0.3)
        pb = perso(ctx, "bastien", CORDE_X - 170, SOL + 20 - 30 * k, 0.9, 1, rot=-math.pi / 2 * k,
                   pose=p_allonge() if k > 0.5 else p_debout(t),
                   expr="triste" if t > 33 else "panique", parle=S.parle("bastien", t), t=t, poussiere=True)
    tetes["bastien"] = pb["haut"]
    # --- Lucie
    if t < 13.3:
        pl = perso(ctx, "lucie", 560, SOL + 20, 0.9, -1, expr="gene" if t > 6 else "neutre",
                   parle=S.parle("lucie", t), t=t)
    elif t < 14.3:
        x = mix(560, 980, (t - 13.3) / 1.0)
        pl = perso(ctx, "lucie", x, SOL + 20, 0.9, 1, pose=p_course(t), expr="surpris", t=t)
    elif t < 14.8:
        k = lisse((t - 14.3) / 0.5)
        pl = perso(ctx, "lucie", mix(980, 1060, k), SOL + 20 - 60 * k, 0.9, 1, rot=math.pi / 2 * 0.9 * k,
                   pose=fondu_pose(p_moulin(t), p_allonge(), k), expr="panique", t=t)
    elif t < 19.0:
        pl = perso(ctx, "lucie", 1060, SOL - 40, 0.9, 1, rot=math.pi / 2 * 0.9, pose=p_allonge(),
                   expr="panique", parle=S.parle("lucie", t), t=t)
    elif t < 19.8:
        k = lisse((t - 19.0) / 0.8)
        pl = perso(ctx, "lucie", 1100, SOL + 20 - 60 * (1 - k), 0.9, 1, rot=math.pi / 2 * 0.9 * (1 - k),
                   pose=fondu_pose(p_allonge(), p_debout(t), k), expr="gene", t=t, poussiere=True)
    elif t < 23.8:
        x = mix(1100, CORDE_X + 120, lin(t, 19.8, 21.5))
        pl = perso(ctx, "lucie", x, SOL + 20, 0.9, -1, pose=p_marche(t) if t < 21.5 else p_debout(t),
                   expr="sourire", t=t, poussiere=True)
    elif t < 31.0:
        haut = 380 * lisse((t - 23.8) / 1.8)
        main = seg((CORDE_X, 120), ang, 700 - haut - 40)
        ctx.save()
        ctx.translate(*main)
        ctx.rotate(-ang)
        pl = perso(ctx, "lucie", 0, 470 * 0.9, 0.9, 1, pose=p_grimpe(t),
                   expr="crie" if t > 25.6 else "sourire", parle=S.parle("lucie", t), t=t, poussiere=True)
        ctx.restore()
    else:
        k = lisse((t - 31.0) / 0.35)
        yh = mix(120 + 700 - 380 - 40 + 470 * 0.9, SOL - 20, k)
        pl = perso(ctx, "lucie", mix(CORDE_X, CORDE_X - 200, k), yh, 0.9, -1,
                   rot=math.pi / 2 * 0.9 * k, pose=fondu_pose(p_grimpe(t), p_allonge(), k),
                   expr="gene" if t > 33 else "crie", parle=S.parle("lucie", t), t=t, poussiere=True)
    tetes["lucie"] = pl["haut"]
    boum(ctx, 1000, SOL - 320, t - 12.8)
    boum(ctx, 1150, SOL - 360, t - 14.8, "BOUM !")
    boum(ctx, CORDE_X - 260, SOL - 360, t - 31.35, "PAF !")
    # chrono
    if t > 37.5:
        k = rebond((t - 37.5) / 0.4)
        ctx.save()
        ctx.translate(1500, 230)
        ctx.scale(k, k)
        rrect(ctx, -220, -80, 440, 160, 20)
        remplir(ctx, c("2d3436"), 6)
        texte(ctx, "8:00", 0, 38, 110, c("ff4757"))
        texte(ctx, "record : 1:30", 0, 130, 40, (1, 1, 1, 1), OUT, 5)
        ctx.restore()
    decal = {"bastien": (0, 0), "lucie": (0, 0), "prof": (0, 0)}
    if 31.3 < t:
        decal["bastien"] = (60, -40)
        decal["lucie"] = (-40, -60)
    S.dessiner(ctx, t, {k: (v[0] + decal[k][0], v[1] + decal[k][1]) for k, v in tetes.items()})


SC = SCENES[-1]
S9 = Script()
S9.dit(0.3, "prof", "Bon, vous deux, puisque vous êtes toujours ensemble à faire n'importe quoi, vous allez faire équipe pour le parcours d'obstacles.", 5.8)
S9.dit(6.4, "bastien", "On va mourir.", 1.8)
S9.dit(8.3, "lucie", "Probablement.", 1.8)
S9.raconte(10.2, "Courir, sauter des haies, grimper à une corde. Ça avait l'air facile.", 2.3)
S9.raconte(12.6, "Ça ne l'était pas.", 2.0)
S9.dit(15.0, "lucie", "PARDON !", 1.4)
S9.dit(16.5, "bastien", "C'EST BON, JE RESPIRE ENCORE !", 2.4)
S9.raconte(19.2, "La corde était le prochain obstacle.", 2.2)
S9.raconte(21.6, "Bastien monta de trente centimètres... et glissa.", 2.1)
S9.raconte(23.8, "Lucie monta un peu plus haut... et la corde se balança.", 2.0)
S9.dit(26.0, "lucie", "BASTIEN ! AIDE-MOI !", 1.7)
S9.dit(27.8, "bastien", "COMMENT ?!", 1.4)
S9.dit(29.3, "lucie", "J'EN SAIS RIEN !", 1.6)
S9.raconte(31.5, "Finalement, Lucie lâcha prise et tomba. Directement sur Bastien. Encore.", 2.3)
S9.dit(33.9, "bastien", "On est vraiment nuls.", 1.8)
S9.dit(35.8, "lucie", "Vraiment, vraiment nuls.", 1.8)
S9.dit(37.8, "prof", "Vous avez fini derniers. De loin. Huit minutes. Le record, c'est une minute trente.", 4.8)
S9.dit(42.8, "bastien", "Désolés !", 1.6)
S9.dit(42.9, "lucie", "Désolés !", 1.5)
S9.dit(44.6, "prof", "Allez vous asseoir.", 2.4)
S9.sfx += [(10.1, "sifflet"), (12.8, "bam"), (12.5, "haie"), (14.8, "bam"), (22.9, "glisse"),
           (26.0, "crie"), (31.35, "bam"), (37.6, "tampon")]
SC[2] = S9


# 10 — le banc
@scene(0)
def s_banc(ctx, t, S):
    fond_terrain(ctx, t)
    banc(ctx, 700, SOL - 95 * 0.95 + 20, 520)
    rit = t < 2.4
    pb = perso(ctx, "bastien", 780, SOL - 5, 0.95, 1,
               pose=p_rire(t) if rit else (P(**{**p_assis(), "sr": 1.45, "er": 0.05}) if 12.9 < t else p_assis()),
               expr="rire" if rit else ("sourire" if t > 12 else "neutre"),
               parle=S.parle("bastien", t), t=t, poussiere=True)
    if rit:
        pb = pb
    pl = perso(ctx, "lucie", 1140, SOL - 5, 0.95, -1,
               pose=P(**{**p_assis(), "sr": 1.45 if t > 9.8 else 0.6, "er": 0.05}),
               expr="rire" if rit else "sourire", parle=S.parle("lucie", t), t=t, poussiere=True)
    if rit:
        rires(ctx, t, [(960, 330)])
    if 13.5 < t < 15.0:
        k = (t - 13.5) / 1.5
        cx = (pb["main_d"][0] + pl["main_d"][0]) / 2
        cy = (pb["main_d"][1] + pl["main_d"][1]) / 2
        for i in range(10):
            a = i * math.pi / 5
            ctx.move_to(cx + math.cos(a) * 40 * (1 + k), cy + math.sin(a) * 40 * (1 + k))
            ctx.line_to(cx + math.cos(a) * 80 * (1 + k), cy + math.sin(a) * 80 * (1 + k))
        ctx.set_source_rgba(1, 0.85, 0.1, 1 - k)
        ctx.set_line_width(8)
        ctx.stroke()
    S.dessiner(ctx, t, {"bastien": pb["haut"], "lucie": pl["haut"]})


SC = SCENES[-1]
S10 = Script()
S10.raconte(0.2, "Assis sur le banc, couverts de poussière et de honte, Bastien et Lucie se mirent à rire.", 3.0)
fin = S10.suite(3.4, [("bastien", "On est les pires."),
                      ("lucie", "Les pires des pires."),
                      ("bastien", "Mais au moins, on est les pires ensemble."),
                      ("lucie", "Deal. On est une équipe de losers.", 2.8)])
fin = S10.dit(fin + 0.6, "bastien", "L'équipe des catastrophes.", 2.4)
fin = S10.raconte(fin + 0.2, "Et c'est comme ça que tout commença. Une amitié forgée dans l'échec, la maladresse... et les chutes spectaculaires.", 5.0)
S10.sfx += [(0.3, "rire2"), (13.5, "check")]
SC[1], SC[2] = fin + 0.3, S10


# 11 — les SMS
SMS = [("m", "18h34", "J'ai eu ton bulletin"), ("m", "18h34", "On doit parler"),
       ("b", "18h45", "Je sais maman désolé"), ("m", "18h46", "7 en maths Bastien"),
       ("m", "18h46", "SEPT"), ("b", "18h47", "Au moins c'est pas 6 ?"), ("m", "18h48", "..."),
       ("m", "18h49", "Tu rentres à quelle heure"), ("b", "18h50", "Je suis avec Lucie on fait les devoirs"),
       ("m", "18h51", "La fille qui a encore pire notes que toi ??"),
       ("b", "18h52", "Ouais mais elle est sympa"), ("m", "18h53", "Rentre avant 20h"),
       ("m", "18h53", "Et travaille plus")]
SMS_T0, SMS_PAS = 1.4, 1.45


@scene(SMS_T0 + SMS_PAS * len(SMS) + 2.5)
def s_sms(ctx, t, S):
    fond_bd(ctx, c("2d3436"), c("636e72"))
    texte(ctx, "SMS entre Bastien", 380, 150, 46, c("ffd84d"), OUT, 6)
    texte(ctx, "et sa mère", 380, 210, 46, c("ffd84d"), OUT, 6)
    texte(ctx, "Soir du premier trimestre", 380, 270, 32, (1, 1, 1, 0.9), gras=False)
    px, py, pw, ph = 760, 40, 520, 1000
    rrect(ctx, px, py, pw, ph, 60)
    remplir(ctx, c("111111"), 6)
    rrect(ctx, px + 22, py + 70, pw - 44, ph - 140, 20)
    ctx.set_source_rgba(*c("f1f2f6"))
    ctx.fill()
    rrect(ctx, px + 22, py + 70, pw - 44, 90, 20)
    ctx.set_source_rgba(*c("dfe4ea"))
    ctx.fill()
    ctx.arc(px + 80, py + 115, 28, 0, 2 * math.pi)
    remplir(ctx, c("e84393"), 3)
    texte(ctx, "Maman", px + 180, py + 127, 34, c("2d3436"))
    # messages
    n = min(len(SMS), int((t - SMS_T0) / SMS_PAS) + 1) if t >= SMS_T0 else 0
    police(ctx, 28, gras=False)
    blocs = []
    for qui, h, msg in SMS[:n]:
        lignes = couper(ctx, msg, 300)
        blocs.append((qui, h, lignes, len(lignes) * 36 + 44))
    total = sum(b[3] + 14 for b in blocs)
    haut_vis = ph - 260
    ctx.save()
    rrect(ctx, px + 22, py + 165, pw - 44, ph - 240, 10)
    ctx.clip()
    y = py + 180 - max(0, total - haut_vis)
    for i, (qui, h, lignes, bh) in enumerate(blocs):
        police(ctx, 28, gras=False)
        bw = max(ctx.text_extents(l).x_advance for l in lignes) + 40
        x = px + 40 if qui == "m" else px + pw - 40 - bw
        age = t - (SMS_T0 + i * SMS_PAS)
        k = rebond(age / 0.25)
        ctx.save()
        ctx.translate(x + bw / 2, y + bh / 2)
        ctx.scale(k, k)
        ctx.translate(-bw / 2, -bh / 2)
        rrect(ctx, 0, 0, bw, bh - 14, 22)
        ctx.set_source_rgba(*(c("ffffff") if qui == "m" else c("0a84ff")))
        ctx.fill()
        police(ctx, 28, gras=(lignes[0] == "SEPT"))
        ctx.set_source_rgba(*((0.1, 0.1, 0.1, 1) if qui == "m" else (1, 1, 1, 1)))
        for j, l in enumerate(lignes):
            ctx.move_to(20, 38 + j * 36)
            ctx.show_text(l)
        police(ctx, 16, gras=False)
        ctx.set_source_rgba(0.5, 0.5, 0.55, 1)
        ctx.move_to(bw - 60 if qui == "b" else 0, bh + 2)
        ctx.show_text(h)
        ctx.restore()
        y += bh + 14
    ctx.restore()
    # Bastien réagit à droite
    dernier = SMS[n - 1][2] if n else ""
    expr = "sourire"
    if dernier in ("7 en maths Bastien", "SEPT", "...", "La fille qui a encore pire notes que toi ??"):
        expr = "panique"
    elif dernier in ("J'ai eu ton bulletin", "On doit parler", "Rentre avant 20h", "Et travaille plus"):
        expr = "gene"
    perso(ctx, "bastien", 1590, SOL + 60, 0.95, -1, pose=P(sr=1.3, er=1.4, tete=0.15), expr=expr, t=t,
          sueur=expr == "panique", rouge=0.6 if expr == "gene" else 0)


SCENES[-1][2] = Script()
SCENES[-1][2].sfx += [(SMS_T0 + i * SMS_PAS, "ding" if q == "m" else "envoi") for i, (q, _, _) in enumerate(SMS)]


# 12 — pour toujours
@scene(0)
def s_toujours(ctx, t, S):
    soir = min(1, t / 14)
    fond_cour(ctx, t, soir)
    banc(ctx, 700, SOL - 95 * 0.95 + 20, 520)
    coude = 16.2 < t < 17.6
    pb = perso(ctx, "bastien", 800, SOL - 5, 0.95, 1, pose=p_assis(), expr="sourire" if t < 16 or t > 18 else "surpris",
               parle=S.parle("bastien", t), t=t, look=(0, -6) if 12 < t < 14.5 else (0, 0))
    pl = perso(ctx, "lucie", 1120, SOL - 5, 0.95, -1,
               pose=P(**{**p_assis(), "sr": 0.6 if coude else 0.6, "er": 1.9 if coude else 0.5,
                         "lean": 0.35 if coude else 0.0}),
               expr="content" if t > 16 else "sourire", parle=S.parle("lucie", t), t=t)
    if 12.4 < t < 14.4:
        for i in range(3):
            ctx.arc(pb["haut"][0] - 40 - i * 30, pb["haut"][1] - 20 - i * 34, 8 + i * 6, 0, 2 * math.pi)
            remplir(ctx, (1, 1, 1, 1), 3)
    S.dessiner(ctx, t, {"bastien": pb["haut"], "lucie": pl["haut"]})


SC = SCENES[-1]
S12 = Script()
S12.raconte(0.2, "Les mois passèrent. Bastien et Lucie devinrent inséparables.", 3.2)
S12.raconte(3.5, "Ils partageaient tout : les devoirs qu'ils ne comprenaient pas, les colles, les moqueries des autres élèves. Mais ils s'en fichaient.", 4.4)
S12.raconte(8.0, "Parce qu'ils avaient trouvé quelque chose de rare : quelqu'un d'aussi nul, d'aussi maladroit qu'eux.", 3.4)
fin = S12.suite(11.6, [("lucie", "Tu crois qu'on sera toujours amis ? Genre même après le lycée ?", 3.6)])
fin = S12.suite(fin + 0.6, [("bastien", "Bah ouais. Qui d'autre voudrait être ami avec nous ?", 3.0),
                            ("lucie", "Idiot.", 1.4),
                            ("bastien", "Mais sérieusement. On reste ensemble. Pour toujours.", 3.2),
                            ("lucie", "Pour toujours.", 2.4)])
S12.sfx += [(16.3, "boing")]
SC[1], SC[2] = fin + 0.4, S12


# 13 — dix ans plus tard
COUV = None


@scene(15.0)
def s_final(ctx, t, S):
    global COUV
    if t < 6.5:
        fond_cour(ctx, t + 20, 1.0)
        banc(ctx, 700, SOL - 95 * 0.95 + 20, 520)
        k = lisse((t - 3.4) / 1.0)
        chap = t > 4.4
        a = perso(ctx, "bastien", 800, SOL - 5, 0.95, 1, pose=p_assis(), expr="surpris" if chap else "sourire",
                  t=t, chap=chap)
        b = perso(ctx, "lucie", 1120, SOL - 5, 0.95, -1, pose=p_assis(), expr="surpris" if chap else "sourire",
                  t=t, chap=chap)
        if 3.4 < t <= 4.4:
            for tx, ty in (a["tete"], b["tete"]):
                ctx.save()
                ctx.translate(tx, mix(-150, ty, k))
                ctx.rotate((1 - k) * 4)
                ctx.scale(0.95, 0.95)
                chapeau(ctx, 85)
                ctx.restore()
        legende(ctx, "Ils ne savaient pas encore qu'un jour, dix ans plus tard, cette amitié les mènerait à devenir détectives.", t - 0.2, 6.0)
        if t > 5.6:
            ctx.set_source_rgba(1, 1, 1, lin(t, 5.6, 6.5))
            ctx.paint()
        return
    if COUV is None:
        COUV = cairo.ImageSurface.create_from_png("couverture_ch1.png")
    fond_bd(ctx, c("1e2a78"), c("3c55c7"))
    z = 1 + 0.04 * (t - 6.5) / 8.5
    cw, ch = COUV.get_width(), COUV.get_height()
    s = 960 / ch * z
    ctx.save()
    ctx.translate(560, H / 2)
    ctx.scale(s, s)
    ctx.translate(-cw / 2, -ch / 2)
    ctx.set_source_surface(COUV, 0, 0)
    ctx.paint()
    ctx.restore()
    if t > 7.5:
        a = lin(t, 7.5, 8.2)
        texte(ctx, "Les pires détectives", 1420, 380, 62, c("ffd84d", a), c("7a3b00", a), 8)
        texte(ctx, "du monde.", 1420, 460, 62, c("ffd84d", a), c("7a3b00", a), 8)
    if t > 9.3:
        a = lin(t, 9.3, 10.0)
        texte(ctx, "Mais les meilleurs amis", 1420, 590, 50, (1, 1, 1, a), OUT, 6)
        texte(ctx, "qu'on puisse imaginer.", 1420, 655, 50, (1, 1, 1, a), OUT, 6)
    if t > 11.3:
        k = rebond((t - 11.3) / 0.4)
        ctx.save()
        ctx.translate(1420, 830)
        ctx.scale(k, k)
        rrect(ctx, -300, -55, 600, 110, 55)
        remplir(ctx, c("c2185b"), 6)
        texte(ctx, "Fin du chapitre 1", 0, 16, 46, (1, 1, 1, 1))
        ctx.restore()
    if t < 7.2:
        ctx.set_source_rgba(1, 1, 1, 1 - lin(t, 6.5, 7.2))
        ctx.paint()


SCENES[-1][2] = Script()
SCENES[-1][2].sfx += [(3.5, "whoosh"), (4.4, "pop"), (6.5, "magie")]


# ------------------------------------------------------------ son
SR = 44100


def bruitages(total):
    son = np.zeros(int(total * SR) + SR)
    rng = np.random.default_rng(7)

    def ajoute(t0, s, vol=1.0):
        i = int(t0 * SR)
        if i < 0 or i >= len(son):
            return
        s = s[:len(son) - i]
        son[i:i + len(s)] += vol * s

    def tps(d):
        return np.arange(int(d * SR)) / SR

    def bam():
        tt = tps(0.6)
        f = 110 * np.exp(-tt * 4)
        s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 7)
        s += 0.6 * np.convolve(rng.standard_normal(len(tt)), np.ones(8) / 8, "same") * np.exp(-tt * 18)
        return s

    def whoosh():
        tt = tps(0.5)
        return 0.5 * np.convolve(rng.standard_normal(len(tt)), np.ones(30) / 30, "same") * np.sin(np.pi * tt / 0.5) ** 2 * 4

    def boing():
        tt = tps(0.6)
        f = 220 + 380 * tt / 0.6 + 40 * np.sin(2 * np.pi * 14 * tt)
        return 0.6 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 3)

    def pop():
        tt = tps(0.08)
        return 0.35 * np.sin(2 * np.pi * (600 + 2500 * tt) * tt) * np.exp(-tt * 40)

    def ding():
        tt = tps(0.5)
        return 0.4 * (np.sin(2 * np.pi * 1320 * tt) + 0.6 * np.sin(2 * np.pi * 1760 * tt)) * np.exp(-tt * 8)

    def envoi():
        tt = tps(0.25)
        return 0.3 * np.sin(2 * np.pi * (500 + 1600 * tt) * tt) * np.exp(-tt * 12)

    def sifflet():
        tt = tps(0.9)
        f = 2800 + 180 * np.sign(np.sin(2 * np.pi * 22 * tt))
        return 0.35 * np.sin(2 * np.pi * np.cumsum(f) / SR) * np.minimum(1, (0.9 - tt) * 8)

    def rire(base=210):
        s = np.zeros(int(1.4 * SR))
        for k in range(6):
            tt = tps(0.13)
            f = base * (1 - 0.04 * k) * (1 + 0.1 * rng.random())
            v = sum(np.sin(2 * np.pi * f * h * tt) * np.exp(-((f * h - 800) / 500) ** 2) for h in range(1, 12))
            v *= np.sin(np.pi * tt / 0.13)
            i = int(k * 0.2 * SR)
            s[i:i + len(v)] += v
        return 0.25 * s / (np.abs(s).max() + 1e-9)

    def tampon():
        tt = tps(0.3)
        return 0.8 * np.sin(2 * np.pi * 70 * tt) * np.exp(-tt * 15) + 0.3 * rng.standard_normal(len(tt)) * np.exp(-tt * 40)

    def glisse():
        tt = tps(0.7)
        f = 900 - 700 * tt / 0.7
        return 0.35 * np.sin(2 * np.pi * np.cumsum(f) / SR)

    def crie():
        tt = tps(1.2)
        f = 520 + 60 * np.sin(2 * np.pi * 6 * tt)
        v = sum(np.sin(2 * np.pi * np.cumsum(f * h) / SR) * np.exp(-((520 * h - 1000) / 700) ** 2) for h in range(1, 8))
        return 0.18 * v / 3 * np.minimum(1, (1.2 - tt) * 5)

    def magie():
        s = np.zeros(int(1.2 * SR))
        for k, f in enumerate([880, 1109, 1319, 1760, 2217]):
            tt = tps(0.6)
            v = 0.2 * np.sin(2 * np.pi * f * tt) * np.exp(-tt * 5)
            i = int(k * 0.1 * SR)
            s[i:i + len(v)] += v
        return s

    def check():
        s = 0.3 * bam()[:int(0.15 * SR)]
        p = pop() * 2
        s[:len(p)] += p
        return s

    def course():
        s = np.zeros(int(9.5 * SR))
        for k in range(int(9.5 * 4)):
            tt = tps(0.06)
            v = 0.25 * np.convolve(rng.standard_normal(len(tt)), np.ones(40) / 40, "same") * np.exp(-tt * 60) * 6
            i = int(k * 0.25 * SR * (0.8 if k > 24 else 1))
            if i + len(v) < len(s):
                s[i:i + len(v)] += v
        return s

    def cloche():
        tt = tps(2.0)
        return 0.3 * np.sin(2 * np.pi * 950 * tt) * (0.6 + 0.4 * np.sign(np.sin(2 * np.pi * 18 * tt))) * np.minimum(1, (2.0 - tt) * 3)

    sons = dict(cloche=cloche, bam=bam, whoosh=whoosh, boing=boing, pop=pop, ding=ding, envoi=envoi, sifflet=sifflet,
                rire=rire, rire2=lambda: rire(260), tampon=tampon, glisse=glisse, crie=crie, magie=magie,
                check=check, course=course, haie=lambda: 0.5 * tampon())
    t = 0.0
    for f, d, S in SCENES:
        for ts, nom in S.sfx:
            ajoute(t + ts, sons[nom](), 0.9)
        t += d
    return son


def musique(total):
    n = int(total * SR) + SR
    son = np.zeros(n)
    hz = lambda m: 440 * 2 ** ((m - 69) / 12)

    def note(f, deb, dur, vol, pizz=True):
        i0, k = int(deb * SR), int(dur * SR)
        if i0 >= n:
            return
        k = min(k, n - i0)
        tt = np.arange(k) / SR
        if pizz:
            s = (np.sin(2 * np.pi * f * tt) + 0.3 * np.sin(4 * np.pi * f * tt)) * np.exp(-tt * 9)
        else:
            s = np.sin(2 * np.pi * f * tt) * np.exp(-tt * 4)
        son[i0:i0 + k] += vol * s

    basse = [40, 47, 43, 47, 40, 47, 45, 44]
    theme = [64, None, 67, 66, 64, None, 71, 70, 69, None, 67, 66, 64, 62, 64, None,
             67, None, 69, 71, 72, None, 71, 69, 67, 66, 64, 66, 67, None, None, None]
    pas, t = 0, 0.0
    while t < total:
        note(hz(basse[pas % 8]), t, 0.4, 0.35, False)
        m = theme[pas % 32]
        if m and (pas // 64) % 2 == 0:
            note(hz(m), t, 0.3, 0.2)
        elif m and pas % 2 == 0:
            note(hz(m + 12), t, 0.2, 0.08)
        if pas % 4 == 2:
            note(3000, t, 0.02, 0.03, False)
        t += 0.25
        pas += 1
    return son


def piste_son(total):
    m = musique(total)
    b = bruitages(total)
    m = 0.22 * m / (np.abs(m).max() + 1e-9)
    s = m + 0.8 * b / (np.abs(b).max() + 1e-9)
    s = np.tanh(s * 1.2)
    fin = int(1.5 * SR)
    s[-fin:] *= np.linspace(1, 0, fin)
    with wave.open("chapitre1.wav", "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((s * 32000).astype(np.int16).tobytes())


# ------------------------------------------------------------ rendu
def preparer_couverture():
    from PIL import Image
    im = Image.open("couverture.jpg").convert("RGB").crop((367, 163, 2284, 3247))
    im.thumbnail((700, 1120))
    im.save("couverture_ch1.png")


def image(surface, ctx, scene_fn, t, duree, S):
    ctx.save()
    ctx.set_source_rgb(0, 0, 0)
    ctx.paint()
    random.seed(int(t * 1000))
    scene_fn(ctx, t, S)
    a = min(1, t / 0.3, (duree - t) / 0.3)
    if a < 1:
        ctx.set_source_rgba(0, 0, 0, 1 - max(0, a))
        ctx.paint()
    ctx.restore()


def main():
    preparer_couverture()
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surface)
    if "--apercu" in sys.argv:
        for i, (f, d, S) in enumerate(SCENES):
            for j, frac in enumerate((0.25, 0.55, 0.85)):
                image(surface, ctx, f, d * frac, d, S)
                surface.write_to_png(f"apercu_{i:02d}_{j}.png")
        print("durée totale :", sum(d for _, d, _ in SCENES))
        return
    total = sum(d for _, d, _ in SCENES)
    piste_son(total)
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    proc = subprocess.Popen(
        [ff, "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-i", "chapitre1.wav", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "21", "-preset", "medium",
         "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", "chapitre1_dessin_anime.mp4"],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for f, d, S in SCENES:
        for i in range(int(round(d * FPS))):
            image(surface, ctx, f, i / FPS, d, S)
            surface.flush()
            proc.stdin.write(bytes(surface.get_data()))
    proc.stdin.close()
    proc.wait()
    print(f"OK : {total:.1f} s")


if __name__ == "__main__":
    main()
