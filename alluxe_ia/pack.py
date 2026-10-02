"""Le kit du constructeur de alluxe.ia : les prompts des posts, en PDF.

C'est ce que recoit quelqu'un qui commente KIT (sequence ManyChat) et ce
qui se telecharge depuis le lien de la bio. Les prompts sont TIRES de
alluxe_ia/posts.json (posts listes dans THEMES) : un prompt corrige dans
un post est corrige dans le kit au prochain rendu, il n'y a pas deux
copies a tenir a jour.

    python3 -m alluxe_ia.pack            ->  data/alluxe_ia/kit-constructeur.pdf

Necessite fpdf2 (pip install fpdf2), seulement pour produire le PDF.
"""
from __future__ import annotations

import json
import os

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
POLICES = os.path.join(ICI, "polices")

# Theme affiche au-dessus de chaque prompt, par post. Un post absent
# d'ici n'entre pas dans le kit.
THEMES = {
    "02-le-labo": "Le labo", "03-108-rejetees": "Déboguer",
    "04-cahier-des-charges": "Démarrer un projet", "05-publication-auto": "Automatiser",
    "06-fichier-decisions": "Mémoire de l'IA", "07-tests-verts": "Vérifier",
    "08-agent-garde-fous": "Sécurité", "09-methode-4-cases": "Méthode",
    "11-assistant-perso": "Assistant perso",
}

# Memes couleurs que les slides (alluxe_ia/slides.py).
FOND = (14, 21, 19)
ENCRE_CLAIRE = (234, 241, 237)
MENTHE = (92, 195, 180)
MENTHE_FONCE = (14, 107, 98)
AMBRE = (227, 162, 74)
ENCRE = (22, 32, 28)
DOUX = (90, 104, 98)
CADRE = (238, 243, 240)


def prompts_choisis() -> list[tuple[str, str, str]]:
    """(thème, titre, prompt) de chaque slide prompt des posts de THEMES,
    dans l'ordre de posts.json."""
    with open(os.path.join(ICI, "posts.json"), encoding="utf-8") as f:
        posts = json.load(f)
    sortie = []
    for post in posts:
        if post["id"] not in THEMES:
            continue
        for slide in post["slides"]:
            if slide["type"] != "prompt":
                continue
            titre = slide["titre"]
            propre = titre.split(". ", 1)[-1] if titre[:2].rstrip(".").isdigit() else titre
            sortie.append((THEMES[post["id"]], propre, slide["prompt"]))
    return sortie


def construire(chemin: str) -> str:
    from fpdf import FPDF

    class _PDF(FPDF):
        # fpdf2 justifie par defaut : sur du texte court ou un prompt, ca
        # ouvre des trous entre les mots. Tout est aligne a gauche.
        def multi_cell(self, *args, **kwargs):
            kwargs.setdefault("align", "L")
            return super().multi_cell(*args, **kwargs)

    pdf = _PDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_font("titre", "", os.path.join(POLICES, "BricolageGrotesque.ttf"))
    pdf.add_font("texte", "", os.path.join(POLICES, "AtkinsonHyperlegible-Regular.ttf"))
    pdf.add_font("texte", "B", os.path.join(POLICES, "AtkinsonHyperlegible-Bold.ttf"))
    pdf.add_font("mono", "", os.path.join(POLICES, "JetBrainsMono.ttf"))
    prompts = prompts_choisis()
    pdf.set_title(f"alluxe.ia — le kit du constructeur ({len(prompts)} prompts)")
    pdf.set_author("alluxe.ia")

    # Couverture, sombre comme les slides.
    pdf.add_page()
    pdf.set_fill_color(*FOND)
    pdf.rect(0, 0, 210, 297, "F")
    pdf.set_fill_color(*MENTHE)
    pdf.ellipse(20, 22, 18, 18, "F")
    pdf.set_font("titre", size=15)
    pdf.set_text_color(*FOND)
    pdf.set_xy(20, 26)
    pdf.cell(18, 10, "a.", align="C")
    pdf.set_text_color(*ENCRE_CLAIRE)
    pdf.set_xy(42, 25)
    pdf.cell(0, 8, "alluxe.ia")
    pdf.set_font("titre", size=40)
    pdf.set_xy(20, 95)
    pdf.multi_cell(170, 17, "Le kit du constructeur.")
    pdf.set_font("texte", size=14)
    pdf.set_text_color(160, 178, 170)
    pdf.set_x(20)
    pdf.multi_cell(170, 7.5, f"Les {len(prompts)} prompts que j'utilise vraiment pour construire "
                   "avec Claude et ChatGPT sans être développeur, dans l'ordre "
                   "où je m'en sers. Copie, remplace les crochets, colle.")
    pdf.set_font("texte", "B", size=12)
    pdf.set_text_color(*MENTHE)
    pdf.set_xy(20, 265)
    pdf.cell(0, 8, "@alluxe.ia sur Instagram")

    # Mode d'emploi.
    pdf.add_page()
    pdf.set_text_color(*ENCRE)
    pdf.set_font("titre", size=24)
    pdf.set_x(20)
    pdf.cell(0, 14, "Comment s'en servir", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    regles = [
        ("Remplace les crochets.", "Tout ce qui est entre [crochets] est à "
         "remplacer par ta situation. Plus tu donnes de détails, meilleure est la réponse."),
        ("Ne t'arrête pas à la première réponse.", "Réponds « plus court », « plus "
         "concret », « avec un exemple ». La troisième version est souvent la bonne."),
        ("Ajoute cette phrase à la fin.", "« Avant de répondre, pose-moi les "
         "questions qui te manquent. » L'IA arrête d'inventer."),
        ("Ne colle jamais de données sensibles.", "Mots de passe, IBAN, numéros "
         "de sécurité sociale, données de tes clients : retire-les avant."),
        ("Vérifie ce qui compte.", "L'IA peut se tromper avec assurance sur un "
         "chiffre, une date ou une règle. Pour l'administratif, la santé ou "
         "l'argent, vérifie à la source."),
    ]
    for titre, texte in regles:
        pdf.set_x(20)
        pdf.set_font("texte", "B", size=12)
        pdf.set_text_color(*MENTHE_FONCE)
        pdf.multi_cell(170, 6.5, titre)
        pdf.set_x(20)
        pdf.set_font("texte", size=11.5)
        pdf.set_text_color(*ENCRE)
        pdf.multi_cell(170, 6.2, texte)
        pdf.ln(4)

    # Les 20 prompts : chaque bloc reste entier sur sa page.
    pdf.add_page()
    for i, (theme, titre, prompt) in enumerate(prompts, start=1):
        pdf.set_font("mono", size=9.5)
        lignes = pdf.multi_cell(158, 5.2, prompt, dry_run=True, output="LINES")
        hauteur_bloc = 22 + len(lignes) * 5.2 + 12
        if pdf.get_y() + hauteur_bloc > 297 - 18:
            pdf.add_page()
        pdf.set_x(20)
        pdf.set_font("mono", size=9)
        pdf.set_text_color(*MENTHE_FONCE)
        pdf.cell(0, 5, f"{i:02d} · {theme.upper()}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(20)
        pdf.set_font("titre", size=15)
        pdf.set_text_color(*ENCRE)
        pdf.cell(0, 9, titre, new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y() + 1
        h = len(lignes) * 5.2 + 8
        pdf.set_fill_color(*CADRE)
        pdf.rect(20, y, 170, h, "F")
        pdf.set_xy(26, y + 4)
        pdf.set_font("mono", size=9.5)
        pdf.multi_cell(158, 5.2, prompt)
        pdf.set_y(y + h + 8)

    # Fin.
    pdf.add_page()
    pdf.set_text_color(*ENCRE)
    pdf.set_font("titre", size=24)
    pdf.set_x(20)
    pdf.multi_cell(170, 12, "La suite sur @alluxe.ia")
    pdf.set_font("texte", size=12)
    pdf.set_x(20)
    pdf.multi_cell(170, 6.5, "Chaque semaine : les coulisses d'un système réel construit "
                   "avec l'IA, ce qui a cassé, et comment le refaire chez toi.")
    pdf.ln(6)
    pdf.set_font("texte", size=10)
    pdf.set_text_color(*DOUX)
    pdf.set_x(20)
    pdf.multi_cell(170, 5.5, "Ce kit est gratuit et ne contient aucun lien "
                   "sponsorisé. Les réponses de l'IA sont à vérifier : ce document "
                   "ne remplace pas un conseil juridique, médical ou financier.")

    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    pdf.output(chemin)
    return chemin


if __name__ == "__main__":
    print(construire(os.path.join(RACINE, "data", "alluxe_ia", "kit-constructeur.pdf")))
