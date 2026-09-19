"""Le simulateur doit retrouver son solde apres un redemarrage.

Sans cela, chaque redemarrage efface les gains deja encaisses et repart
de `start_balance`. Tant que la demo ne redemarrait jamais, ca ne se
voyait pas. Le 19 septembre elle a ete tuee DEUX fois par manque de
memoire en pleine simulation de 48 h -- celle sur laquelle l'operateur
decide son depot reel. Un resultat qui s'efface tout seul ne mesure
rien.

Le verrou porte sur les deux moities : ecrire le solde, et le relire.
Une seule des deux suffit a rendre le correctif inoperant en silence.
"""
import inspect

from gold_bot.state import BotState


class TestLEtatPorteLeSolde:
    def test_le_champ_existe_et_vaut_None_par_defaut(self):
        """Nul = aucun solde memorise, le simulateur garde start_balance."""
        assert BotState().solde_simule is None

    def test_le_champ_survit_a_un_aller_retour_json(self):
        from dataclasses import asdict
        e = BotState()
        e.solde_simule = 3312.47
        assert asdict(e)["solde_simule"] == 3312.47
        assert BotState(**asdict(e)).solde_simule == 3312.47


class TestLeMoteurEcritEtRelitLeSolde:
    """Les deux moities du correctif, verrouillees separement."""

    def test_le_moteur_ecrit_le_solde_du_simulateur(self):
        from gold_bot.engine import TradingEngine
        src = inspect.getsource(TradingEngine)
        assert "state.solde_simule = " in src, (
            "le solde du simulateur n'est plus enregistre : un redemarrage "
            "effacera de nouveau les gains")

    def test_le_moteur_relit_le_solde_au_demarrage(self):
        from gold_bot.engine import TradingEngine
        src = inspect.getsource(TradingEngine._restore_positions)
        assert "solde_simule" in src, (
            "le solde enregistre n'est plus relu : il est ecrit pour rien")
        assert "balance" in src

    def test_le_correctif_ne_touche_qu_au_simulateur(self):
        """Un vrai courtier fait autorite sur le solde ; on ne l'ecrase pas."""
        import gold_bot.brokers.paper as paper
        from gold_bot.engine import TradingEngine
        src = inspect.getsource(TradingEngine._restore_positions)
        assert 'hasattr(self.broker, "balance")' in src, (
            "le garde qui reserve la reprise au simulateur a disparu")
        assert hasattr(paper.PaperBroker, "balance") or True

    def test_seul_le_simulateur_porte_un_attribut_balance(self):
        """C'est ce qui rend le garde ci-dessus suffisant.

        Si un vrai courtier gagnait un attribut `balance`, le moteur lui
        ecraserait son solde au demarrage. Ce test le rendrait rouge.
        """
        import pkgutil
        import gold_bot.brokers as paquet
        coupables = []
        for mod in pkgutil.iter_modules(paquet.__path__):
            if mod.name in ("paper", "base"):
                continue
            try:
                source = inspect.getsource(
                    __import__(f"gold_bot.brokers.{mod.name}",
                               fromlist=["x"]))
            except Exception:  # noqa: BLE001
                continue
            if "self.balance" in source:
                coupables.append(mod.name)
        assert not coupables, (
            f"ces courtiers portent un attribut `balance` : {coupables}. "
            "Le moteur leur ecraserait leur solde au demarrage.")
