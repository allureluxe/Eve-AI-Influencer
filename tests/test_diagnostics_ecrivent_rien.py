"""Aucun diagnostic ne doit toucher au marqueur de strategie.

POURQUOI CE TEST EXISTE
-----------------------
Le marqueur `data/strategie-<broker>.json` date le debut de la
configuration en service. Quand son empreinte change, le robot conclut
que la strategie a change et REMET A ZERO l'echantillon des 40 trades —
celui qui commande le passage du palier « preuve » (0,6 % de risque) au
palier « croissance » (1,0 %).

Plusieurs diagnostics CALIBRENT la configuration pour raisonner : ils
choisissent une unite de temps tenable au capital du moment (D1 -> H1,
stop temporel 7200 -> 300 min). Cette configuration calibree n'est pas
celle du robot, mais le marqueur est partage. Chaque lancement
l'ecrasait donc, et le robot repartait de zero au demarrage suivant.

CE PIEGE S'EST REFERME TROIS FOIS :
  9 septembre 2026  — corrige dans rapport_matin.py
 13 septembre 2026  — retrouve dans etat.py ET plan_croissance.py.
                      Le compteur affichait 0/40 apres 151 trades
                      reels, et les deux empreintes s'ecrasaient a
                      chaque lancement (065a24517609 <-> 3c10cb08dac1).

Corriger sans verrouiller aurait garanti une quatrieme fois. Ce test
couvre TOUT script a la racine : un diagnostic ajoute demain sera
attrape avant d'avoir efface un echantillon.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent

#: Ce qui, dans un script, finit par ecrire le marqueur. `calibrer`
#: n'ecrit rien par lui-meme, mais un script qui calibre produit une
#: configuration DIFFERENTE de celle du robot ; s'il touche ensuite au
#: marqueur, il pose la mauvaise empreinte.
DECLENCHEURS = ("TradingEngine", "depuis_quand", "marqueur", "calibrer")

#: Les lanceurs : eux DOIVENT ecrire le marqueur, c'est leur role.
#: Reconnus par leur prefixe plutot que par une liste : une liste
#: nommee se perime au premier lanceur ajoute — ce test a echoue des
#: son ecriture sur `run_bot.py` et `run_pionex.py`, que j'avais
#: oublies.
def _est_un_lanceur(nom: str) -> bool:
    return nom.startswith("run_") or nom == "run.py"


def _scripts_racine() -> list[Path]:
    return sorted(p for p in RACINE.glob("*.py")
                  if not _est_un_lanceur(p.name) and not p.name.startswith("_"))


class TestAucunDiagnosticNEcraseLeMarqueur(unittest.TestCase):

    def test_tout_script_qui_calibre_protege_le_marqueur(self):
        coupables = []
        for script in _scripts_racine():
            texte = script.read_text(encoding="utf-8", errors="replace")
            if not any(d in texte for d in DECLENCHEURS):
                continue
            if "GB_STRATEGIE_FILE" not in texte:
                coupables.append(script.name)

        self.assertEqual(
            coupables, [],
            "ces scripts construisent ou calibrent une configuration sans "
            "detourner GB_STRATEGIE_FILE : au prochain demarrage du robot, "
            "l'echantillon des 40 trades repartira de zero. Ajouter en tete "
            "de fichier :\n"
            '    os.environ["GB_STRATEGIE_FILE"] = "/tmp/strategie-<nom>.json"\n'
            f"scripts : {coupables}")

    def test_la_protection_vise_bien_un_fichier_jetable(self):
        # Detourner vers un chemin du depot ne protegerait rien : il
        # serait relu par le robot comme le vrai marqueur.
        for script in _scripts_racine():
            texte = script.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(
                    r'GB_STRATEGIE_FILE"?\]\s*=\s*"([^"]+)"', texte):
                chemin = m.group(1)
                self.assertTrue(
                    chemin.startswith("/tmp/"),
                    f"{script.name} detourne le marqueur vers {chemin!r} : "
                    "il faut un chemin jetable sous /tmp/, sinon le robot "
                    "le relira comme le vrai marqueur")

    def test_la_protection_precede_les_imports_de_gold_bot(self):
        """Poser la variable trop tard ne sert a rien.

        On compare a la premiere LIGNE D'IMPORT de `gold_bot`, pas a la
        premiere occurrence des mots declencheurs : ceux-ci
        apparaissent aussi dans la documentation en tete de fichier, ce
        qui faisait echouer ce test sur du code pourtant correct.
        """
        # `gold_bot.env` est EXCLU, et ce n'est pas une facilite : il
        # charge le fichier .env et doit donc s'executer avant tout le
        # reste, y compris avant la garde. Il n'ecrit aucun marqueur.
        motif = re.compile(
            r'^\s*(?:from|import)\s+gold_bot(?!\.env\b)\b', re.M)
        for script in _scripts_racine():
            texte = script.read_text(encoding="utf-8", errors="replace")
            if "GB_STRATEGIE_FILE" not in texte:
                continue
            premier = motif.search(texte)
            if premier is None:
                continue
            self.assertLess(
                texte.index("GB_STRATEGIE_FILE"), premier.start(),
                f"{script.name} pose GB_STRATEGIE_FILE apres le premier "
                "import de gold_bot : le marqueur peut deja etre ecrit")


if __name__ == "__main__":
    unittest.main()
