"""Aimant à audience : le guide de style, et le media kit pour les marques.

Le guide est gratuit et sert un objectif précis — construire la liste et
l'habitude d'achat *avant* l'ouverture du site de vêtements. Rien n'est
vendu ici, et rien ne concerne le système de trading.
"""
from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from eve.config import settings
from eve.content import library as lib
from eve.persona.persona import Persona

# La garde-robe de trente pièces : la trame du guide.
GARDE_ROBE = [
    ("Hauts", 9, ["3 t-shirts en coton dense (blanc, noir, gris)",
                  "2 chemises (une blanche, une rayée)",
                  "2 pulls fins (laine mérinos ou cachemire deux fils)",
                  "1 col roulé noir",
                  "1 débardeur en soie ou modal"]),
    ("Bas", 6, ["1 jean brut coupe droite", "1 jean noir",
                "2 pantalons tailleur (camel, noir)",
                "1 jupe midi", "1 short en lin (l'été)"]),
    ("Robes", 3, ["1 robe noire simple", "1 robe midi imprimée discrète",
                  "1 robe longue en lin"]),
    ("Vestes", 4, ["1 blazer bien coupé", "1 trench",
                   "1 veste en jean", "1 manteau en laine"]),
    ("Chaussures", 5, ["1 paire de baskets blanches minimalistes",
                       "1 paire de mules ou escarpins bas",
                       "1 paire de bottines en cuir",
                       "1 paire de sandales en cuir",
                       "1 paire de mocassins"]),
    ("Sacs", 3, ["1 cabas structuré pour le jour",
                 "1 petit sac bandoulière", "1 pochette pour le soir"]),
]

REGLES_ACHAT = [
    ("Regarde l'envers avant l'endroit",
     "Coutures droites et denses, doublure propre, finitions nettes. C'est là que se voit le prix réel."),
    ("Froisse le tissu dans la main",
     "S'il garde le pli trois secondes après ouverture, il le gardera sur toi toute la journée."),
    ("Lis la composition, pas l'étiquette de marque",
     "Au-delà de trente pour cent de polyester dans une maille, la pièce boulochera en une saison."),
    ("Vérifie l'entretien",
     "« Nettoyage à sec uniquement » est un coût récurrent que personne ne calcule à l'achat."),
    ("Trois couleurs, pas plus",
     "Une palette restreinte multiplie les combinaisons et divise les achats."),
    ("Compte le coût par port",
     "Une pièce à 300 € portée cent fois coûte 3 €. Une pièce à 40 € portée deux fois en coûte 20."),
    ("Achète en fin de saison",
     "Les pièces intemporelles ne se démodent pas entre deux soldes."),
    ("Fais retoucher",
     "Vingt euros de retouche transforment une pièce correcte en pièce qui semble faite pour toi."),
]


def build_guide_markdown(persona: Persona, title: str = "La garde-robe de 30 pièces") -> str:
    ident = persona.raw()["identity"]
    parts = [
        f"# {title}",
        f"### par {ident['full_name']} — {ident['city']}",
        "",
        f"> {persona.disclosure['caption_tag']}. "
        f"{ident['full_name']} est un personnage créé par intelligence artificielle.",
        "",
        "Trente pièces couvrent une année entière si elles sont choisies pour aller",
        "ensemble. Ce guide donne la liste, les règles d'achat, et l'ordre dans lequel",
        "constituer la garde-robe sans tout acheter d'un coup.",
        "",
        "## La liste",
        "",
    ]
    total = 0
    for categorie, nombre, pieces in GARDE_ROBE:
        total += nombre
        parts.append(f"### {categorie} — {nombre} pièces")
        parts += [f"- {piece}" for piece in pieces]
        parts.append("")
    parts += [f"**Total : {total} pièces.** Deux ou trois de plus ne changent rien ; "
              "quinze de plus changent tout.", "",
              "## Les huit règles d'achat", ""]
    for i, (regle, explication) in enumerate(REGLES_ACHAT, start=1):
        parts.append(f"**{i}. {regle}** — {explication}")
        parts.append("")

    parts += ["## Dans quel ordre construire", "",
              "| Mois | Priorité | Pourquoi |",
              "|---|---|---|",
              "| 1 | Chaussures et manteau | Ce qu'on porte tous les jours, et ce qui se voit le plus |",
              "| 2 | Bas (jeans, pantalons) | La base de toutes les tenues |",
              "| 3 | Hauts neutres | Ils s'associent à tout ce qui précède |",
              "| 4 | Blazer et pièces d'assemblage | Ils transforment l'existant |",
              "| 5 | Sacs et accessoires | En dernier : ils ne dépannent jamais |",
              "",
              "## À retenir", ""]
    for topic, reponse, _ in lib.FASHION_TOPICS[:4]:
        parts.append(f"**{topic}** — {reponse}")
        parts.append("")
    return "\n".join(parts)


def markdown_to_html(md: str, title: str) -> str:
    """Rendu HTML minimal et imprimable — pas de dépendance markdown."""
    out: list[str] = []
    in_table = False
    for raw in md.splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            cells = [html.escape(c.strip()) for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False

        esc = html.escape(line)
        esc = _inline(esc)
        if line.startswith("#### "):
            out.append(f"<h4>{_inline(html.escape(line[5:]))}</h4>")
        elif line.startswith("### "):
            out.append(f"<h3>{_inline(html.escape(line[4:]))}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{_inline(html.escape(line[3:]))}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{_inline(html.escape(line[2:]))}</h1>")
        elif line.startswith("> "):
            out.append(f"<blockquote>{_inline(html.escape(line[2:]))}</blockquote>")
        elif line.startswith("- "):
            out.append(f"<li>{_inline(html.escape(line[2:]))}</li>")
        elif not line:
            out.append("")
        else:
            out.append(f"<p>{esc}</p>")

    if in_table:
        out.append("</table>")

    body = "\n".join(out).replace("<li>", "<ul><li>").replace("</li>", "</li></ul>")
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,sans-serif;max-width:760px;
      margin:40px auto;padding:0 24px;line-height:1.55;color:#1a1a1a}}
 h1{{font-size:2.2rem;margin-bottom:0}} h2{{margin-top:2.2rem;border-bottom:2px solid #e8e8e8;padding-bottom:6px}}
 h3{{color:#555;font-weight:500;margin-top:4px}} h4{{margin-bottom:4px}}
 blockquote{{background:#f5f7f9;border-left:4px solid #7bb;padding:10px 16px;margin:16px 0}}
 table{{border-collapse:collapse;width:100%;margin:16px 0}} td,th{{border:1px solid #ddd;padding:8px}}
 ul{{margin:4px 0}} em{{color:#666}}
 @media print{{body{{margin:0}} h2{{page-break-after:avoid}}}}
</style></head><body>{body}</body></html>"""


def _inline(text: str) -> str:
    """Gras, italique et retour à la ligne markdown → HTML."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![\w])_(.+?)_(?![\w])", r"<em>\1</em>", text)
    return text.replace("  \n", "<br>")


def export_guide(persona: Persona, out_dir: Path | None = None,
                 title: str = "La garde-robe de 30 pièces") -> dict[str, Path]:
    out_dir = out_dir or settings.paths.products
    out_dir.mkdir(parents=True, exist_ok=True)
    md = build_guide_markdown(persona, title)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    md_path = out_dir / f"{slug}.md"
    html_path = out_dir / f"{slug}.html"
    md_path.write_text(md, encoding="utf-8")
    html_path.write_text(markdown_to_html(md, title), encoding="utf-8")
    return {"markdown": md_path, "html": html_path}


def build_media_kit(persona: Persona, stats: dict, out_dir: Path | None = None) -> Path:
    """Dossier de presse pour démarcher les marques (transparence IA incluse)."""
    out_dir = out_dir or settings.paths.products
    out_dir.mkdir(parents=True, exist_ok=True)
    ident = persona.raw()["identity"]
    m = settings.monetization

    md = f"""# Media kit — {ident['full_name']} (@{ident['handle']})

**Créatrice virtuelle générée par IA** · {ident['city']}, {ident['state']} · lifestyle & style

> Transparence : {ident['full_name']} est un personnage créé par intelligence artificielle.
> Chaque publication porte la mention IA exigée par les plateformes et la FTC.

## Positionnement
{persona.raw()['expertise']['positioning']}

**Audience visée** : {persona.raw()['audience']['primary']}

## Chiffres (au {date.today().isoformat()})
| Indicateur | Instagram | TikTok |
|---|---|---|
| Abonnés | {stats.get('instagram_followers', '—')} | {stats.get('tiktok_followers', '—')} |
| Vues 30 j | {stats.get('instagram_views_30d', '—')} | {stats.get('tiktok_views_30d', '—')} |
| Taux d'engagement | {stats.get('instagram_engagement', '—')} | {stats.get('tiktok_engagement', '—')} |

## Formats proposés
- Vidéo intégrée (30-60 s) : le produit dans une tenue ou une routine réelle.
- Série de 3 vidéos sur une semaine, avec lien suivi.
- Story ou carrousel pédagogique : matière, coupe, entretien.

## Ce que je ne fais pas
- Aucun produit financier, aucune promesse de gain, aucun parrainage de plateforme.
- Aucune contrefaçon, aucun revendeur non autorisé.
- Aucun partenariat sans mention #ad visible.
- Aucune affirmation que mon train de vie provient d'un revenu quelconque :
  le personnage est généré par IA et n'en a aucun.

## Contact
{m.business_email or 'à renseigner (BUSINESS_EMAIL)'}
"""
    path = out_dir / "media-kit.md"
    path.write_text(md, encoding="utf-8")
    (out_dir / "media-kit.html").write_text(
        markdown_to_html(md, f"Media kit — {ident['full_name']}"), encoding="utf-8")
    return path
