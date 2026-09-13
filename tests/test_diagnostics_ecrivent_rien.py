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
            # Deux protections valables, et la seconde est meilleure :
            #   - detourner GB_STRATEGIE_FILE vers un fichier jetable ;
            #   - ou n'appeler le marqueur qu'en `lecture_seule=True`,
            #     ce qui rend la VRAIE date sans jamais l'ecrire.
            if ("GB_STRATEGIE_FILE" not in texte
                    and "lecture_seule=True" not in texte):
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



class TestLeJournalNeSeDoublePas(unittest.TestCase):
    """`load()` ajoutait sans vider, et `__init__` l'appelle deja.

    Consequence mesuree le 13 septembre 2026 : `plan_croissance.py`
    annoncait « 38/40 trades, plus que 2 » quand il y en avait 19. Un
    palier de risque franchi sur un echantillon deux fois trop petit,
    c'est precisement ce que le module de croissance existe pour
    empecher.
    """

    def test_relire_le_journal_ne_double_pas_les_trades(self):
        import json
        from tempfile import TemporaryDirectory
        from gold_bot.state import TradeJournal

        with TemporaryDirectory() as tmp:
            chemin = Path(tmp) / "trades.jsonl"
            # Les champs et la casse viennent d'une VRAIE ligne du
            # journal : `Side` attend « BUY », pas « buy », et une
            # ligne incomplete est avalee en silence par `load()` —
            # ce qui donnait un journal vide et un test trompeur.
            ligne = {
                "position_id": "1", "symbol": "BTCEUR", "side": "BUY",
                "volume": 0.1, "entry_price": 100.0, "exit_price": 110.0,
                "opened_at": 1.0, "closed_at": 2.0, "profit": 1.0,
                "r_multiple": 1.0, "reason": "tp", "tp_extensions": 0,
                "max_favorable_r": 1.0, "partial": False,
            }
            chemin.write_text("\n".join(json.dumps(ligne | {"position_id": str(i)})
                                        for i in range(5)))

            journal = TradeJournal(path=str(chemin))
            self.assertEqual(len(journal.trades), 5)
            journal.load()
            self.assertEqual(len(journal.trades), 5,
                             "un second load() a double le journal")
            journal.load()
            self.assertEqual(len(journal.trades), 5)

    def test_load_sur_un_fichier_absent_vide_la_liste(self):
        # Sinon un rechargement apres suppression du fichier garderait
        # l'ancien contenu en memoire, et les statistiques porteraient
        # sur des trades qui n'existent plus.
        from gold_bot.state import TradeJournal
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp:
            journal = TradeJournal(path=str(Path(tmp) / "absent.jsonl"))
            journal.trades.append(object())          # type: ignore[arg-type]
            journal.load()
            self.assertEqual(journal.trades, [])

if __name__ == "__main__":
    unittest.main()
