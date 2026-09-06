"""Kit de lancement de compte : tout ce qu'il faut pour créer les profils.

Sert le premier vrai geste de l'utilisateur — créer les comptes et publier à
la main. La bio, la photo de profil et la liste de contrôle sortent du
character bible, donc restent cohérentes avec le contenu produit.
"""
from __future__ import annotations

from pathlib import Path

from eve.config import settings
from eve.media.images import generate_image
from eve.monetization.products import markdown_to_html
from eve.persona.persona import Persona

# Instagram tolère 150 caractères de bio, TikTok 80.
IG_BIO_LIMIT = 150
TIKTOK_BIO_LIMIT = 80


# La mention IA doit tenir dans la bio ; TikTok est trop court pour la forme
# longue, d'où une variante compacte qui dit la même chose.
DISCLOSURE_COURTE = "🤖 IA · créatrice virtuelle"


def build_bios(persona: Persona) -> dict[str, str]:
    """Bios prêtes à coller, tenant dans les limites de chaque plateforme.

    La mention IA occupe toujours la première ligne ; les lignes suivantes
    sont ajoutées par ordre d'importance tant que la place le permet.
    L'URL n'est pas comptée : les deux plateformes ont un champ séparé.
    """
    ident = persona.raw()["identity"]
    longue = persona.disclosure["bio_line"]

    instagram = _assembler(longue, [
        "Style, art de vivre et coulisses d'un métier technique",
        f"{ident['city']}, FL 🌴",
        "↓ Le guide garde-robe, gratuit",
    ], IG_BIO_LIMIT)

    tiktok = _assembler(DISCLOSURE_COURTE, [
        "Style & art de vivre · Miami 🌴",
        "Créatrice virtuelle",
    ], TIKTOK_BIO_LIMIT)

    return {"instagram": instagram, "tiktok": tiktok}


def _assembler(entete: str, lignes: list[str], limite: int) -> str:
    """En-tête obligatoire, puis autant de lignes que la limite l'autorise."""
    retenues = [entete]
    total = len(entete)
    for ligne in lignes:
        if total + len(ligne) + 1 > limite:
            continue
        retenues.append(ligne)
        total += len(ligne) + 1
    return "\n".join(retenues)


def profile_picture(persona: Persona, out_dir: Path | None = None) -> Path:
    """Portrait carré : la photo de profil des deux comptes."""
    out_dir = out_dir or settings.paths.products
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = persona.image_prompt(
        "smiling warmly at the camera, head and shoulders portrait, "
        "relaxed and approachable, soft natural light",
        outfit="a fine cream knit sweater with a delicate gold necklace",
        location="a bright room with a softly blurred neutral background",
    )
    return generate_image(prompt, out_dir / "photo-de-profil.png",
                          seed=persona.seed, width=1080, height=1080).path


def build_launch_kit(persona: Persona, out_dir: Path | None = None) -> dict[str, Path]:
    out_dir = out_dir or settings.paths.products
    out_dir.mkdir(parents=True, exist_ok=True)
    ident = persona.raw()["identity"]
    bios = build_bios(persona)
    photo = profile_picture(persona, out_dir)

    md = f"""# Kit de lancement — {ident['full_name']}

## 1. Noms de compte

Pseudo souhaité : **@{ident['handle']}**
Nom affiché : **{ident['display_name']}**

Si le pseudo est pris, garde la même racine : `{ident['handle']}.official`,
`{ident['handle']}fit`, `coach.{ident['handle']}`. Le même pseudo sur les deux
plateformes vaut mieux qu'un pseudo parfait sur une seule.

## 2. Photo de profil

`{photo.name}` — générée avec le même visage que les vidéos. Recadre en cercle,
le visage doit rester lisible en tout petit.

## 3. Bios à copier-coller

### Instagram ({len(bios['instagram'])} / {IG_BIO_LIMIT} caractères)

```
{bios['instagram']}
```

### TikTok ({len(bios['tiktok'])} / {TIKTOK_BIO_LIMIT} caractères)

```
{bios['tiktok']}
```

**Champ « site web » / « lien »**, à part de la bio :
`{settings.monetization.linkinbio_url or 'à créer — Beacons, Linktree ou Stan Store, gratuits'}`

La première ligne — la mention IA — n'est pas négociable : c'est une
obligation légale et une règle des deux plateformes.

## 4. Réglages de compte, une fois pour toutes

- [ ] Instagram passé en compte **Professionnel** (Créateur)
- [ ] Label IA activé sur les deux comptes
- [ ] Même photo de profil et même pseudo des deux côtés
- [ ] Lien en bio configuré (Beacons, Linktree ou Stan Store — tous gratuits)
- [ ] Adresse e-mail dédiée pour les marques

## 5. Les 7 premiers jours

Publie **une vidéo par jour, à heure fixe**. Prends les MP4 dans
`output/videos/`, la légende est dans le fichier `legendes.txt` posé à côté de
chacun.

Ne change rien avant 7 jours : sans données, toute modification est une
supposition. Au bout d'une semaine, regarde quelle vidéo a le plus de vues et
fais-en trois variantes.

## 6. Ce qui compte vraiment la première semaine

1. **Publier tous les jours** — la régularité prime sur la qualité au départ.
2. **Répondre à tous les commentaires** — c'est manuel, c'est le plus rentable.
3. **Regarder le taux de rétention à 3 secondes** — s'il est bas, le problème
   est le hook, pas la vidéo.
"""
    md_path = out_dir / "kit-lancement.md"
    md_path.write_text(md, encoding="utf-8")
    html_path = out_dir / "kit-lancement.html"
    html_path.write_text(markdown_to_html(md, f"Kit de lancement — {ident['full_name']}"),
                         encoding="utf-8")
    return {"markdown": md_path, "html": html_path, "photo": photo}
