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
