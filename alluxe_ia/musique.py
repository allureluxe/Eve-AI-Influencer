"""La musique des Reels et Stories de @alluxe.ia, composée par programme.

Pourquoi composer plutôt que télécharger : un morceau « libre de droits »
pris sur un site peut être reconnu par Instagram et rendre la vidéo muette
ou bloquée. Une musique synthétisée ici n'appartient à personne d'autre :
aucun risque de droits.

Pourquoi pas la musique d'Instagram : depuis mai 2026, Meta ne l'ouvre aux
programmes que pour les Reels, et seulement aux comptes reliés par
**Facebook** — le nôtre l'est par la connexion « Instagram ». Jamais pour
les Stories. Un Reel muet part avec un gros handicap (4 oct. : 5 vues).

Style : depuis le 4 oct., des beats « jeunes » (phonk, funk brésilien,
drill, afro, trap) choisis selon le sujet ; le lo-fi au piano d'origine
reste disponible (style="lofi") mais n'est plus utilisé par défaut. Chaque `graine` donne une tonalité, une grille
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


def _lofi(duree: float, graine: str = "alluxe", bpm: float | None = None) -> np.ndarray:
    """Le lo-fi au piano d'origine. Plus utilisé par défaut depuis le 4 oct.
    (« le piano endort ») ; gardé pour un tuto très calme : style="lofi".

    `bpm` impose le tempo (le Reel cale ses changements de texte dessus,
    4 oct.) ; au-dessus de 100, on joue en demi-tempo, comme le lo-fi."""
    g = _graine(graine)
    rng = np.random.default_rng(g)
    tonique = 57 + (g % 7) - 3                 # autour de La grave
    grille = GRILLES[(g >> 3) % len(GRILLES)]
    if bpm is None:
        bpm = 78 + (g >> 6) % 14                # 78 à 91
    elif bpm > 100:
        bpm = bpm / 2                           # demi-tempo : 1 temps = 2 temps du Reel
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


# ---------------------------------------------------------------- beats « jeunes »
#
# 4 oct., opérateur : « pas de piano, ça endort ; des musiques tendance jeune
# qui attirent, adaptées au sujet ». Cinq styles qui tournent sur les
# Reels, tous synthétisés ici (aucun droit d'auteur) :
#   phonk   cloche (cowbell) en riff, 808 saturée, charleston en roulements
#   funk    funk brésilien : rythme « tamborzão », stabs, grosse caisse dense
#   drill   demi-tempo, 808 qui glisse, charleston en triolets, cloche sombre
#   afro    log drum, shaker en doubles croches, clap sur 2 et 4, marimba
#   trap    808, charleston en roulements, cloche aiguë
# Le style vient du sujet (reel.py, ambiance -> STYLE_DE_L_AMBIANCE).

STYLES = ("phonk", "funk", "drill", "afro", "trap")
GAMME_MINEURE = (0, 2, 3, 5, 7, 8, 10)
PHRYGIEN = (0, 1, 3, 5, 7, 8, 10)


def _env(n: int, chute: float, attaque: float = 0.002) -> np.ndarray:
    return _enveloppe(n, attaque, chute)


def _kick_dur(force: float = 1.0) -> np.ndarray:
    n = int(0.45 * TAUX)
    t = np.arange(n) / TAUX
    f = 50 + 140 * np.exp(-t / 0.03)
    ph = 2 * np.pi * np.cumsum(f) / TAUX
    clic = np.diff(np.random.default_rng(7).standard_normal(n), prepend=0) * _env(n, 0.004)
    return 0.55 * np.tanh(2.2 * force * np.sin(ph) * _env(n, 0.09)) + 0.15 * clic


def _snare(rng, clap: bool = False) -> np.ndarray:
    n = int(0.25 * TAUX)
    bruit = rng.standard_normal(n)
    bruit = np.diff(bruit, prepend=0)              # plus brillant
    t = np.arange(n) / TAUX
    corps = 0 if clap else 0.5 * np.sin(2 * np.pi * 190 * t) * _env(n, 0.05)
    if clap:                                       # trois petites claques rapprochées
        env = sum(_env(n, 0.012) * (np.arange(n) >= int(d * TAUX)) for d in (0, 0.009, 0.018))
        env = env + _env(n, 0.09) * 0.6
    else:
        env = _env(n, 0.09)
    return 0.6 * bruit * env + corps


def _hat(rng, ouvert: bool = False) -> np.ndarray:
    n = int((0.2 if ouvert else 0.05) * TAUX)
    b = np.diff(rng.standard_normal(n), prepend=0)
    return 0.3 * b * _env(n, 0.07 if ouvert else 0.015)


def _808(freq: float, duree: float, vers: float | None = None, sature: float = 4.0) -> np.ndarray:
    n = int(duree * TAUX)
    t = np.arange(n) / TAUX
    f = np.full(n, freq)
    if vers:                                       # la glissade de la drill
        g = np.clip((t - duree * 0.55) / 0.08, 0, 1)
        f = freq + (vers - freq) * g
    f = f * (1 + 0.6 * np.exp(-t / 0.02))          # attaque qui « claque »
    ph = 2 * np.pi * np.cumsum(f) / TAUX
    env = _env(n, max(0.25, duree * 0.8), 0.003)
    rel = min(n, int(0.03 * TAUX))
    env[-rel:] *= np.linspace(1, 0, rel)
    return np.tanh(sature * np.sin(ph) * env) / np.tanh(sature)


def _cloche(freq: float, duree: float = 0.22) -> np.ndarray:
    """La cowbell de la phonk : deux carrés désaccordés, filtrés."""
    n = int(duree * TAUX)
    t = np.arange(n) / TAUX
    x = np.sign(np.sin(2 * np.pi * freq * t)) + np.sign(np.sin(2 * np.pi * freq * 1.48 * t))
    x = np.diff(x, prepend=0) * 0.5 + 0.15 * x      # passe-haut grossier
    return 0.35 * x * _env(n, 0.09)


def _log_drum(freq: float) -> np.ndarray:
    n = int(0.35 * TAUX)
    t = np.arange(n) / TAUX
    f = freq * (1 + 0.5 * np.exp(-t / 0.03))
    ph = 2 * np.pi * np.cumsum(f) / TAUX
    return np.tanh(1.8 * np.sin(ph) * _env(n, 0.12)) * 0.8


def _marimba(freq: float) -> np.ndarray:
    n = int(0.4 * TAUX)
    t = np.arange(n) / TAUX
    return (np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 4 * t) * _env(n, 0.02)) \
        * _env(n, 0.18) * 0.35


def _stab(freq: float, duree: float = 0.12) -> np.ndarray:
    """Petit accord carré court, le « stab » du funk."""
    n = int(duree * TAUX)
    t = np.arange(n) / TAUX
    x = sum(np.sign(np.sin(2 * np.pi * freq * r * t)) for r in (1, 1.189, 1.498))
    return 0.12 * x * _env(n, 0.05)


def _beat(duree: float, style: str, bpm: float, graine: str) -> np.ndarray:
    g = _graine(graine + style)
    rng = np.random.default_rng(g)
    tonique = 33 + g % 7                            # La1 à Ré#2 : la zone de la 808
    gamme = PHRYGIEN if style == "phonk" else GAMME_MINEURE
    pas = 60.0 / bpm / 4                            # double croche
    n = int((duree + 1.0) * TAUX)
    batt, basse, mel = np.zeros(n), np.zeros(n), np.zeros(n)
    hz = lambda deg, oct=0: _hz(tonique + 12 * oct + gamme[deg % 7] + 12 * (deg // 7))  # noqa: E731
    nb_mesures = int(np.ceil((duree + 0.5) / (16 * pas)))
    progression = [0, 0, 5, 3] if style != "afro" else [0, 3, 5, 4]
    riff = [rng.integers(0, 7) for _ in range(8)]
    riff[0] = 0
    for m in range(nb_mesures):
        d0 = m * 16 * pas
        racine = progression[m % 4]
        for k in range(16):
            t = d0 + k * pas
            if style == "phonk":
                if k in (0, 10) or (k == 7 and m % 2):
                    _poser(batt, _kick_dur(), t, 0.9)
                    _poser(basse, _808(hz(racine), 6 * pas), t, 0.55)
                if k == 8:
                    _poser(batt, _snare(rng), t, 0.7)
                if k % 2 == 0 or (m % 2 and k >= 12):
                    _poser(batt, _hat(rng), t, 0.6)
                if k % 2 == 0:
                    deg = riff[(k // 2) % 8] + racine
                    _poser(mel, _cloche(hz(deg, 3)), t, 0.5)
            elif style == "funk":
                if k in (0, 3, 6, 10, 12):
                    _poser(batt, _kick_dur(1.2), t, 0.9)
                if k in (4, 12):
                    _poser(batt, _snare(rng, clap=True), t, 0.7)
                if k in (2, 7, 14):
                    _poser(batt, _snare(rng), t, 0.35)     # le « tamborzão »
                if k % 2 == 1:
                    _poser(batt, _hat(rng), t, 0.5)
                if k in (0, 6, 10):
                    _poser(basse, _808(hz(racine), 3 * pas, sature=3.5), t, 0.5)
                if k in (3, 11):
                    _poser(mel, _stab(hz(racine + 2, 2)), t, 0.7)
            elif style == "drill":
                if k in (0, 11) or (k == 6 and m % 2):
                    _poser(batt, _kick_dur(), t, 0.85)
                if k == 0:
                    vers = hz(racine + (2 if m % 2 else -1))
                    _poser(basse, _808(hz(racine), 14 * pas, vers=vers), t, 0.6)
                if k == 8:
                    _poser(batt, _snare(rng), t, 0.75)
                if k in (0, 3, 6, 8, 11, 14) or (k == 12 and m % 2):
                    _poser(batt, _hat(rng), t, 0.55)
                    if k == 12:                                 # triolet
                        for r in (1, 2):
                            _poser(batt, _hat(rng), t + r * pas * 2 / 3, 0.45)
                if k in (0, 3, 6):
                    _poser(mel, _marimba(hz(riff[k % 8] + racine, 2)), t, 0.55)
            elif style == "afro":
                if k in (0, 8) or (k == 6 and m % 2):
                    _poser(batt, _kick_dur(0.8), t, 0.75)
                if k in (4, 12):
                    _poser(batt, _snare(rng, clap=True), t, 0.5)
                _poser(batt, _hat(rng), t, 0.32 if k % 2 else 0.18)   # shaker
                if k in (3, 6, 10, 14):
                    _poser(basse, _log_drum(hz(racine + (k // 5), 1)), t, 0.5)
                if k in (0, 3, 7, 10, 12):
                    _poser(mel, _marimba(hz(riff[k % 8] + racine, 2)), t, 0.5)
            else:  # trap
                if k in (0, 7, 10):
                    _poser(batt, _kick_dur(), t, 0.85)
                    _poser(basse, _808(hz(racine), 5 * pas), t, 0.55)
                if k in (4, 12):
                    _poser(batt, _snare(rng, clap=True), t, 0.7)
                _poser(batt, _hat(rng), t, 0.5 if k % 2 == 0 else 0.3)
                if k == 14 and m % 2:                            # roulement
                    for r in range(1, 4):
                        _poser(batt, _hat(rng), t + r * pas / 3, 0.4)
                if k in (0, 6, 12):
                    _poser(mel, _marimba(hz(riff[k % 8] + racine, 3)), t, 0.4)
    # Un téléphone ne rend presque rien sous 150 Hz : la 808 est saturée
    # (ses harmoniques s'entendent), et la mélodie passe devant.
    mono = batt + 0.6 * basse + 2.6 * mel
    gauche = mono + 0.08 * np.roll(mel, int(0.012 * TAUX))
    droite = mono + 0.08 * np.roll(mel, int(0.019 * TAUX))
    st = np.stack([gauche, droite], axis=1)[: int(duree * TAUX)]
    sor = int(min(1.0, duree / 6) * TAUX)
    st[-sor:] *= np.linspace(1, 0, sor)[:, None]
    crete = np.max(np.abs(st)) or 1.0
    return np.tanh(1.4 * st / crete) * 0.9


TEMPO_DU_STYLE = {"phonk": 140, "funk": 130, "drill": 142, "afro": 108, "trap": 140}


def composer(duree: float, graine: str = "alluxe", bpm: float | None = None,
             style: str | None = None) -> np.ndarray:
    """Un beat stéréo (n, 2), entre -1 et 1. Sans style : un des cinq
    styles jeunes, fixé par la graine (toujours le même pour un Reel)."""
    if style == "lofi":
        return _lofi(duree, graine, bpm)
    style = style or STYLES[_graine(graine) % len(STYLES)]
    return _beat(duree, style, bpm or TEMPO_DU_STYLE[style], graine)


def ecrire_wav(chemin: str, duree: float, graine: str = "alluxe",
               bpm: float | None = None, style: str | None = None) -> str:
    st = composer(duree, graine, bpm, style)
    with wave.open(chemin, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(TAUX)
        w.writeframes((st * 32767).astype("<i2").tobytes())
    return chemin


if __name__ == "__main__":
    print(ecrire_wav(sys.argv[2], float(sys.argv[1]), sys.argv[3] if len(sys.argv) > 3 else "alluxe"))
