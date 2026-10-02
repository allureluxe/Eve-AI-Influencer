"""Le pack gratuit de alluxe.ia : 20 prompts en PDF, texte selectionnable.

C'est ce que recoit quelqu'un qui commente PROMPTS (sequence ManyChat) et
ce qui se telecharge depuis le lien de la bio. Les prompts sont TIRES de
alluxe_ia/posts.json, dans l'ordre de CHOIX ci-dessous : un prompt
corrige dans un post est corrige dans le pack au prochain rendu, il n'y a
pas deux copies a tenir a jour.

    python3 -m alluxe_ia.pack            ->  data/alluxe_ia/pack-gratuit.pdf

Necessite fpdf2 (pip install fpdf2), seulement pour produire le PDF.
"""
from __future__ import annotations

import json
import os

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
POLICES = os.path.join(ICI, "polices")

# (identifiant du post, titre de la slide prompt) -- 20 prompts.
CHOIX = [
    ("01-cv-lettre", "1. Le CV taillé pour l'offre"),
    ("01-cv-lettre", "2. Les mots-clés des logiciels de tri"),
    ("01-cv-lettre", "3. La lettre qu'on lit jusqu'au bout"),
    ("01-cv-lettre", "4. L'entretien répété"),
    ("01-cv-lettre", "5. La question piège du salaire"),
    ("02-photo-pro", "Le prompt"),
    ("03-mails", "Relancer sans être lourd"),
    ("03-mails", "Dire non sans fâcher"),
    ("03-mails", "Réclamer et obtenir gain de cause"),
    ("04-apprendre", "1. Le plan d'apprentissage"),
    ("04-apprendre", "2. L'explication qui fait tilt"),
    ("04-apprendre", "3. Le prof qui interroge"),
    ("04-apprendre", "4. La fiche de révision"),
    ("05-budget", "1. Le grand tri"),
    ("05-budget", "2. Les fuites"),
    ("06-administratif", "Comprendre un courrier officiel"),
    ("06-administratif", "Contester une décision"),
    ("07-repas-semaine", "Le menu de la semaine"),
    ("08-bien-acheter", "2. Comparer sans se faire avoir"),
    ("09-methode-4-cases", "Les 4 cases ensemble"),
]

THEMES = {
    "01-cv-lettre": "Candidature", "02-photo-pro": "Photo pro", "03-mails": "Mails",
    "04-apprendre": "Apprendre", "05-budget": "Budget", "06-administratif": "Administratif",
    "07-repas-semaine": "Repas", "08-bien-acheter": "Achats", "09-methode-4-cases": "Méthode",
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
    """(thème, titre, prompt) pour chaque entrée de CHOIX, dans l'ordre."""
    with open(os.path.join(ICI, "posts.json"), encoding="utf-8") as f:
        posts = {p["id"]: p for p in json.load(f)}
    sortie = []
    for pid, titre in CHOIX:
        slide = next(s for s in posts[pid]["slides"]
                     if s["type"] == "prompt" and s["titre"] == titre)
        propre = titre.split(". ", 1)[-1] if titre[:2].rstrip(".").isdigit() else titre
        if propre == "Le prompt":
            propre = "La photo de profil pro"
        sortie.append((THEMES[pid], propre, slide["prompt"]))
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
    pdf.set_title("alluxe.ia — 20 prompts qui font le travail à ta place")
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
    pdf.multi_cell(170, 17, "20 prompts qui font le travail à ta place.")
    pdf.set_font("texte", size=14)
    pdf.set_text_color(160, 178, 170)
    pdf.set_x(20)
    pdf.multi_cell(170, 7.5, "Candidature, mails, apprentissage, budget, paperasse, "
                   "repas, achats. Copie, remplace les crochets, colle dans "
                   "ChatGPT, Claude ou Gemini.")
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
    for i, (theme, titre, prompt) in enumerate(prompts_choisis(), start=1):
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
    pdf.multi_cell(170, 6.5, "Un nouveau pack de prompts chaque semaine, des "
                   "méthodes et les coulisses de projets construits avec l'IA. "
                   "Commente le mot-clé sous un post pour recevoir la version complète.")
    pdf.ln(6)
    pdf.set_font("texte", size=10)
    pdf.set_text_color(*DOUX)
    pdf.set_x(20)
    pdf.multi_cell(170, 5.5, "Ce pack est gratuit et ne contient aucun lien "
                   "sponsorisé. Les réponses de l'IA sont à vérifier : ce document "
                   "ne remplace pas un conseil juridique, médical ou financier.")

    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    pdf.output(chemin)
    return chemin


if __name__ == "__main__":
    print(construire(os.path.join(RACINE, "data", "alluxe_ia", "pack-gratuit.pdf")))
