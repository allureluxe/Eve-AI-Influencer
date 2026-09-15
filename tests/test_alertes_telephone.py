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

from gold_bot.notifiers import AlluxeBotChannel, Notification, TelegramChannel


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


class _EspionAlluxe(AlluxeBotChannel):
    """Meme principe pour Alluxe Bot -- remplace Telegram, meme discipline
    (decision de l'operateur, 15 sept. 2026)."""

    def __init__(self):
        super().__init__()
        self.url, self.cle = "https://x", "cle"
        self.envoyes: list[str] = []

    def send(self, note):
        if note.data.get("telephone") is False:
            return
        self.envoyes.append(note.title)


def _passe(niveau: str, titre: str, data=None, classe_canal=_Espion) -> bool:
    canal = classe_canal()
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

    def test_le_demarrage_et_l_arret_normaux_arrivent(self):
        """15 sept. 2026, demande explicite : "je veux une notif quand le
        robot s'arrete et quand le robot demarre". Ces deux evenements
        (gold_bot/engine.py: start()/shutdown()) sont passes de "info" a
        "warning" ce jour-la -- "info" ne sonnait jamais (voir
        TestCeQuiNeDoitPasSonner)."""
        assert _passe("warning", "Robot demarre")
        assert _passe("warning", "Robot arrete")

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
        assert not _passe("info", "Robot actif")
        assert not _passe("info", "Cycle termine")
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


class TestAlluxeBotSuitLaMemeDiscipline:
    """15 sept. 2026 : Alluxe Bot remplace Telegram -- meme seuil
    (`trade`), meme garde-fou `telephone: False`. Pas d'exhaustivite ici
    (deja verifiee sur Telegram ci-dessus), juste la preuve que le meme
    comportement s'applique au nouveau canal."""

    def test_une_position_ouverte_arrive(self):
        assert _passe("trade", "Position ouverte — BUY ETHFIUSD",
                      classe_canal=_EspionAlluxe)

    def test_un_ordre_refuse_ne_sonne_pas(self):
        assert not _passe("warning", "Ordre refuse — SAGAUSD",
                          {"telephone": False}, classe_canal=_EspionAlluxe)

    def test_les_scans_de_routine_ne_sonnent_pas(self):
        assert not _passe("info", "Robot actif", classe_canal=_EspionAlluxe)

    def test_le_demarrage_et_l_arret_normaux_arrivent(self):
        assert _passe("warning", "Robot demarre", classe_canal=_EspionAlluxe)
        assert _passe("warning", "Robot arrete", classe_canal=_EspionAlluxe)

    def test_enabled_exige_url_et_cle(self):
        canal = AlluxeBotChannel()
        canal.url, canal.cle = "", ""
        assert not canal.enabled()
        canal.url, canal.cle = "https://x", "cle"
        assert canal.enabled()

    def test_send_poste_sur_la_table_alertes(self, monkeypatch):
        appels = []

        def _http_json_factice(url, method="POST", payload=None, headers=None, timeout=10.0):
            appels.append((url, method, payload, headers))
            return {}

        import gold_bot.notifiers as notifiers
        monkeypatch.setattr(notifiers, "http_json", _http_json_factice)

        canal = AlluxeBotChannel()
        canal.url, canal.cle = "https://exemple.supabase.co", "secret"
        note = Notification(level="trade", title="Position ouverte", body="detail")
        canal.send(note)

        assert len(appels) == 1
        url, methode, payload, entetes = appels[0]
        assert url == "https://exemple.supabase.co/rest/v1/alluxe_bot_alertes"
        assert methode == "POST"
        assert payload["titre"] == "Position ouverte"
        assert payload["niveau"] == "trade"
        assert entetes["apikey"] == "secret"

    def test_send_ne_poste_pas_si_telephone_est_faux(self, monkeypatch):
        appels = []
        import gold_bot.notifiers as notifiers
        monkeypatch.setattr(notifiers, "http_json", lambda *a, **k: appels.append(1))

        canal = AlluxeBotChannel()
        canal.url, canal.cle = "https://exemple.supabase.co", "secret"
        note = Notification(level="warning", title="Ordre refuse",
                            data={"telephone": False})
        canal.send(note)

        assert appels == []


class TestFirebasePushSuitLaMemeDiscipline:
    """15 sept. 2026 : vraie notification push (achat/vente/robot
    suspendu), demande explicite de l'operateur -- pas juste un onglet a
    ouvrir. Meme seuil (`trade`) et meme garde-fou `telephone: False`."""

    def _canal(self, tmp_path):
        from gold_bot.notifiers import FirebasePushChannel

        fichier = tmp_path / "cle.json"
        fichier.write_text('{"client_email": "x@y.iam.gserviceaccount.com", '
                           '"private_key": "factice", "project_id": "allure-bot-d5a4c"}')
        canal = FirebasePushChannel()
        canal.fichier_cle = str(fichier)
        canal.url_supabase = "https://exemple.supabase.co"
        canal.cle_supabase = "secret"
        return canal

    def test_enabled_exige_le_fichier_et_les_identifiants_supabase(self, tmp_path):
        canal = self._canal(tmp_path)
        assert canal.enabled()
        canal.fichier_cle = str(tmp_path / "absent.json")
        assert not canal.enabled()

    def test_un_ordre_refuse_ne_declenche_aucun_appel_reseau(self, tmp_path, monkeypatch):
        """Le garde-fou doit agir AVANT toute tentative d'authentification --
        sinon chaque refus de courtier signerait un JWT pour rien."""
        canal = self._canal(tmp_path)
        appele = []
        monkeypatch.setattr(canal, "_jeton_appareil", lambda: appele.append(1))
        monkeypatch.setattr(canal, "_jeton_oauth", lambda: appele.append(1))

        note = Notification(level="warning", title="Ordre refuse",
                            data={"telephone": False})
        canal.send(note)

        assert appele == []

    def test_sans_jeton_d_appareil_enregistre_rien_n_est_envoye(self, tmp_path, monkeypatch):
        canal = self._canal(tmp_path)
        monkeypatch.setattr(canal, "_jeton_appareil", lambda: "")
        appels = []
        import gold_bot.notifiers as notifiers
        monkeypatch.setattr(notifiers, "http_json", lambda *a, **k: appels.append(1))

        canal.send(Notification(level="trade", title="Position ouverte"))

        assert appels == []

    def test_send_poste_le_bon_message_a_fcm(self, tmp_path, monkeypatch):
        canal = self._canal(tmp_path)
        monkeypatch.setattr(canal, "_jeton_appareil", lambda: "jeton-appareil")
        monkeypatch.setattr(canal, "_jeton_oauth", lambda: "jeton-oauth")

        appels = []

        def _http_json_factice(url, method="POST", payload=None, headers=None, timeout=10.0):
            appels.append((url, method, payload, headers))
            return {}

        import gold_bot.notifiers as notifiers
        monkeypatch.setattr(notifiers, "http_json", _http_json_factice)

        note = Notification(level="trade", title="Position ouverte — BUY ETHFIUSD",
                            body="Entree a 2450 EUR")
        canal.send(note)

        assert len(appels) == 1
        url, methode, payload, entetes = appels[0]
        assert url == "https://fcm.googleapis.com/v1/projects/allure-bot-d5a4c/messages:send"
        assert methode == "POST"
        assert payload["message"]["token"] == "jeton-appareil"
        assert payload["message"]["notification"]["title"] == "Position ouverte — BUY ETHFIUSD"
        assert payload["message"]["notification"]["body"] == "Entree a 2450 EUR"
        assert entetes["Authorization"] == "Bearer jeton-oauth"
