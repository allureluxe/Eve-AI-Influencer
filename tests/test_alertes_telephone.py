"""Ce qui arrive sur le telephone de l'operateur, et ce qui n'y arrive pas.

Decision de l'operateur, 10 septembre 2026, mot pour mot : « qu'il
m'envoie des alertes uniquement quand le bot prend une position et quand
il la ferme, quand le robot s'arrete et quand il y a un probleme, mais
pas a chaque fois qu'un ordre est refuse ».

POURQUOI C'EST UNE QUESTION DE SECURITE, ET PAS DE CONFORT.

Un refus de courtier est ordinaire et se reproduit a chaque cycle tant
que sa cause dure. Dix messages en une minute apprennent a ignorer les
alertes — or la seule qui compte vraiment, le chien de garde, arrive par
le meme canal. Noyer les alertes, c'est les desarmer.

Rien n'est perdu : tout reste dans `data/journal.jsonl` (canal fichier,
niveau debug) et dans la console. Seul le telephone filtre.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.notifiers import Notification, TelegramChannel


class _Espion(TelegramChannel):
    """Un canal Telegram qui note au lieu d'envoyer."""

    def __init__(self):
        super().__init__()
        self.token, self.chat_id = "jeton", "42"
        self.envoyes: list[str] = []

    def _poster(self, note):                      # pragma: no cover
        self.envoyes.append(note.title)

    def send(self, note):
        if note.data.get("telephone") is False:
            return
        self.envoyes.append(note.title)


def _passe(niveau: str, titre: str, data=None) -> bool:
    canal = _Espion()
    note = Notification(level=niveau, title=titre, body="", data=data or {})
    if not canal.accepts(note.level):
        return False
    canal.send(note)
    return bool(canal.envoyes)


class TestCeQueLOperateurVeutRecevoir:
    """Les quatre cas demandes doivent passer."""

    def test_une_position_ouverte_arrive(self):
        assert _passe("trade", "Position ouverte — BUY ETHFIUSD")

    def test_une_position_fermee_arrive(self):
        # Un gain part en « trade », une perte en « warning » : les deux
        # doivent arriver, c'est le meme evenement vu de deux cotes.
        assert _passe("trade", "Gain +2.84 EUR — NEARUSD")
        assert _passe("warning", "Perte -1.77 EUR — BNBUSD")

    def test_l_arret_du_robot_arrive(self):
        assert _passe("critical", "Robot en securite")
        assert _passe("warning", "Trading suspendu")

    def test_un_vrai_probleme_arrive(self):
        assert _passe("critical", "Connexion au broker impossible")
        assert _passe("critical", "Demarrage refuse")
        assert _passe("warning", "Capital insuffisant pour cette plateforme")
        assert _passe("warning", "Positions plus petites que voulu")
        assert _passe("warning", "Cycle en echec")


class TestCeQuiNeDoitPasSonner:
    """Le bruit reste au journal."""

    def test_un_ordre_refuse_ne_sonne_pas(self):
        assert not _passe("warning", "Ordre refuse — SAGAUSD",
                          {"telephone": False})

    def test_un_stop_refuse_ne_sonne_pas(self):
        assert not _passe("warning", "Action refusee — KAVAUSD",
                          {"telephone": False})

    def test_la_banniere_de_demarrage_ne_sonne_pas(self):
        """Une par redemarrage. Cinq le 10 septembre, toutes identiques."""
        assert not _passe("warning", "Bitvavo en mode REEL",
                          {"telephone": False})

    def test_un_objectif_repousse_ne_sonne_pas(self):
        """Ni une ouverture ni une fermeture : la position ne bouge pas."""
        assert not _passe("trade", "Objectif repousse — KAVAUSD",
                          {"telephone": False})

    def test_les_scans_de_routine_ne_sonnent_pas(self):
        """Le niveau « info » reste sous le seuil du canal."""
        assert not _passe("info", "Robot demarre")
        assert not _passe("info", "Robot actif")
        assert not _passe("debug", "Trade non dimensionnable — ETHFIUSD")


class TestLeMarqueurNeSilencePasLeJournal:
    """`telephone: False` ne doit museler QUE le telephone.

    Si le marqueur remontait dans `Notifier.send` ou dans `accepts`, il
    effacerait l'evenement du journal ET de la console. Or c'est la que
    l'on retrouve la cause d'une panne : le 10 septembre, ce sont les
    refus « budget de place insuffisant » qui ont permis de remonter au
    vrai defaut.
    """

    def test_le_canal_fichier_recoit_tout(self, tmp_path):
        from gold_bot.notifiers import FileChannel, Notifier

        chemin = tmp_path / "journal.jsonl"
        fichier = FileChannel(path=str(chemin))
        n = Notifier([fichier])
        n.notify("warning", "Ordre refuse — SAGAUSD", "raison",
                 data={"telephone": False})
        contenu = chemin.read_text()
        assert "Ordre refuse" in contenu, (
            "le marqueur telephone a efface l'evenement du JOURNAL : on ne "
            "pourra plus diagnostiquer une panne")

    def test_le_niveau_de_gravite_reste_vrai(self):
        """Un refus reste un `warning`, il n'est simplement pas destine ici.

        L'alternative — descendre ces evenements en « info » — aurait
        aussi marche pour le telephone, mais elle aurait menti sur leur
        gravite dans journalctl.
        """
        from gold_bot.notifiers import LEVEL_ORDER

        assert LEVEL_ORDER["warning"] > LEVEL_ORDER["info"]
        canal = _Espion()
        assert canal.accepts("warning"), (
            "le canal refuse desormais les warnings : les vrais problemes "
            "n'arriveraient plus")
