"""Le stop suiveur doit arriver jusqu'a l'application.

`stop_loss` est ecrit une seule fois, a l'ouverture, et ne bouge jamais
-- c'est voulu, tout le calcul du R en depend. Mais l'application
affichait donc le stop d'ORIGINE en croyant montrer la protection
actuelle, alors que le suiveur avait remonte cote robot. C'est
exactement l'information que l'operateur a demandee : « le stop loss
d'ouverture et l'actuel s'il a monte ».
"""
import pytest

from gold_bot.signal_publisher import SignalPublie, SignalPublisher


class _ClientFactice:
    def __init__(self):
        self.inserts = []
        self.modifs = []

    def inserer(self, table, corps):
        self.inserts.append((table, corps))

    def modifier(self, table, filtre, corps):
        self.modifs.append((table, filtre, corps))


@pytest.fixture
def publieur(tmp_path):
    p = SignalPublisher.__new__(SignalPublisher)
    import threading
    p.client = _ClientFactice()
    p._verrou = threading.RLock()
    p._file = []
    p._publies = set()
    p._echecs = 0
    p._pause_jusqua = 0.0
    p.est_demo = False
    p.fichier_file = tmp_path / "file.jsonl"
    return p


class TestLeSuiviNeTouchePasAuStopDOuverture:
    def test_il_ecrit_stop_loss_actuel_et_rien_d_autre(self, publieur):
        publieur.publier_suivi("abc:1", 1.2345)
        assert len(publieur.client.modifs) == 1
        table, filtre, corps = publieur.client.modifs[0]
        assert table == "signals"
        assert filtre == "reference=eq.abc:1"
        assert corps == {"stop_loss_actuel": 1.2345}, (
            "le suivi ne doit ecrire QUE le stop courant : toucher "
            "`stop_loss` rendrait faux tout le calcul du R")


class TestLeVolumeEstPublie:
    def test_le_nombre_d_unites_part_vers_la_base(self, publieur):
        publieur.publier_ouverture(SignalPublie(
            reference="x:1", pair="BTC/EUR", side="buy",
            entry_price=60000.0, stop_loss=59000.0, volume=0.00123456))
        _, corps = publieur.client.inserts[0]
        assert corps["volume"] == pytest.approx(0.00123456, abs=1e-12), (
            "le volume doit partir SANS arrondi serre : le PEPE se compte "
            "en millions d'unites et le BTC en millionnemes")

    def test_un_volume_absent_ne_cree_pas_de_colonne(self, publieur):
        publieur.publier_ouverture(SignalPublie(
            reference="y:1", pair="BTC/EUR", side="buy",
            entry_price=60000.0, stop_loss=59000.0))
        _, corps = publieur.client.inserts[0]
        assert "volume" not in corps


class TestLaFileNeSeFaitPasNoyerParLesSuivis:
    """Le piege introduit avec le suivi, et son garde-fou."""

    def test_un_suivi_remplace_le_precedent_sur_la_meme_ligne(self, publieur):
        for niveau in (1.0, 1.1, 1.2):
            publieur._empiler({"type": "suivi", "table": "signals",
                               "filtre": "reference=eq.abc:1",
                               "corps": {"stop_loss_actuel": niveau}})
        suivis = [t for t in publieur._file if t["type"] == "suivi"]
        assert len(suivis) == 1, (
            f"{len(suivis)} suivis empiles pour la meme position : la file "
            "va deborder et jeter les ouvertures en attente")
        assert suivis[0]["corps"]["stop_loss_actuel"] == 1.2, (
            "c'est le DERNIER stop qui doit rester, pas le premier")

    def test_deux_positions_differentes_gardent_chacune_le_leur(self, publieur):
        publieur._empiler({"type": "suivi", "table": "signals",
                           "filtre": "reference=eq.abc:1",
                           "corps": {"stop_loss_actuel": 1.0}})
        publieur._empiler({"type": "suivi", "table": "signals",
                           "filtre": "reference=eq.def:1",
                           "corps": {"stop_loss_actuel": 2.0}})
        assert len([t for t in publieur._file if t["type"] == "suivi"]) == 2

    def test_un_suivi_ne_chasse_jamais_une_ouverture(self, publieur):
        """Une ouverture perdue ne se reconstitue pas ; un suivi, si."""
        publieur._empiler({"type": "ouverture", "table": "signals",
                           "corps": {"reference": "abc:1"}})
        for niveau in range(50):
            publieur._empiler({"type": "suivi", "table": "signals",
                               "filtre": "reference=eq.abc:1",
                               "corps": {"stop_loss_actuel": float(niveau)}})
        types = [t["type"] for t in publieur._file]
        assert "ouverture" in types, (
            "l'ouverture a ete chassee de la file par les suivis")
        assert len(publieur._file) == 2, publieur._file
