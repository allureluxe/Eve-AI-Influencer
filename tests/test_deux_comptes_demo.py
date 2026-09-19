"""Deux comptes demo en parallele, sans jamais se melanger.

Demande de l'operateur le 20 septembre : « une fois la methode trouvee
tu vas creer un 2e compte demo sur l'appli avec 3 300 EUR de capital
demo ». C'est la bonne facon de comparer deux methodes -- le MEME
marche, aux MEMES heures. Les essayer l'une apres l'autre melangerait
l'effet du reglage et celui du marche, la faute que CLAUDE.md appelle
« une mesure qui bouge deux variables ».

Ce qui est verrouille ici : l'isolation. Le 18 septembre, la simulation
a ecrit dans les fichiers du robot REEL parce qu'un seul chemin n'avait
pas ete isole. A deux simulations, la meme faute se reproduirait entre
elles -- et elle serait plus difficile a voir, les deux etant
« virtuelles ».
"""
import inspect
import subprocess
import sys


class TestLeNomDuCompteSuffixeTousLesFichiers:
    def test_aucun_chemin_ne_reste_ecrit_en_dur(self):
        source = inspect.getsource(__import__("run_demo"))
        for fichier in ("state", "trades", "objectives", "journal", "outbox"):
            en_dur = f'"data/{fichier}-demo.'
            assert en_dur not in source, (
                f"data/{fichier}-demo reste ecrit en dur : le 2e compte "
                "ecrirait dans les fichiers du premier")

    def test_les_deux_comptes_ont_des_chemins_differents(self):
        source = inspect.getsource(__import__("run_demo"))
        # Chaque fichier est construit a partir du nom du compte.
        for fichier in ("state", "trades", "objectives", "journal", "outbox"):
            assert f'{fichier}-{{compte}}' in source, (
                f"le fichier {fichier} ne suit pas le nom du compte")


class TestOnNePeutPasSeFAIREPASSERPOURLEROBOTREEL:
    """Le garde-fou qui compte le plus."""

    def test_un_nom_qui_ne_commence_pas_par_demo_est_refuse(self):
        r = subprocess.run(
            [sys.executable, "run_demo.py", "--compte", "reel"],
            capture_output=True, text=True, timeout=60)
        assert r.returncode == 2, (
            "un compte nomme « reel » a ete accepte : il ecrirait dans "
            "data/state-reel.json, et plus rien ne garantit l'isolation")
        assert "refuse" in r.stdout.lower()

    def test_le_nom_par_defaut_reste_demo(self):
        """L'ancien comportement ne doit pas changer : le service en
        service ne passe pas `--compte`."""
        source = inspect.getsource(__import__("run_demo"))
        assert '"--compte", default="demo"' in source


class TestLesPublicationsPortentLeNomDuCompte:
    def test_le_signal_publie_porte_le_compte(self):
        from gold_bot.signal_publisher import SignalPublie
        s = SignalPublie(reference="x:1", pair="BTC/EUR", side="buy",
                         entry_price=100.0, stop_loss=90.0, compte="demo2")
        assert s.vers_supabase()["compte"] == "demo2"

    def test_le_premier_compte_n_alourdit_pas_chaque_ligne(self):
        """`demo` est la valeur par defaut en base : l'ecrire a chaque
        fois n'ajouterait rien."""
        from gold_bot.signal_publisher import SignalPublie
        s = SignalPublie(reference="x:1", pair="BTC/EUR", side="buy",
                         entry_price=100.0, stop_loss=90.0)
        assert "compte" not in s.vers_supabase()

    def test_les_alertes_portent_le_compte(self):
        from gold_bot.notifiers import AlluxeBotChannel
        canal = AlluxeBotChannel(est_demo=True, compte="demo2")
        assert canal.compte == "demo2"
        source = inspect.getsource(AlluxeBotChannel.send)
        assert '"compte": self.compte' in source, (
            "les alertes du 2e compte se melangeraient a celles du 1er")
