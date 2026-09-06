"""Kit de lancement de compte : tout ce qu'il faut pour créer les profils.

Sert le premier vrai geste de l'utilisateur — créer les comptes et publier à
la main. La bio, la photo de profil et la liste de contrôle sortent du
character bible, donc restent cohérentes avec le contenu produit.
"""
from __future__ import annotations

from datetime import date
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
DISCLOSURE_COURTE = "🤖 Personnage virtuel généré"


def ligne_compteur(journal=None) -> str:
    """Ligne « où en est le compte », calculée depuis le journal réel.

    Chaîne vide tant qu'aucun compte n'est ouvert : une bio ne doit jamais
    afficher un chiffre inventé, même pour faire joli.
    """
    from eve.content import story

    journal = journal if journal is not None else story.load_journal()
    if journal is None or journal.solde_actuel is None:
        return ""

    ouverture = next((e for e in journal.entrees if e.a_un_solde), None)
    if ouverture is None:
        return ""
    jours = (date.fromisoformat(journal.derniere.date)
             - date.fromisoformat(ouverture.date)).days
    solde = f"{journal.solde_actuel:.2f}".replace(".", ",")
    return f"Jour {jours} : {solde} €" if jours > 0 else f"Compte ouvert : {solde} €"


def build_bios(persona: Persona) -> dict[str, str]:
    """Bios prêtes à coller, tenant dans les limites de chaque plateforme.

    La mention IA occupe toujours la première ligne ; les lignes suivantes
    sont ajoutées par ordre d'importance tant que la place le permet.
    L'URL n'est pas comptée : les deux plateformes ont un champ séparé.
    """
    ident = persona.raw()["identity"]
    longue = persona.disclosure["bio_line"]

    capital = persona.raw().get("story", {}).get("capital_depart_eur", 100)
    compteur = ligne_compteur()

    # Le compteur passe avant le reste : c'est lui qui donne envie de revenir.
    # Absent tant qu'aucun compte réel n'est ouvert.
    instagram = _assembler(longue, [
        f"J'ai codé un robot de trading. {capital:.0f} € dessus.",
        compteur,
        "Je publie tout, même les pertes",
        f"{ident['city']} ☀️",
    ], IG_BIO_LIMIT)

    tiktok = _assembler(DISCLOSURE_COURTE, [
        f"{capital:.0f} € · mon robot · {compteur}" if compteur
        else f"{capital:.0f} € · un robot que j'ai codé",
        "Les pertes aussi sont publiées",
    ], TIKTOK_BIO_LIMIT)

    return {"instagram": instagram, "tiktok": tiktok}


def _assembler(entete: str, lignes: list[str], limite: int) -> str:
    """En-tête obligatoire, puis autant de lignes que la limite l'autorise."""
    retenues = [entete]
    total = len(entete)
    for ligne in lignes:
        if not ligne or total + len(ligne) + 1 > limite:
            continue
        retenues.append(ligne)
        total += len(ligne) + 1
    return "\n".join(retenues)


def profile_picture(persona: Persona, out_dir: Path | None = None) -> Path:
    """Portrait carré : la photo de profil des deux comptes."""
    out_dir = out_dir or settings.paths.products
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt = persona.image_prompt(
        "looking at the camera without posing, head and shoulders, "
        "slight natural smile, unposed, soft daylight from a window",
        outfit="a plain grey sweatshirt, hair tied up loosely",
        location="a small flat with a softly blurred desk behind her",
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

## 5. L'ordre de publication

Le récit a un début. Ne publie pas le journal du compte avant d'avoir raconté
pourquoi elle s'y est mise — sinon personne ne comprend de quoi il s'agit.

1. **Épisode 1** : pourquoi elle a commencé (aucune donnée requise)
2. Puis les épisodes de construction, au rythme de ton avancée réelle
3. Le point sur le compte de 100 € **seulement** une fois le compte ouvert

Les épisodes s'ouvrent tout seuls au fur et à mesure que tu remplis
`data/trading/journal.json`. L'agent refuse de raconter une étape que tu n'as
pas franchie.

## 6. Ce qui compte vraiment les premières semaines

1. **Publier tous les jours** — la régularité prime sur la qualité au départ.
2. **Répondre à tous les commentaires** — manuel, et c'est le plus rentable.
3. **Montrer une mauvaise semaine dès qu'il y en a une** — c'est ce qui rendra
   les bonnes crédibles. C'est le cœur de la promesse du compte.
4. **Ne rien vendre.** Si on te demande le programme, la réponse est non.
"""
    md_path = out_dir / "kit-lancement.md"
    md_path.write_text(md, encoding="utf-8")
    html_path = out_dir / "kit-lancement.html"
    html_path.write_text(markdown_to_html(md, f"Kit de lancement — {ident['full_name']}"),
                         encoding="utf-8")
    return {"markdown": md_path, "html": html_path, "photo": photo}
