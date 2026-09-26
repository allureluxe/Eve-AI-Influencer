"""La suite de tests n'ecrit JAMAIS dans les donnees du robot en service.

CE QUE CE FICHIER EMPECHE
-------------------------
Le 13 septembre 2026, en cherchant pourquoi le compteur des 40 trades
affichait 0/40 apres 151 trades reels, trois coupables sont apparus.
Les deux premiers etaient des diagnostics (`etat.py`,
`plan_croissance.py`) qui ecrivaient le marqueur de strategie.

Le troisieme etait CETTE SUITE DE TESTS.

Un test qui construit un moteur avec la vraie configuration ecrit
`data/strategie-bitvavo.json` — avec l'empreinte de sa propre
configuration calibree (`unite: M15`), pas celle du robot. Au
demarrage suivant, le robot constate un changement de strategie et
REMET A ZERO l'echantillon qui commande le palier de risque.

Autrement dit : lancer les tests effacait la preuve accumulee par le
robot en argent reel. Silencieusement, et depuis des semaines.

COMMENT
-------
Toutes les variables qui designent un fichier d'etat sont detournees
vers un dossier temporaire, AVANT que le moindre test ne s'importe.
Un test qui veut lire un vrai fichier doit le dire explicitement, ce
qui est exactement le bon defaut.

Ce n'est pas un contournement : c'est la regle. Une suite de tests qui
touche aux donnees de production n'est pas une suite de tests, c'est un
risque de plus.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

#: Chaque variable pointe un fichier que le robot en service utilise.
#: En ajouter une ici est plus sur que d'esperer qu'aucun test ne la
#: touche.
FICHIERS_D_ETAT = {
    "GB_STRATEGIE_FILE": "strategie.json",
    "GB_TRADES_FILE": "trades.jsonl",
    "GB_STATE_FILE": "etat.json",
    "GB_JOURNAL_FILE": "journal.jsonl",
    "GB_OBJECTIFS_FILE": "objectifs.json",
    "GB_POIDS_FILE": "poids.json",
}

# Le detournement se fait A L'IMPORT, pas dans une fixture : certains
# modules lisent ces variables au moment ou ils sont importes, donc
# avant qu'une fixture n'ait eu la moindre chance de tourner.
_BAC_A_SABLE = tempfile.mkdtemp(prefix="gold-bot-tests-")
for _variable, _nom in FICHIERS_D_ETAT.items():
    os.environ[_variable] = str(Path(_BAC_A_SABLE) / _nom)


@pytest.fixture(autouse=True)
def _pas_d_ecriture_en_production():
    """Verifie apres CHAQUE test que rien n'a fui vers data/.

    La redirection ci-dessus couvre les chemins qui passent par une
    variable d'environnement. Un test qui ecrirait « data/... » en dur
    y echapperait — d'ou ce controle, qui nomme le test fautif au lieu
    de laisser le probleme se manifester des semaines plus tard sous la
    forme d'un compteur remis a zero.
    """
    vrai = Path(__file__).resolve().parent.parent / "data"
    surveilles = ["strategie-bitvavo.json", "trades.jsonl", "etat-bitvavo.json"]
    avant = {n: _empreinte(vrai / n) for n in surveilles}

    yield

    for nom, signature in avant.items():
        assert _empreinte(vrai / nom) == signature, (
            f"ce test a modifie data/{nom}, qui appartient au robot en "
            f"service. Utiliser tmp_path ou une des variables de "
            f"FICHIERS_D_ETAT (voir tests/conftest.py).")


def _empreinte(chemin: Path):
    try:
        etat = chemin.stat()
        return (etat.st_mtime_ns, etat.st_size)
    except OSError:
        return None


# --------------------------------------------------------------------------
#: Les cles qui decident QUELS FOURNISSEURS composent une chaine de
#: generation. Elles n'ont rien a faire dans un test unitaire : leur
#: presence change le resultat sans que le test en parle.
CLES_DE_FOURNISSEURS = (
    "OPENAI_API_KEY",
    "STABILITY_API_KEY",
    "HUGGINGFACE_API_KEY",
    "TOGETHER_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_API_TOKEN",
    "RUNWAYML_API_SECRET",
    "RUNWAY_API_KEY",
    # AJOUTES LE 26 SEPTEMBRE, quelques heures apres cette fixture, et
    # oublies au moment de brancher Kling : six tests sont tombes des
    # que l'operateur a pose sa cle. C'est la faiblesse de cette liste —
    # elle ne se met pas a jour toute seule. `test_isolation_des_cles.py`
    # la compare desormais aux variables reellement lues par le code.
    "KLING_API_KEY",
    "KLING_ACCESS_KEY",
    "KLING_SECRET_KEY",
    "LUNA_VIDEO_MODELE_KLING",
    "LUNA_VIDEO_MODELE_SORA",
    "LUNA_SORA_ACTIF",
    # Le TEXTE aussi a ses fournisseurs : ce sont eux qui decident si
    # Luna parle avec Claude, avec un endpoint compatible OpenAI, ou
    # avec le repli hors ligne. Meme raisonnement que pour l'image.
    "ANTHROPIC_API_KEY",
    "LUNA_API_KEY",
    "LUNA_API_MODELE",
    "LUNA_MODELE",
    "LUNA_IMAGE_URL",
    "LUNA_IMAGE_KEY",
    "LUNA_IMAGE_MODELE",
    "LUNA_IMAGE_MODELE_OPENAI",
    "TIKTOK_ACCESS_TOKEN",
)


@pytest.fixture(autouse=True)
def _sans_les_cles_de_l_operateur(monkeypatch):
    """La suite de tests ne LIT pas le `.env` du serveur non plus.

    LE PENDANT DE CE FICHIER, TROUVE LE 26 SEPTEMBRE. Le reste de ce
    conftest empeche les tests d'ECRIRE dans les donnees du robot. Il
    manquait l'autre sens : plusieurs modules de `ops/` appellent
    `charger_env()` A L'IMPORT, donc le simple fait qu'un test importe
    l'un d'eux verse le `.env` REEL de l'operateur dans l'environnement
    de toute la session de tests.

    C'etait invisible tant qu'aucune cle n'y figurait. Le jour ou
    l'operateur a pose sa cle OpenAI, trois tests de
    `TestGenerateurImages` se sont mis a echouer — ils passaient seuls
    et tombaient dans la suite complete, parce qu'OpenAI s'ajoutait en
    tete d'une chaine dont ils verifiaient la composition.

    Le defaut n'etait donc PAS dans ces trois tests : ils avaient
    raison, et c'est l'environnement qui avait change sous eux. Les
    corriger aurait ete masquer le probleme — c'est exactement ce que
    la regle « ne jamais supprimer un test pour faire passer la suite »
    interdit dans le CLAUDE.md de ce depot.

    Un test qui a besoin d'une cle la pose lui-meme avec
    `monkeypatch.setenv`, qui s'applique apres cette fixture et
    l'emporte donc. C'est la forme juste : la cle fait alors partie de
    ce que le test DIT, au lieu de venir d'une machine.
    """
    for cle in CLES_DE_FOURNISSEURS:
        monkeypatch.delenv(cle, raising=False)
    yield
