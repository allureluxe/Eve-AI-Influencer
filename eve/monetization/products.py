"""Produits numériques : le premier revenu qui ne dépend d'aucune plateforme.

Génère un programme 4 semaines (Markdown + HTML imprimable en PDF) et un
media kit pour démarcher les marques. Zéro dépendance externe : le HTML
s'imprime en PDF depuis n'importe quel navigateur.
"""
from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

from eve.config import settings
from eve.content import library as lib
from eve.persona.persona import Persona

# Progression classique : volume croissant sur 3 semaines, décharge en S4.
WEEK_PLAN = [
    ("Semaine 1 — Prise de repères", ["full_body_10", "core_5", "glutes_15"],
     "Objectif : trois rendez-vous tenus. La charge n'a aucune importance cette semaine."),
    ("Semaine 2 — On ajoute une série", ["full_body_10", "gym_upper", "glutes_15", "core_5"],
     "Même mouvements, une série de plus. On note les répétitions."),
    ("Semaine 3 — Point haut", ["gym_upper", "gym_lower", "full_body_10", "core_5"],
     "La semaine la plus chargée. Si une séance saute, ce n'est pas grave : on ne saute jamais deux fois."),
    ("Semaine 4 — Décharge et bilan", ["full_body_10", "glutes_15", "core_5"],
     "Volume réduit de moitié. On compare les répétitions de la semaine 1."),
]


def _workout_markdown(key: str) -> str:
    wo = lib.WORKOUTS_BY_KEY[key]
    lines = [f"#### {wo.title_fr} · {wo.duration_min} min · matériel : {wo.equipment}"]
    for exo_key, fmt in wo.blocks:
        exo = lib.EXERCISES_BY_KEY[exo_key]
        cue = exo.cues[0] if exo.cues else ""
        lines.append(f"- **{exo.name_fr}** — {fmt} · _{cue}_")
    return "\n".join(lines)


def build_program_markdown(persona: Persona, title: str = "Reset 4 semaines") -> str:
    parts = [
        f"# {title}",
        f"### par {persona.raw()['identity']['full_name']} — coach virtuelle, {persona.raw()['identity']['city']}",
        "",
        f"> {persona.disclosure['caption_tag']}. "
        f"{persona.raw()['identity']['full_name']} est un personnage généré par intelligence artificielle.",
        "",
        f"**Avertissement.** {persona.disclaimer}",
        "",
        "## Comment utiliser ce programme",
        "- 3 à 4 séances par semaine, jamais deux jours de repos consécutifs.",
        "- On note les répétitions à chaque séance : c'est la seule mesure de progrès qui compte.",
        "- Échauffement : 5 minutes de marche rapide + 10 squats à vide avant chaque séance.",
        "- Une douleur articulaire arrête la série. Une courbature, non.",
        "",
    ]
    for week_title, workouts, note in WEEK_PLAN:
        parts += [f"## {week_title}", f"_{note}_", ""]
        parts += [_workout_markdown(k) for k in workouts]
        parts.append("")

    parts += ["## Fiche technique — les points à ne pas rater", ""]
    for exo in lib.EXERCISES:
        parts.append(f"**{exo.name_fr}** ({exo.target}) — "
                     + " ; ".join(exo.cues[:2])
                     + f". Erreur fréquente : {exo.mistakes[0]}.")
    parts += ["", "## Suivi", "",
              "| Semaine | Séances faites | Sensation (1-5) | Note |",
              "|---|---|---|---|"]
    parts += [f"| {i} |  |  |  |" for i in range(1, 5)]
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


def export_program(persona: Persona, out_dir: Path | None = None,
                   title: str = "Reset 4 semaines") -> dict[str, Path]:
    out_dir = out_dir or settings.paths.products
    out_dir.mkdir(parents=True, exist_ok=True)
    md = build_program_markdown(persona, title)
    slug = title.lower().replace(" ", "-")
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

**Créatrice virtuelle générée par IA** · {ident['city']}, {ident['state']} · coach sportive

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
- Vidéo intégrée (30-60 s) dans une séance ou une démonstration technique.
- Série de 3 vidéos sur une semaine, avec code promo suivi.
- Story / carrousel pédagogique avec le produit en usage réel.

## Ce que je ne fais pas
- Aucune allégation santé, aucune promesse de perte de poids chiffrée.
- Aucun complément alimentaire non certifié.
- Aucun partenariat sans mention #ad visible.

## Contact
{m.business_email or 'à renseigner (BUSINESS_EMAIL)'}
"""
    path = out_dir / "media-kit.md"
    path.write_text(md, encoding="utf-8")
    (out_dir / "media-kit.html").write_text(
        markdown_to_html(md, f"Media kit — {ident['full_name']}"), encoding="utf-8")
    return path
