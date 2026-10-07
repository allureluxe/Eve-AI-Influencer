"""La musique des Reels et Stories de @alluxe.ia, composée par programme.

Pourquoi composer plutôt que télécharger : un morceau « libre de droits »
pris sur un site peut être reconnu par Instagram et rendre la vidéo muette
ou bloquée. Une musique synthétisée ici n'appartient à personne d'autre :
aucun risque de droits.

Pourquoi pas la musique d'Instagram : depuis mai 2026, Meta ne l'ouvre aux
programmes que pour les Reels, et seulement aux comptes reliés par
**Facebook** — le nôtre l'est par la connexion « Instagram ». Jamais pour
les Stories. Un Reel muet part avec un gros handicap (4 oct. : 5 vues).

Style : lo-fi calme (piano électrique, basse ronde, batterie feutrée), qui
laisse lire le texte. Chaque `graine` donne une tonalité, une grille
d'accords et un tempo différents, toujours les mêmes pour la même graine.

    python3 -m alluxe_ia.musique 22.5 sortie.wav [graine]
"""
from __future__ import annotations

import hashlib
import sys
import wave

import numpy as np

TAUX = 44100

# Grilles en degrés (demi-tons depuis la tonique) : accords de 4 sons.
GRILLES = [
    [(9, "m7"), (5, "maj7"), (0, "maj7"), (7, "6")],      # vi IV I V
    [(2, "m7"), (7, "7"), (0, "maj7"), (9, "m7")],        # ii V I vi
    [(0, "maj7"), (9, "m7"), (2, "m7"), (7, "7")],        # I vi ii V
    [(5, "maj7"), (4, "m7"), (2, "m7"), (0, "maj7")],     # IV iii ii I
]
QUALITES = {"maj7": (0, 4, 7, 11), "m7": (0, 3, 7, 10), "7": (0, 4, 7, 10), "6": (0, 4, 7, 9)}


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _graine(texte: str) -> int:
    return int(hashlib.sha256(texte.encode()).hexdigest()[:8], 16)


def _enveloppe(n: int, attaque: float, chute: float) -> np.ndarray:
    t = np.arange(n) / TAUX
    env = np.exp(-t / chute)
    a = max(1, int(attaque * TAUX))
    env[:a] *= np.linspace(0, 1, a)
    return env


def _piano(freq: float, duree: float) -> np.ndarray:
    """Piano électrique : fondamentale + harmoniques qui s'éteignent vite."""
    n = int(duree * TAUX)
    t = np.arange(n) / TAUX
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    son = (np.sin(2 * np.pi * freq * t)
           + 0.35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t / 0.4)
           + 0.12 * np.sin(2 * np.pi * 3 * freq * t) * np.exp(-t / 0.2))
    return son * trem * _enveloppe(n, 0.01, 1.6)


def _kick(n: int) -> np.ndarray:
    t = np.arange(n) / TAUX
    f = 50 + 70 * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / TAUX) * np.exp(-t / 0.18)


def _bruit(n: int, chute: float, rng: np.random.Generator, doux: int) -> np.ndarray:
    b = rng.standard_normal(n)
    if doux > 1:                      # passe-bas grossier : moyenne glissante
        b = np.convolve(b, np.ones(doux) / doux, mode="same")
    return b * _enveloppe(n, 0.002, chute)


def _poser(piste: np.ndarray, son: np.ndarray, debut: float, gain: float) -> None:
    i = int(debut * TAUX)
    if i >= len(piste):
        return
    fin = min(len(piste), i + len(son))
    piste[i:fin] += gain * son[: fin - i]


def _echo(x: np.ndarray, retard: float, retour: float, fois: int = 4) -> np.ndarray:
    y = x.copy()
    d = int(retard * TAUX)
    for k in range(1, fois + 1):
        if d * k >= len(x):
            break
        y[d * k:] += (retour ** k) * x[: len(x) - d * k]
    return y


def composer(duree: float, graine: str = "alluxe") -> np.ndarray:
    """Rend un tableau stéréo (n, 2) en float, entre -1 et 1."""
    g = _graine(graine)
    rng = np.random.default_rng(g)
    tonique = 57 + (g % 7) - 3                 # autour de La grave
    grille = GRILLES[(g >> 3) % len(GRILLES)]
    bpm = 78 + (g >> 6) % 14                    # 78 à 91
    temps = 60.0 / bpm
    mesure = 4 * temps
    n = int((duree + 2.5) * TAUX)               # marge pour les queues d'échos
    accords = np.zeros(n)
    basse = np.zeros(n)
    batterie = np.zeros(n)
    pompe = np.ones(n)

    nb_mesures = int(np.ceil((duree + 1) / mesure))
    for m in range(nb_mesures):
        racine, qualite = grille[m % len(grille)]
        debut = m * mesure
        notes = [tonique + racine + iv for iv in QUALITES[qualite]]
        # Accord légèrement arpégé (« strum ») sur le 1er temps, rappel au 3e.
        for k, note in enumerate(notes):
            _poser(accords, _piano(_hz(note), mesure), debut + 0.012 * k, 0.16)
            _poser(accords, _piano(_hz(note + 12), temps * 1.5), debut + 2 * temps + 0.3 * temps + 0.01 * k, 0.05)
        # Basse ronde : tonique de l'accord, une octave sous.
        fb = _hz(tonique + racine - 12)
        for b, long in ((0, 1.6), (2.5, 1.2)):
            nb = int(long * temps * TAUX)
            t = np.arange(nb) / TAUX
            _poser(basse, np.sin(2 * np.pi * fb * t) * _enveloppe(nb, 0.01, 0.6), debut + b * temps, 0.32)
        # Batterie feutrée : grosse caisse 1 et 3(+), caisse claire 2 et 4, charleston en croches.
        for b in (0, 2.5) if m % 2 else (0, 2):
            _poser(batterie, _kick(int(0.4 * TAUX)), debut + b * temps, 0.55)
            i = int((debut + b * temps) * TAUX)
            fin = min(n, i + int(0.35 * TAUX))
            pompe[i:fin] = np.minimum(pompe[i:fin], 0.55 + 0.45 * np.linspace(0, 1, fin - i))
        for b in (1, 3):
            _poser(batterie, _bruit(int(0.25 * TAUX), 0.07, rng, 6), debut + b * temps, 0.13)
        for c in range(8):
            jeu = 0.012 * rng.standard_normal()          # léger « swing » humain
            gain = 0.035 if c % 2 == 0 else 0.022
            _poser(batterie, _bruit(int(0.06 * TAUX), 0.018, rng, 1), debut + c * temps / 2 + abs(jeu), gain)

    accords = _echo(accords, temps * 0.75, 0.35)
    # Grain de vinyle très bas : la texture lo-fi.
    vinyle = 0.006 * np.convolve(rng.standard_normal(n), np.ones(20) / 20, mode="same")
    craque = (rng.random(n) > 0.99985) * rng.standard_normal(n) * 0.05

    mono = accords * pompe + basse * pompe + batterie + vinyle + craque
    gauche = mono + 0.04 * np.roll(accords, int(0.011 * TAUX))
    droite = mono + 0.04 * np.roll(accords, int(0.017 * TAUX))
    st = np.stack([gauche, droite], axis=1)[: int(duree * TAUX)]

    # Fondu d'entrée court (le son doit être là dès la 1re seconde), sortie 1,5 s.
    ent, sor = int(0.25 * TAUX), int(min(1.5, duree / 4) * TAUX)
    st[:ent] *= np.linspace(0, 1, ent)[:, None]
    st[-sor:] *= np.linspace(1, 0, sor)[:, None]
    crete = np.max(np.abs(st)) or 1.0
    return np.tanh(1.2 * st / crete) * 0.85      # légère saturation douce, sans écrêtage


# --- Style « adrénaline » (drift phonk), 7 oct. -------------------------------
# L'opérateur : « musique adrénaline, un passage persistant, pas le début ».
# Pour Facebook, la musique de la bibliothèque Instagram n'est pas disponible
# (bundle.social ne la pose que sur Instagram) : la vidéo doit PORTER sa musique.
# Ce morceau démarre à pleine énergie dès la première seconde, sans intro.

def _cloche(freq: float, duree: float) -> np.ndarray:
    """La « cowbell » du phonk : deux carrés désaccordés, attaque sèche, saturés."""
    n = int(duree * TAUX)
    t = np.arange(n) / TAUX
    s = np.sign(np.sin(2 * np.pi * freq * t)) + 0.8 * np.sign(np.sin(2 * np.pi * freq * 1.48 * t))
    s = np.convolve(s, np.ones(6) / 6, mode="same")          # adoucit les arêtes
    return np.tanh(2.5 * s) * _enveloppe(n, 0.001, 0.09)


def _basse808(freq: float, duree: float) -> np.ndarray:
    n = int(duree * TAUX)
    t = np.arange(n) / TAUX
    f = freq * (1 + 1.5 * np.exp(-t / 0.03))                  # petit « pitch drop » d'attaque
    s = np.sin(2 * np.pi * np.cumsum(f) / TAUX)
    return np.tanh(3.5 * s) * _enveloppe(n, 0.003, max(0.25, duree * 0.8))


def composer_phonk(duree: float, graine: str = "alluxe") -> np.ndarray:
    g = _graine(graine)
    rng = np.random.default_rng(g)
    bpm = 138 + (g % 8)
    croche = 60 / bpm / 2                     # une double-croche = un quart de temps
    dc = croche / 2
    tonique = 50 + (g % 5)                    # ré à fa#, en mineur
    n = int(duree * TAUX) + TAUX
    batt, basse, cloche = (np.zeros(n) for _ in range(3))
    # Riff de cloche sur 2 mesures (32 doubles-croches), degrés du mineur phrygien.
    riff = [0, None, 0, None, 3, None, 0, 7, None, 5, None, 3, None, 5, 3, None,
            0, None, 0, None, 3, None, 0, 8, None, 7, None, 5, 3, None, 1, None]
    ligne_basse = [0, 0, 0, 0, -2, -2, 1, 1]  # une note par demi-mesure
    k = 0
    while k * dc < duree + 1:
        pos = k % 32
        tps = k * dc
        if riff[pos] is not None:
            _poser(cloche, _cloche(_hz(tonique + 24 + riff[pos]), dc * 1.6), tps, 0.32)
        if pos % 8 == 0 or pos in (6, 11, 22, 27):               # kick sec et syncopé
            _poser(batt, _kick(int(0.25 * TAUX)), tps, 0.95)
        if pos % 16 == 8:                                        # clap en demi-tempo
            _poser(batt, _bruit(int(0.2 * TAUX), 0.09, rng, 3), tps, 0.55)
        ch = 0.16 if pos % 2 == 0 else 0.09                      # charleston serré
        _poser(batt, np.diff(_bruit(int(0.04 * TAUX), 0.012, rng, 1), prepend=0), tps, ch)
        if pos in (29, 30, 31) and (k // 32) % 2 == 1:           # roulement de triolets
            for r in range(3):
                _poser(batt, np.diff(_bruit(int(0.03 * TAUX), 0.01, rng, 1), prepend=0), tps + r * dc / 3, 0.1)
        if pos % 4 == 0:
            note = ligne_basse[(k // 4) % 8]
            _poser(basse, _basse808(_hz(tonique - 12 + note), dc * 4), tps, 0.6)
        k += 1
    mix = batt + basse * 0.9 + _echo(cloche, croche * 1.5, 0.25, 2)
    mix = mix[: int(duree * TAUX)]
    st = np.stack([mix + 0.15 * np.roll(cloche[: len(mix)], 300), mix + 0.15 * np.roll(cloche[: len(mix)], -300)], axis=1)
    fondu = int(0.25 * TAUX); st[-fondu:] *= np.linspace(1, 0, fondu)[:, None]
    crete = np.max(np.abs(st)) or 1.0
    return np.tanh(1.6 * st / crete) * 0.9


def ecrire_wav(chemin: str, duree: float, graine: str = "alluxe", style: str = "lofi") -> str:
    st = composer_phonk(duree, graine) if style == "phonk" else composer(duree, graine)
    with wave.open(chemin, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(TAUX)
        w.writeframes((st * 32767).astype("<i2").tobytes())
    return chemin


if __name__ == "__main__":
    print(ecrire_wav(sys.argv[2], float(sys.argv[1]), sys.argv[3] if len(sys.argv) > 3 else "alluxe"))
