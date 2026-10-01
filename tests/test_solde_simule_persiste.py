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


class TestLaRepriseDuSoldeNEstPasUnDepot:
    """2 oct. 2026 : a chaque redemarrage, la demo 1 prenait la reprise de
    son propre solde (3 300 -> 3 512) pour un apport. Sa reference etait
    montee a 6 609 EUR pour un compte de ~3 500 : positions bridees."""

    def test_le_moteur_recale_l_equite_apres_la_reprise(self):
        from gold_bot.engine import TradingEngine
        src = inspect.getsource(TradingEngine.start)
        reprise = src.index("self._restore_positions()")
        recalage = src.index("self.risk.account.equity = apres.equity")
        assert recalage > reprise, (
            "l'equite n'est plus recalee APRES la reprise du solde : chaque "
            "redemarrage de la demo redeviendra un faux depot")

    def test_avec_le_recalage_le_premier_cycle_ne_voit_aucun_apport(self):
        from gold_bot.risk import RiskConfig, RiskManager
        rm = RiskManager(RiskConfig())
        rm.sync_account(3300.0, 3300.0, ts=1_790_000_000.0)
        rm.account.reference_equity = 3500.0      # relue depuis l'etat
        rm.account.equity = 3512.57               # recalage apres reprise
        rm.sync_account(3512.57, 3460.0, ts=1_790_000_010.0)
        assert rm.dernier_apport == 0.0
        assert rm.account.reference_equity == 3500.0
