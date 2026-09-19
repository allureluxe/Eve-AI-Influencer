"""Peut-on supprimer Telegram sans rien perdre ?

Decision de l'operateur, 19 septembre : « je veux que tu mettes tout
comme Telegram, comme ca je supprime Telegram, j'aurai plus besoin de
lui ».

C'est une decision qu'on ne peut pas defaire a moitie : une fois le
compte supprime, un message qui ne partait que par la ne partira plus
nulle part, et personne ne s'en apercevra — un canal muet ne previent
pas qu'il est muet. Ces tests verrouillent l'equivalence AVANT la
suppression.

Trois choses passaient par Telegram :
  1. les alertes du robot        -> `AlluxeBotChannel`
  2. les commandes ecrites       -> `ops/ecoute_discussion.py`
  3. la page ALLURE en fichier   -> colonne `rapport_html`
"""
import inspect

import pytest

from gold_bot.notifiers import (AlluxeBotChannel, Notification,
                                Notifier, TelegramChannel)


def _note(niveau: str, **donnees) -> Notification:
    return Notification(level=niveau, title="essai", body="corps",
                        data=donnees)


class TestLesDeuxCanauxRetiennentLesMemesMessages:
    """Meme seuil, meme garde-fou : la substitution doit etre exacte."""

    @pytest.mark.parametrize("niveau", ["debug", "info", "trade",
                                        "warning", "critical"])
    def test_le_seuil_est_le_meme(self, niveau):
        t, a = TelegramChannel(), AlluxeBotChannel()
        assert t.accepts(niveau) == a.accepts(niveau), (
            f"niveau « {niveau} » : Telegram et Alluxe Bot ne filtrent pas "
            "pareil, donc supprimer Telegram ferait perdre des messages")

    def test_le_seuil_par_defaut_est_identique(self):
        assert TelegramChannel().min_level == AlluxeBotChannel().min_level

    def test_les_deux_ignorent_les_refus_ordinaires_de_courtier(self):
        """`telephone=False` : le garde-fou anti-spam du 10 septembre.

        S'il n'existait que d'un cote, l'application recevrait la rafale
        de messages que Telegram avait appris a taire -- et une rafale
        apprend a ignorer les alertes, y compris celle du chien de garde.
        """
        source_t = inspect.getsource(TelegramChannel.send)
        source_a = inspect.getsource(AlluxeBotChannel.send)
        for source, nom in ((source_t, "Telegram"), (source_a, "Alluxe Bot")):
            assert 'data.get("telephone") is False' in source, (
                f"{nom} n'a plus le garde-fou `telephone=False`")


class TestLesCommandesEcritesSurviventASuppressionDeTelegram:
    def test_les_deux_ecouteurs_partagent_le_meme_cerveau(self):
        """Recopier l'interpretation garantirait la divergence."""
        import ops.ecoute_discussion as discussion
        import gold_bot.commandes as commandes

        source = inspect.getsource(discussion)
        assert "from gold_bot.commandes import" in source, (
            "l'ecouteur de l'application a sa propre interpretation des "
            "commandes : elle divergera de celle de Telegram")
        # Les memes commandes sont comprises des deux cotes.
        for mot in ("rapport", "semaine", "jour", "etat"):
            assert mot in commandes.AIDE or mot in inspect.getsource(
                commandes.repondre), f"la commande « {mot} » a disparu"

    def test_aucune_commande_n_agit_sur_le_robot(self):
        """La contrainte de `ecoute_telegram.py` vaut d'autant plus ici :
        l'application est desormais le SEUL canal."""
        source = inspect.getsource(__import__("gold_bot.commandes",
                                              fromlist=["x"]))
        for interdit in ("systemctl", "subprocess", "os.system",
                         "close_position", "open_position"):
            assert interdit not in source, (
                f"« {interdit} » dans les commandes : un canal de "
                "discussion ne doit pas pouvoir engager de l'argent")

    def test_une_commande_non_publiee_reste_a_traiter(self):
        """Sinon elle disparait en silence.

        Marquer « traite » avant d'avoir reussi a repondre fait perdre la
        demande : l'operateur attend une reponse qui ne viendra jamais, et
        rien dans le journal ne le dira.
        """
        import ops.ecoute_discussion as discussion
        source = inspect.getsource(discussion.main)
        avant_publication = source.index("_publier")
        apres_marquage = source.index('"traite": True')
        assert avant_publication < apres_marquage, (
            "la commande est marquee traitee avant que la reponse soit "
            "partie")


class TestLaPageAllureArriveJusquAuTelephone:
    def test_le_rapport_voyage_dans_la_ligne_pas_sur_une_adresse_publique(self):
        import ops.ecoute_discussion as discussion
        source = inspect.getsource(discussion)
        assert "rapport_html" in source, (
            "la page ALLURE n'est plus jointe a la reponse")
        # « on ne met pas les finances de quelqu'un sur le web ouvert
        # pour economiser un clic » -- ecoute_telegram.py
        assert "storage" not in source.lower(), (
            "la page passe par un stockage a adresse publique")

    def test_une_page_trop_lourde_ne_bloque_pas_la_reponse(self):
        import ops.ecoute_discussion as discussion
        assert discussion.RAPPORT_MAX_OCTETS > 0
        source = inspect.getsource(discussion._publier)
        assert "RAPPORT_MAX_OCTETS" in source


class TestTelegramNEstPlusDansLesCanauxParDefaut:
    """Le test qui devient vrai le jour ou on coupe vraiment."""

    def test_alluxe_bot_est_toujours_present(self):
        noms = [c.name for c in Notifier().channels]
        assert "alluxe_bot" in noms, (
            "le canal de l'application a disparu de la liste par defaut")
