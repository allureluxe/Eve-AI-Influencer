"""La liste d'isolation ne doit pas prendre de retard sur le code.

POURQUOI CE TEST EXISTE

Le 26 septembre au matin, une fixture a ete ajoutee pour que la suite de
tests ne lise plus le `.env` reel de l'operateur : plusieurs modules de
`ops/` appellent `charger_env()` a l'import, et il suffisait qu'un test
en importe un pour que toutes les cles du serveur se repandent dans la
session.

L'apres-midi meme, en branchant Kling, j'ai oublie d'ajouter ses trois
variables a cette liste. Six tests sont tombes des que l'operateur a
pose sa cle — pas parce qu'ils avaient tort, mais parce que la fabrique
choisissait soudain un fournisseur qu'ils ne connaissaient pas.

Une liste tenue a la main prend toujours du retard sur le code. Celle-ci
est donc comparee aux variables REELLEMENT lues par les modules de
generation : ajouter un fournisseur sans l'isoler fait echouer ce test
tout de suite, au lieu d'attendre qu'une cle apparaisse en production.
"""
from __future__ import annotations

import re
from pathlib import Path

from conftest import CLES_DE_FOURNISSEURS

RACINE = Path(__file__).resolve().parent.parent

#: Les fichiers qui choisissent un fournisseur de generation.
FICHIERS = ("luna/media.py", "luna/moteurs.py")

#: Ce qui trahit une variable de FOURNISSEUR plutot qu'un reglage
#: ordinaire : une cle, un secret, un jeton, un identifiant de compte,
#: ou le nom d'un modele — tout ce dont la presence change QUI repond.
# `_MODELE` sans souligne final : la premiere version exigeait
# « _MODELE_ » et laissait donc passer `LUNA_IMAGE_MODELE`, qui se
# termine par le mot. Le detecteur avait le meme angle mort que la
# liste qu'il surveille.
MOTIFS = ("_API_KEY", "_API_SECRET", "_ACCESS_KEY", "_SECRET_KEY",
          "_API_TOKEN", "_ACCOUNT_ID", "_MODELE", "_ACTIF")


def _variables_lues() -> set[str]:
    trouvees: set[str] = set()
    for nom in FICHIERS:
        texte = (RACINE / nom).read_text(encoding="utf-8")
        for variable in re.findall(r'os\.getenv\(\s*"([A-Z0-9_]+)"', texte):
            if any(m in variable for m in MOTIFS):
                trouvees.add(variable)
    return trouvees


def test_toute_variable_de_fournisseur_est_isolee():
    manquantes = _variables_lues() - set(CLES_DE_FOURNISSEURS)
    assert not manquantes, (
        "ces variables decident quel fournisseur repond et ne sont pas "
        f"neutralisees dans les tests : {sorted(manquantes)}. Les ajouter "
        "a CLES_DE_FOURNISSEURS dans tests/conftest.py, sinon la suite "
        "changera de comportement le jour ou l'operateur posera la cle "
        "correspondante — exactement ce qui est arrive avec Kling le "
        "26 septembre.")


def test_la_liste_ne_contient_pas_de_variable_fantome():
    """L'inverse : une entree qui ne correspond plus a rien.

    Moins grave — neutraliser une variable inutilisee ne casse rien —
    mais une liste qui accumule des noms morts finit par ne plus etre
    relue, et c'est comme ca qu'un oubli passe inapercu.
    """
    lues = _variables_lues()
    # Les variables posees ailleurs que dans les deux fichiers surveilles
    # (Instagram, TikTok, Stability...) restent legitimes.
    connues_ailleurs = {"TIKTOK_ACCESS_TOKEN", "STABILITY_API_KEY",
                        "HUGGINGFACE_API_KEY", "TOGETHER_API_KEY",
                        "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN",
                        "OPENAI_API_KEY", "RUNWAYML_API_SECRET",
                        "RUNWAY_API_KEY", "LUNA_IMAGE_URL", "LUNA_IMAGE_KEY"}
    fantomes = set(CLES_DE_FOURNISSEURS) - lues - connues_ailleurs
    assert not fantomes, (
        f"entrees qui ne correspondent plus a rien : {sorted(fantomes)}")
