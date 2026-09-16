"""Alluxe v2 : combine script, photo, voix et video pour Luna.

(Nom "v2" pour ne pas se confondre avec "Alluxe" tout court, le futur
agent vocal personnel -- voir alluxe_v2.py a la racine du depot.)

Une demande en langage naturel -- ou aucune -- et quatre etapes
automatiques :

    python3 alluxe_v2.py "un post Instagram sur son week-end au ski"
    python3 alluxe_v2.py                 (Luna improvise toute seule)

1. SCRIPT   -- le moteur de conversation (Groq, puis Claude, puis
   hors-ligne -- `MoteurAvecRepli`) ecrit la legende ET decrit la scene,
   dans le personnage de Luna. C'EST LUI qui choisit la tenue, le lieu,
   l'humeur et la pose, cale sur le moment de la journee -- pas nous.
2. PHOTO    -- GenerateurImages (Hugging Face / Cloudflare / Stability,
   repli automatique entre les trois) illustre cette scene.
3. VOIX     -- Edge TTS (voix neuronale, gratuite), puis gTTS en repli.
4. VIDEO    -- ffmpeg (local, gratuit) assemble la photo et la voix en
   une courte video avec un effet de zoom (Ken Burns), et retombe sur
   une version sans zoom si l'effet echoue.

Chaque etape ET chaque fournisseur a l'interieur d'une etape peuvent
echouer independamment sans bloquer le reste : `Resultat` rend ce qui a
marche, avec les erreurs a cote -- meme discipline partout (texte,
image, voix, video), demandee par l'operateur le 15 sept. Rien de tout
ca n'est un "avatar qui parle" (voir HeyGen/D-ID pour ca, payant) --
c'est une photo + une voix off, ce que le gratuit permet aujourd'hui.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

from .moments import moment_pour
from .moteurs import ErreurMoteur, GenerateurImages, choisir_moteur
from .persona import LUNA, Persona
from .photos import NEGATIF, RENDU, SIGNATURE

logger = logging.getLogger(__name__)

DOSSIER_DEFAUT = "contenu_alluxe"

# 15 sept., 2e passage : l'operateur veut Luna AUTONOME a terme -- c'est
# elle (le moteur, ici) qui doit decider la tenue, le lieu, l'humeur,
# la pose, pas nous a chaque fois. Le sujet donne (`demande`) peut donc
# rester tres vague, voire vide -- le moment de la journee (deja code
# dans luna.moments) et CONTEXTE/CARACTERE suffisent a improviser un
# post credible. Deux consignes ajoutees explicitement, parce que sans
# elles le modele reproduit toujours le meme sourire/la meme pose d'une
# generation a l'autre (constate le 15 sept.) :
#   - varier expression ET pose a chaque fois, jamais le meme sourire
#   - decrire une vraie photo amateur, pas un shooting (deja renforce
#     par RENDU/NEGATIF ensuite, mais le demander ici aussi aide le
#     modele a proposer une pose/un cadrage coherents avec ce rendu)
SYSTEME_SCRIPT = """{presentation}

MOMENT ACTUEL : {moment_nom}. {moment_ambiance}

Tu ecris du contenu pour les reseaux sociaux de {prenom}, dans son personnage.
On te donne un sujet, parfois tres vague voire absent -- dans ce cas
c'est TOI qui inventes un post credible et interessant, coherent avec
le moment actuel, son caractere et son contexte. C'est TOI qui decides
la tenue, le lieu, l'humeur et la pose : on ne te les impose jamais.
Tu rends EXACTEMENT deux lignes, rien d'autre :

LEGENDE: une legende courte, en francais, dans le ton de {prenom} (voir CARACTERE), avec 1 a 2 emojis maximum.
SCENE: une description en ANGLAIS de la scene a photographier pour illustrer ce post -- le decor, la tenue, LA POSE et L'EXPRESSION precises. Pas de nom propre, pas de marque. Une seule phrase dense. Choisis une pose et une expression DIFFERENTES de ce qu'on fait d'habitude (souris pas toujours de la meme facon : parfois elle rit, parfois elle est concentree, pensive, surprise, taquine...). Decris une vraie photo amateur prise au telephone, pas un shooting professionnel.

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


def _debut(ligne: str, prefixe: str) -> bool:
    """`ligne` commence-t-elle par `prefixe`, en ignorant accents/majuscules ?"""
    sans_accent = "".join(c for c in unicodedata.normalize("NFKD", ligne)
                           if not unicodedata.combining(c))
    return sans_accent.upper().startswith(prefixe)


def _ecrire_script(demande: str, moteur, persona: Persona = LUNA) -> tuple[str, str]:
    """Rend (legende, scene_prompt). Leve ErreurMoteur si le moteur echoue.

    `demande` peut etre vide : c'est le moteur qui invente alors un post,
    cale sur le moment actuel et le personnage -- c'est ce qui rend Luna
    autonome plutot que dependante d'un sujet donne a chaque fois.
    """
    moment = moment_pour(datetime.now())
    systeme = SYSTEME_SCRIPT.format(
        presentation=persona.presentation(), prenom=persona.prenom,
        moment_nom=moment.nom, moment_ambiance=moment.ambiance,
        caractere="\n".join(f"- {t}" for t in persona.caractere))
    demande_effective = demande.strip() or (
        "(aucun sujet donne -- improvise un post credible pour ce moment)")
    tours = [{"role": "user", "texte": demande_effective}]
    brut = moteur.repondre(systeme, tours)
    legende, scene = "", ""
    for ligne in brut.splitlines():
        # Le moteur derive parfois vers "LEGEND:" (anglais) au lieu de
        # "LEGENDE:" -- constate le 16 sept. sur une reponse Groq par
        # ailleurs correcte. `_debut()` ignore accents/E final pour ne
        # pas jeter tout un script a cause d'une seule lettre en trop.
        if _debut(ligne, "LEGEND"):
            legende = ligne.split(":", 1)[1].strip()
        elif _debut(ligne, "SCEN"):
            scene = ligne.split(":", 1)[1].strip()
    if not legende or not scene:
        raise ErreurMoteur(f"reponse inattendue du moteur : {brut[:200]}")
    return legende, scene


def _generer_photo(scene_prompt: str, images: GenerateurImages, persona: Persona = LUNA) -> bytes:
    if not images.disponible:
        raise ErreurMoteur("aucun generateur d'images configure")
    prompt = ", ".join((persona.apparence.ancre, scene_prompt, RENDU, SIGNATURE))
    return images.generer(prompt, NEGATIF, persona.apparence.graine)


# Voix neuronale Microsoft Edge (gratuite, sans cle) plutot que gTTS :
# gTTS lit de façon plate et mecanique, jugee "pas naturelle" par
# l'operateur le 15 sept. Denise est une voix adulte feminine standard,
# la mieux etablie du catalogue francais ; rate/pitch relevés donnent un
# ton plus jeune et energique, cohérent avec Luna (22 ans). Eloise
# (l'autre voix feminine du catalogue) est ecartee : c'est une voix
# d'enfant chez Microsoft, incompatible avec le personnage adulte.
VOIX_EDGE = "fr-FR-DeniseNeural"
VOIX_RATE = "+8%"
VOIX_PITCH = "+15Hz"


def _voix_edge(propre: str, chemin: str) -> None:
    import asyncio
    import edge_tts

    async def _parler() -> None:
        communicateur = edge_tts.Communicate(propre, VOIX_EDGE, rate=VOIX_RATE, pitch=VOIX_PITCH)
        await communicateur.save(chemin)

    asyncio.run(_parler())


def _voix_gtts(propre: str, chemin: str) -> None:
    from gtts import gTTS
    gTTS(text=propre, lang="fr").save(chemin)


def _generer_voix(texte: str, chemin: str) -> None:
    """Repli : Edge TTS (voix neuronale, la plus naturelle) puis gTTS si
    Edge echoue (reseau, service Microsoft indisponible...). Meme
    discipline que pour les moteurs de texte et d'images -- une panne
    d'un seul fournisseur ne doit plus laisser Luna sans voix du tout."""
    # Les deux moteurs lisent les emojis a voix haute ("coeur", "etincelles"...)
    # -- on les retire avant de les envoyer.
    propre = "".join(c for c in texte if c.isascii() or c.isalpha() or c in " ,.!?'-") or texte

    derniere: Exception | None = None
    for nom, fournisseur in (("edge-tts", _voix_edge), ("gTTS", _voix_gtts)):
        try:
            fournisseur(propre, chemin)
            return
        except ImportError as e:
            derniere = RuntimeError(
                f"{nom} non installe -- pip install -r requirements-alluxe.txt "
                "(idealement dans un venv separe, voir .venv-luna)")
        except Exception as e:                                  # noqa: BLE001
            derniere = RuntimeError(f"{nom} : {e}")
        logger.warning("voix %s indisponible (%s) -- on essaie le suivant "
                       "si un autre est configure.", nom, derniere)
    raise derniere or RuntimeError("aucun moteur de voix disponible")


def _duree_audio(audio: str) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio],
        capture_output=True, text=True, timeout=30)
    try:
        return max(float(r.stdout.strip()), 1.0)
    except ValueError as e:
        raise RuntimeError(f"duree audio illisible : {r.stdout!r} / {r.stderr[-200:]}") from e


def _lancer_ffmpeg(commande: list[str]) -> None:
    r = subprocess.run(commande, capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg : {r.stderr[-300:]}")


def _video_avec_zoom(image: str, audio: str, video: str, duree: float) -> None:
    # Effet de zoom lent (Ken Burns) sur l'image fixe, calee sur la duree de
    # l'audio : sans ca, une photo immobile pendant plusieurs secondes ne
    # ressemble a rien.
    #
    # Piege trouve le 15 sept. : `zoompan=...:d=1` combine a `-shortest`
    # avec une image en boucle (`-loop 1`) ne bouge PAS a l'oeil -- zoompan
    # a besoin de connaitre le nombre TOTAL de frames a produire (`d=`) et
    # d'un `fps` fixe dans le filtre lui-meme, pas seulement en sortie
    # (`-r`). Sans ca il regenere la meme frame de zoom a chaque appel.
    # Corrige : duree lue sur l'audio (ffprobe), d = duree * fps, `-t`
    # explicite au lieu de `-shortest`. Un `scale` plus grand avant le
    # zoom evite le flou d'agrandissement.
    fps = 25
    frames = max(int(duree * fps), fps)
    filtre = (
        f"scale=2048:3072,"
        f"zoompan=z='min(zoom+0.0012,1.3)':d={frames}:s=1024x1536:fps={fps},"
        f"format=yuv420p"
    )
    _lancer_ffmpeg([
        "ffmpeg", "-y", "-loop", "1", "-i", image, "-i", audio,
        "-vf", filtre, "-c:v", "libx264", "-c:a", "aac",
        "-t", f"{duree:.2f}", "-movflags", "+faststart",
        video,
    ])


def _video_statique(image: str, audio: str, video: str, duree: float) -> None:
    """Repli si le zoom echoue (image atypique, ffmpeg trop vieux...) :
    photo fixe + voix, sans animation. Moins bien, mais rend quand meme
    une video plutot que rien."""
    _lancer_ffmpeg([
        "ffmpeg", "-y", "-loop", "1", "-i", image, "-i", audio,
        "-vf", "scale=1024:1536,format=yuv420p",
        "-c:v", "libx264", "-c:a", "aac", "-t", f"{duree:.2f}",
        "-movflags", "+faststart", video,
    ])


def _assembler_video(image: str, audio: str, video: str) -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg n'est pas installe (sudo apt install ffmpeg)")
    duree = _duree_audio(audio)
    derniere: RuntimeError | None = None
    for nom, fournisseur in (("zoom", _video_avec_zoom), ("statique", _video_statique)):
        try:
            fournisseur(image, audio, video, duree)
            return
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            derniere = RuntimeError(f"{nom} : {e}")
            logger.warning("assemblage video '%s' echoue (%s) -- on essaie "
                           "le suivant si un autre est configure.", nom, e)
    raise derniere or RuntimeError("aucun assemblage video n'a reussi")


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
