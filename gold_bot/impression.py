"""Imprimer un rapport sur une imprimante de la maison, depuis le VPS.

LE PROBLEME, ET POURQUOI IL N'EST PAS EVIDENT
---------------------------------------------
Le robot tourne sur un serveur chez OVH. L'imprimante est sur le wifi
de la maison, derriere une box. Les deux ne sont PAS sur le meme
reseau : le serveur ne peut ni voir l'imprimante, ni s'y connecter.
Aucun protocole d'impression classique (IPP, AirPrint, partage
Windows) ne traverse ca sans ouvrir un port ou monter un tunnel — et
ouvrir un port vers une imprimante depuis Internet est une mauvaise
idee qu'on ne fera pas.

LA SEULE VOIE PROPRE : L'IMPRESSION PAR COURRIEL.
Certaines imprimantes recoivent leur propre adresse e-mail chez le
fabricant. On leur envoie un PDF en piece jointe, elles l'impriment.
C'est le fabricant qui traverse la box, pas nous.

    Epson  — « Epson Email Print » (Epson Connect). Fonctionne.
    HP     — « HP ePrint ». SERVICE FERME depuis janvier 2023.
             Une imprimante HP recente ne sait plus faire ca.
    Brother, Canon — selon les modeles, verifier avant d'acheter.

C'est donc un critere d'ACHAT, pas un reglage : une imprimante « wifi »
ordinaire ne suffira pas.

CE QUE FAIT CE MODULE
---------------------
1. Convertit la page HTML du rapport en PDF (Chromium sans interface).
2. Envoie ce PDF par courriel a l'adresse de l'imprimante.

Sans configuration, il ne fait rien et le dit. Le rapport Telegram,
lui, part comme avant : l'impression est un supplement, jamais une
condition.
"""

from __future__ import annotations

import logging
import os
import smtplib
import subprocess
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

#: Ou deposer les PDF. DANS LE DOSSIER PERSONNEL, et c'est necessaire :
#: le Chromium installe par snap est confine et refuse d'ecrire dans
#: /tmp. L'erreur qu'il rend alors est « No such file or directory »,
#: ce qui envoie chercher au mauvais endroit pendant un moment.
DOSSIER = Path.home() / "Eve-AI-Influencer" / "data" / "impressions"

#: Au-dela, on abandonne : Chromium reste parfois bloque sur une page
#: qui attend une ressource distante.
DELAI_PDF = 120


class ImpressionIndisponible(Exception):
    """Rien n'est configure, ou une etape a echoue. Jamais fatale."""


def _chromium() -> Optional[str]:
    for nom in ("chromium-browser", "chromium", "google-chrome",
                "google-chrome-stable"):
        chemin = subprocess.run(["which", nom], capture_output=True,
                                text=True).stdout.strip()
        if chemin:
            return chemin
    return None


def vers_pdf(html: Path, sortie: Optional[Path] = None) -> Path:
    """Convertit la page du rapport en PDF.

    Chromium plutot qu'une bibliotheque Python : la page ALLURE dessine
    sa courbe en JavaScript. Un convertisseur qui n'execute pas le
    script rendrait une page avec un cadre vide a la place du
    graphique — exactement le defaut qu'on vient de corriger sur
    l'artefact du 11 septembre.
    """
    navigateur = _chromium()
    if not navigateur:
        raise ImpressionIndisponible(
            "Chromium n'est pas installe : sudo apt install chromium-browser")

    DOSSIER.mkdir(parents=True, exist_ok=True)
    sortie = sortie or DOSSIER / f"rapport-{time.strftime('%Y%m%d-%H%M%S')}.pdf"

    resultat = subprocess.run(
        [navigateur, "--headless", "--disable-gpu", "--no-sandbox",
         "--no-pdf-header-footer",
         # Le rendu attend que le JavaScript ait dessine la courbe.
         "--virtual-time-budget=5000",
         f"--print-to-pdf={sortie}", str(html)],
        capture_output=True, text=True, timeout=DELAI_PDF,
    )

    # Chromium ecrit des avertissements sans gravite sur stderr (dbus,
    # polices, GPU) meme quand tout va bien : on juge sur le FICHIER,
    # pas sur le code de retour ni sur stderr.
    if not sortie.exists() or sortie.stat().st_size < 1000:
        detail = (resultat.stderr or "")[-300:]
        raise ImpressionIndisponible(f"PDF non produit : {detail}")
    return sortie


def envoyer_a_l_imprimante(pdf: Path, sujet: str = "") -> bool:
    """Envoie le PDF par courriel a l'imprimante. Rend True si c'est parti.

    Ne leve jamais autre chose que `ImpressionIndisponible` : une
    imprimante eteinte ne doit pas empecher le rapport d'arriver sur
    Telegram.
    """
    destinataire = os.getenv("IMPRIMANTE_EMAIL", "").strip()
    if not destinataire:
        raise ImpressionIndisponible("IMPRIMANTE_EMAIL n'est pas defini")

    hote = os.getenv("SMTP_HOTE", "smtp.gmail.com").strip()
    port = int(os.getenv("SMTP_PORT", "587"))
    utilisateur = os.getenv("SMTP_UTILISATEUR", "").strip()
    motdepasse = os.getenv("SMTP_MOTDEPASSE", "").strip()
    if not (utilisateur and motdepasse):
        raise ImpressionIndisponible(
            "SMTP_UTILISATEUR et SMTP_MOTDEPASSE ne sont pas definis")

    message = EmailMessage()
    message["From"] = utilisateur
    message["To"] = destinataire
    # LE SUJET COMPTE : la plupart des services d'impression par
    # courriel l'impriment en tete de page, et certains refusent un
    # message sans sujet.
    message["Subject"] = sujet or "Rapport ALLURE"
    message.set_content(
        "Rapport genere automatiquement par le robot ALLURE.\n"
        "Le document est en piece jointe.")
    message.add_attachment(pdf.read_bytes(), maintype="application",
                           subtype="pdf", filename=pdf.name)

    try:
        with smtplib.SMTP(hote, port, timeout=30) as serveur:
            serveur.starttls()
            serveur.login(utilisateur, motdepasse)
            serveur.send_message(message)
    except Exception as exc:                                # noqa: BLE001
        raise ImpressionIndisponible(f"envoi refuse : {exc}") from exc

    log.info("rapport envoye a l'imprimante (%s)", destinataire)
    return True


def imprimer(html: Path, sujet: str = "") -> tuple[bool, str]:
    """Toute la chaine. Rend (succes, message a afficher).

    Ne leve JAMAIS. L'impression est un confort : le rapport Telegram
    doit partir meme si l'imprimante est eteinte, si le PDF echoue, ou
    si rien n'est configure.
    """
    if not os.getenv("IMPRIMANTE_EMAIL", "").strip():
        return False, ""          # pas configure : on n'en parle meme pas

    try:
        pdf = vers_pdf(Path(html))
        envoyer_a_l_imprimante(pdf, sujet)
    except ImpressionIndisponible as exc:
        log.warning("impression impossible : %s", exc)
        return False, f"Impression impossible : {exc}"
    except Exception as exc:                                # noqa: BLE001
        log.warning("impression impossible : %s", exc)
        return False, "Impression impossible (erreur inattendue)."

    return True, "Envoye a l'imprimante."


def nettoyer(jours: int = 30) -> int:
    """Efface les vieux PDF. Sans ca, le disque se remplit en silence."""
    if not DOSSIER.exists():
        return 0
    limite = time.time() - jours * 86400
    efface = 0
    for fichier in DOSSIER.glob("rapport-*.pdf"):
        try:
            if fichier.stat().st_mtime < limite:
                fichier.unlink()
                efface += 1
        except OSError:
            pass
    return efface
