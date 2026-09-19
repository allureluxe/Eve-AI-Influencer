"""Les garde-fous de l'agent Alluxe.

L'agent a le shell complet sur le serveur qui heberge le robot de
trading, ses cles d'API et son historique. Ces tests verrouillent les
quelques gestes dont on ne revient pas. Si l'un d'eux echoue, ce n'est
pas le test qu'il faut changer.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from ops.agent_outils import (ActionRefusee, RACINE, chemin_sur, commande_sure,
                              environnement_sans_cles, executer, lire_fichier,
                              modifier_fichier)


class TestLesCommandesNeVoientAucuneCle(unittest.TestCase):
    """LA protection qui compte vraiment.

    Un filtre de texte se contourne (`printenv`, `python3 -c "import os;
    print(os.environ)"`, un nom de fichier obfusque...). Retirer la
    valeur de l'environnement, non. Le processus de l'agent charge `.env`
    pour parler a Supabase ; ses sous-processus, eux, ne doivent rien en
    voir.
    """

    def test_aucune_variable_sensible_ne_passe(self):
        propre = environnement_sans_cles()
        for nom in propre:
            for mot in ("KEY", "TOKEN", "SECRET", "PASSWORD", "SUPABASE",
                        "BITVAVO", "INSTAGRAM", "TIKTOK"):
                self.assertNotIn(mot, nom.upper(),
                                 f"{nom} ne doit pas etre passee aux commandes")

    def test_les_cles_reelles_du_projet_sont_bien_retirees(self):
        propre = environnement_sans_cles()
        for nom in ("BITVAVO_API_KEY", "BITVAVO_API_SECRET",
                    "SUPABASE_SERVICE_KEY", "GITHUB_ACTIONS_WRITE_TOKEN",
                    "INSTAGRAM_PASSWORD", "TELEGRAM_BOT_TOKEN"):
            self.assertNotIn(nom, propre)

    def test_le_minimum_pour_travailler_reste_la(self):
        propre = environnement_sans_cles()
        self.assertIn("PATH", propre, "sans PATH aucune commande ne tourne")

    def test_les_lectures_d_environnement_sont_refusees(self):
        for commande in ("printenv", "env", "set",
                         "python3 -c \"import os; print(os.environ)\"",
                         "python3 -c 'print(os.getenv(\"BITVAVO_API_KEY\"))'"):
            with self.assertRaises(ActionRefusee, msg=commande):
                commande_sure(commande)


class TestLesClesSontIntouchables(unittest.TestCase):
    """Un agent qui peut lire .env peut le recopier dans une conversation."""

    def test_le_env_ne_se_lit_pas(self):
        for chemin in (".env", "./.env", "ops/../.env", ".env.backup-20260829-143430"):
            with self.assertRaises(ActionRefusee, msg=chemin):
                chemin_sur(chemin)

    def test_les_cles_privees_ne_se_lisent_pas(self):
        for chemin in ("cle.pem", "dossier/serveur.key", "credentials.json",
                       "firebase/service-account.json", ".ssh/id_rsa"):
            with self.assertRaises(ActionRefusee, msg=chemin):
                chemin_sur(chemin)

    def test_aucune_commande_ne_peut_lire_le_env(self):
        for commande in ("cat .env", "grep SUPABASE .env", "cp .env /tmp/x",
                         "python3 -c \"print(open('.env').read())\""):
            with self.assertRaises(ActionRefusee, msg=commande):
                commande_sure(commande)

    def test_l_outil_executer_refuse_vraiment(self):
        """`executer` doit LEVER, pas rendre un resultat.

        L'assertion d'origine attendait un dictionnaire sans le mot
        "SUPABASE" dedans -- elle testait donc le mauvais comportement :
        un outil qui rendrait poliment le contenu du .env sans ce mot
        l'aurait passee. C'est l'assertion qui etait fausse, pas le code
        (regle du depot : on corrige l'assertion, jamais le code correct).
        """
        with self.assertRaises(ActionRefusee):
            executer({"commande": "cat .env"})


class TestOnNeSortPasDuDepot(unittest.TestCase):
    def test_remonter_hors_du_depot_est_refuse(self):
        for chemin in ("../../etc/passwd", "/etc/passwd", "../autre-projet"):
            with self.assertRaises(ActionRefusee, msg=chemin):
                chemin_sur(chemin)

    def test_un_chemin_normal_passe(self):
        self.assertTrue(chemin_sur("gold_bot/engine.py").startswith(RACINE))


class TestLeRobotReelNeSeTouchePas(unittest.TestCase):
    """Il porte de vrais euros et de vraies positions ouvertes."""

    def test_on_ne_peut_pas_l_arreter(self):
        for commande in ("systemctl stop robot-dual-live",
                         "sudo systemctl restart robot-dual-live",
                         "systemctl  kill   robot-dual-live"):
            with self.assertRaises(ActionRefusee, msg=commande):
                commande_sure(commande)

    def test_la_demo_reste_pilotable(self):
        """La demo n'engage rien : l'agent doit pouvoir la consulter."""
        commande_sure("systemctl is-active robot-demo")
        commande_sure("journalctl -u robot-demo -n 50")


class TestCeQuiEffaceSansRetour(unittest.TestCase):
    def test_effacements_recursifs_refuses(self):
        for commande in ("rm -rf data", "rm -fr /", "rm  -r -f  gold_bot"):
            with self.assertRaises(ActionRefusee, msg=commande):
                commande_sure(commande)

    def test_reecriture_d_historique_refusee(self):
        for commande in ("git push --force", "git push -f origin main",
                         "git reset --hard HEAD~3", "git clean -fd"):
            with self.assertRaises(ActionRefusee, msg=commande):
                commande_sure(commande)

    def test_ecraser_un_fichier_non_commite_est_refuse(self):
        with self.assertRaises(ActionRefusee):
            commande_sure("git checkout -- gold_bot/engine.py")

    def test_pas_de_privileges_administrateur(self):
        with self.assertRaises(ActionRefusee):
            commande_sure("sudo apt install quelquechose")


class TestCeQuiDoitResterPermis(unittest.TestCase):
    """Un assistant qui ne peut rien faire ne sert a rien : le travail
    normal doit passer sans friction."""

    def test_le_travail_courant_passe(self):
        for commande in (
            "python3 -m pytest -q",
            "git status",
            "git diff gold_bot/engine.py",
            "git add gold_bot/engine.py && git commit -m 'essai'",
            "git push",
            "python3 etat.py",
            "npm test",
            "journalctl -u alluxe-agent -n 20",
            "ls data/",
            "grep -rn 'donchian' gold_bot/",
        ):
            commande_sure(commande)   # ne doit rien lever


class TestNavigationEtTor(unittest.TestCase):
    def test_les_adresses_internes_sont_refusees(self):
        """169.254.169.254 rend les identifiants de l'hebergeur sans mot
        de passe. Un agent a qui on passe une URL piegee irait la lire."""
        from ops.agent_outils import url_sure
        for url in ("http://169.254.169.254/latest/meta-data/",
                    "http://localhost:8000/", "http://127.0.0.1/",
                    "http://192.168.1.1/", "http://10.0.0.5/",
                    "file:///etc/passwd", "ftp://ailleurs/x"):
            with self.assertRaises(ActionRefusee, msg=url):
                url_sure(url)

    def test_une_adresse_publique_passe(self):
        from ops.agent_outils import url_sure
        self.assertTrue(url_sure("https://arxiv.org/abs/1234.5678"))

    def test_une_adresse_onion_exige_tor(self):
        """Sans Tor, l'ouvrir en direct ferait fuiter la demande vers le
        DNS public -- et echouerait de toute facon."""
        from ops.agent_outils import lire_page_web, tor_disponible
        if tor_disponible():
            self.skipTest("Tor est installe : ce cas ne s'applique pas")
        with self.assertRaises(ActionRefusee) as cas:
            lire_page_web({"url": "http://exemplefaux7xyz.onion/"})
        self.assertIn("Tor", str(cas.exception))


class TestModificationDeFichier(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp(dir=os.path.join(RACINE, "data"))
        self.nom = os.path.relpath(
            os.path.join(self.dossier, "essai.txt"), RACINE)
        with open(os.path.join(RACINE, self.nom), "w") as f:
            f.write("alpha\nbeta\nalpha\n")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dossier, ignore_errors=True)

    def test_un_texte_present_deux_fois_est_refuse(self):
        """Sinon le modele modifie la mauvaise occurrence en silence."""
        r = modifier_fichier({"chemin": self.nom, "ancien_texte": "alpha",
                              "nouveau_texte": "gamma"})
        self.assertIn("erreur", r)
        self.assertIn("2 fois", r["erreur"])

    def test_un_texte_unique_est_modifie(self):
        r = modifier_fichier({"chemin": self.nom, "ancien_texte": "beta",
                              "nouveau_texte": "gamma"})
        self.assertTrue(r.get("ok"))
        with open(os.path.join(RACINE, self.nom)) as f:
            self.assertIn("gamma", f.read())

    def test_lire_rend_des_numeros_de_ligne(self):
        r = lire_fichier({"chemin": self.nom})
        self.assertIn("1  alpha", r["contenu"])
        self.assertEqual(r["lignes_totales"], 3)


if __name__ == "__main__":
    unittest.main()
