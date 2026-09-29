"""Le montage standard d'une video de Luna — un seul endroit qui le sait.

POURQUOI CE FICHIER EXISTE

Dans la nuit du 26 au 27 septembre, la vitesse d'un Reel a ete reglee a
la main six fois de suite : x1,15 trop lent, x1,3 « parfait », x1,8
« beaucoup trop rapide », retour a x1,3. A chaque nouvelle video je
refaisais le reglage de tete, et l'operateur a tranche :

    « t'as oublie l'acceleration, enregistre-le pour que les videos
      soient toujours a la meme vitesse »

Une valeur qu'on retape a chaque fois n'est pas un reglage, c'est un
souvenir — et il derive. Les trois constantes ci-dessous sont les
valeurs qu'il a validees ; elles vivent ici et nulle part ailleurs.

CE QUE LE MONTAGE FAIT, ET POURQUOI CHAQUE ETAPE EST LA

1. ACCELERATION x1,3. Kling rend un mouvement naturellement mou. x1,15
   restait endormi, x1,8 virait a l'avance rapide. 1,3 est le reglage
   valide, deux fois.

2. 48 IMAGES/SECONDE PAR INTERPOLATION. Accelerer seul fait sauter le
   mouvement : la source est a 24 i/s, et a 1,3x l'oeil voit les ecarts
   entre images. `minterpolate` suit le deplacement de chaque zone et
   CALCULE les images manquantes. C'est ce qui repond a « ca manque de
   fluidite ». C'est aussi l'etape lente (~5 min pour 10 s).

3. COUPE A 5 SECONDES. Choix de l'operateur : « 5 secondes c'est mieux ».
   Un Reel court boucle deux ou trois fois sans que le spectateur s'en
   apercoive, et chaque boucle compte comme une vue.

4. SORTIE EN 1080x1920. **Kling ne rend PAS du 9:16** : il suit le
   format de l'image de depart, et `gpt-image-2` ne sait produire que du
   1024x1536, soit du 2:3. Poste tel quel, Instagram recadre lui-meme et
   decide a notre place ce qu'il coupe. Le fond flou sombre comble le
   haut et le bas sans rien perdre de l'image — invisible sur une scene
   de nuit.

    from luna.montage import monter
    monter("brute.mp4", "reel.mp4")
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

#: Les valeurs validees par l'operateur dans la nuit du 26 au 27 septembre.
VITESSE = 1.3
IMAGES_PAR_SECONDE = 48
DUREE_MAX_S = 5.0
LARGEUR, HAUTEUR = 1080, 1920

#: Le fond qui comble le haut et le bas quand la video n'est pas en 9:16 :
#: la meme image, agrandie, floutee et assombrie.
_FOND = (
    f"[0:v]scale={LARGEUR}:{HAUTEUR}:force_original_aspect_ratio=increase,"
    f"crop={LARGEUR}:{HAUTEUR},boxblur=30:3,eq=brightness=-0.15[bg];"
    f"[0:v]scale={LARGEUR}:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"
)


class MontageErreur(RuntimeError):
    pass


def _ffmpeg(*args: str) -> None:
    """ffmpeg en priorite basse : le VPS fait tourner trois robots.

    `nice` n'est pas du confort ici — un encodage a pleine priorite a
    deja fait tuer le robot de demo par le noyau, faute de memoire.
    """
    binaire = shutil.which("ffmpeg")
    if not binaire:
        raise MontageErreur("ffmpeg introuvable")
    r = subprocess.run(["nice", "-n", "19", binaire, "-v", "error", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise MontageErreur(f"ffmpeg a echoue : {r.stderr[-400:]}")


def monter(source: str | Path, sortie: str | Path, *,
           vitesse: float = VITESSE,
           duree_max_s: float = DUREE_MAX_S) -> Path:
    """Rend le chemin de la video montee, prete a publier en Reel.

    En DEUX passes et non une seule : l'interpolation doit travailler sur
    la video a sa taille d'origine. La faire apres la mise au format
    9:16 lui ferait calculer le mouvement du fond flou aussi — plus lent,
    et sans aucun interet.
    """
    source, sortie = Path(source), Path(sortie)
    if not source.is_file():
        raise MontageErreur(f"video introuvable : {source}")

    intermediaire = sortie.with_name(sortie.stem + "-tmp.mp4")
    try:
        _ffmpeg("-i", str(source),
                "-vf", (f"setpts=PTS/{vitesse},"
                        f"minterpolate=fps={IMAGES_PAR_SECONDE}:mi_mode=mci:"
                        f"mc_mode=aobmc:me_mode=bidir:vsbmc=1"),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-pix_fmt", "yuv420p", "-an", str(intermediaire), "-y")
        _ffmpeg("-t", f"{duree_max_s}", "-i", str(intermediaire),
                "-filter_complex", _FOND,
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
                "-pix_fmt", "yuv420p", "-r", str(IMAGES_PAR_SECONDE),
                "-movflags", "+faststart", "-an", str(sortie), "-y")
    finally:
        intermediaire.unlink(missing_ok=True)
    return sortie
