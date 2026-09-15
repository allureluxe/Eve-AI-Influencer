"""Alluxe : l'agent qui combine script, photo, voix et video pour Luna.

Une seule demande en langage naturel, quatre etapes automatiques :

    python3 alluxe.py "un post Instagram sur son week-end au ski"

1. SCRIPT   -- le moteur de conversation deja branche pour Luna (Groq)
   ecrit la legende ET decrit la scene a illustrer, dans son personnage.
2. PHOTO    -- GenerateurImages (Hugging Face / Cloudflare / Stability,
   repli automatique entre les trois) illustre cette scene.
3. VOIX     -- gTTS (gratuit, sans cle -- voir requirements-alluxe.txt)
   lit la legende a voix haute.
4. VIDEO    -- ffmpeg (local, gratuit) assemble la photo et la voix en
   une courte video avec un leger effet de zoom, pour eviter l'image
   figee.

Chaque etape peut echouer independamment sans bloquer les autres :
`Resultat` rend ce qui a marche, avec les erreurs a cote. Rien de tout
ca n'est un "avatar qui parle" (voir HeyGen/D-ID pour ca, payant) --
c'est une photo + une voix off, ce que le gratuit permet aujourd'hui.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime

from .moteurs import ErreurMoteur, GenerateurImages, choisir_moteur
from .persona import LUNA, Persona
from .photos import NEGATIF, RENDU, SIGNATURE

DOSSIER_DEFAUT = "contenu_alluxe"

SYSTEME_SCRIPT = """{presentation}

Tu ecris du contenu pour les reseaux sociaux de {prenom}, dans son personnage.
On te donne un sujet. Tu rends EXACTEMENT deux lignes, rien d'autre :

LEGENDE: une legende courte, en francais, dans le ton de {prenom} (voir CARACTERE), avec 1 a 2 emojis maximum.
SCENE: une description en ANGLAIS de la scene a photographier pour illustrer ce post -- le decor, la tenue, la pose, l'expression. Pas de nom propre, pas de marque. Une seule phrase dense.

CARACTERE :
{caractere}
"""


@dataclass
class Resultat:
    demande: str
    legende: str = ""
    scene_prompt: str = ""
    dossier: str = ""
    chemin_script: str = ""
    chemin_image: str = ""
    chemin_voix: str = ""
    chemin_video: str = ""
    erreurs: dict[str, str] = field(default_factory=dict)

    def resume(self) -> str:
        lignes = [f"Demande : {self.demande}"]
        if self.legende:
            lignes.append(f"Legende : {self.legende}")
        for cle, chemin in (("Script", self.chemin_script), ("Photo", self.chemin_image),
                            ("Voix", self.chemin_voix), ("Video", self.chemin_video)):
            if chemin:
                lignes.append(f"{cle:<8} : {chemin}")
        for etape, erreur in self.erreurs.items():
            lignes.append(f"! {etape:<8} : {erreur}")
        return "\n".join(lignes)


def _ecrire_script(demande: str, moteur, persona: Persona = LUNA) -> tuple[str, str]:
    """Rend (legende, scene_prompt). Leve ErreurMoteur si le moteur echoue."""
    systeme = SYSTEME_SCRIPT.format(
        presentation=persona.presentation(), prenom=persona.prenom,
        caractere="\n".join(f"- {t}" for t in persona.caractere))
    tours = [{"role": "user", "texte": demande}]
    brut = moteur.repondre(systeme, tours)
    legende, scene = "", ""
    for ligne in brut.splitlines():
        if ligne.upper().startswith("LEGENDE:"):
            legende = ligne.split(":", 1)[1].strip()
        elif ligne.upper().startswith("SCENE:"):
            scene = ligne.split(":", 1)[1].strip()
    if not legende or not scene:
        raise ErreurMoteur(f"reponse inattendue du moteur : {brut[:200]}")
    return legende, scene


def _generer_photo(scene_prompt: str, images: GenerateurImages, persona: Persona = LUNA) -> bytes:
    if not images.disponible:
        raise ErreurMoteur("aucun generateur d'images configure")
    prompt = ", ".join((persona.apparence.ancre, scene_prompt, RENDU, SIGNATURE))
    return images.generer(prompt, NEGATIF, persona.apparence.graine)


def _generer_voix(texte: str, chemin: str) -> None:
    try:
        from gtts import gTTS
    except ImportError as e:
        raise RuntimeError(
            "gTTS non installe -- pip install -r requirements-alluxe.txt "
            "(idealement dans un venv separe, voir .venv-luna)") from e
    # gTTS n'aime pas les emojis : on les retire avant de les envoyer.
    propre = "".join(c for c in texte if c.isascii() or c.isalpha())
    gTTS(text=propre or texte, lang="fr").save(chemin)


def _assembler_video(image: str, audio: str, video: str) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg n'est pas installe (sudo apt install ffmpeg)")
    # Effet de zoom lent (Ken Burns) sur l'image fixe, calee sur la duree de
    # l'audio : sans ca, une photo immobile pendant 10-20 secondes ne
    # ressemble a rien. zoompan a besoin d'un nombre de frames fixe -- 25
    # images/seconde, duree prise sur l'audio par -shortest.
    commande = [
        "ffmpeg", "-y", "-loop", "1", "-i", image, "-i", audio,
        "-vf", "scale=1024:1536,zoompan=z='min(zoom+0.0015,1.2)':d=1:s=1024x1536,format=yuv420p",
        "-r", "25", "-c:v", "libx264", "-c:a", "aac", "-shortest", "-movflags", "+faststart",
        video,
    ]
    r = subprocess.run(commande, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg : {r.stderr[-300:]}")


def creer(demande: str, dossier_racine: str = DOSSIER_DEFAUT,
          persona: Persona = LUNA, moteur=None,
          images: GenerateurImages | None = None) -> Resultat:
    """Enchaine script -> photo -> voix -> video pour une demande donnee.

    `moteur`/`images` s'injectent pour les tests (moteur/generateur
    factices) ; par defaut, ceux reellement configures dans .env.
    """
    moteur = moteur or choisir_moteur()
    images = images if images is not None else GenerateurImages()
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    dossier = os.path.join(dossier_racine, horodatage)
    os.makedirs(dossier, exist_ok=True)
    resultat = Resultat(demande=demande, dossier=dossier)

    try:
        legende, scene_prompt = _ecrire_script(demande, moteur, persona)
        resultat.legende, resultat.scene_prompt = legende, scene_prompt
        resultat.chemin_script = os.path.join(dossier, "script.txt")
        with open(resultat.chemin_script, "w", encoding="utf-8") as f:
            f.write(f"{legende}\n\n[scene: {scene_prompt}]\n")
    except ErreurMoteur as e:
        resultat.erreurs["script"] = str(e)
        return resultat  # sans legende, rien d'autre n'est possible

    try:
        brut = _generer_photo(scene_prompt, images, persona)
        resultat.chemin_image = os.path.join(dossier, "photo.png")
        with open(resultat.chemin_image, "wb") as f:
            f.write(brut)
    except ErreurMoteur as e:
        resultat.erreurs["photo"] = str(e)

    try:
        resultat.chemin_voix = os.path.join(dossier, "voix.mp3")
        _generer_voix(legende, resultat.chemin_voix)
    except (RuntimeError, OSError) as e:
        resultat.erreurs["voix"] = str(e)
        resultat.chemin_voix = ""

    if resultat.chemin_image and resultat.chemin_voix:
        try:
            resultat.chemin_video = os.path.join(dossier, "video.mp4")
            _assembler_video(resultat.chemin_image, resultat.chemin_voix, resultat.chemin_video)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            resultat.erreurs["video"] = str(e)
            resultat.chemin_video = ""

    with open(os.path.join(dossier, "resultat.json"), "w", encoding="utf-8") as f:
        json.dump({
            "demande": demande, "legende": resultat.legende,
            "scene_prompt": resultat.scene_prompt, "erreurs": resultat.erreurs,
        }, f, ensure_ascii=False, indent=2)

    return resultat
