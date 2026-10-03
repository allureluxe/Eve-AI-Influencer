"""Le robot KIT de @alluxe.ia : commenter KIT -> le kit part en privé.

Ce qui est verrouillé ici :
  - le mot KIT déclenche, pas un mot qui le contient ;
  - le robot ne se répond jamais à lui-même, ne devine pas une réponse
    floue, et respecte les deux fenêtres de Meta (7 jours, 24 h) ;
  - rien ne part sans --confirmer, et une erreur ne marque pas
    l'évènement comme traité (il sera retenté).
"""
from __future__ import annotations

import datetime as dt

from helpers import *  # noqa: F401,F403

from alluxe_ia.kit import decider, demande_kit, profil

LIEN = "https://exemple.test/kit"
MAINTENANT = dt.datetime(2026, 10, 3, 12, tzinfo=dt.timezone.utc)


def _com(texte="KIT", ident="C1", il_y_a=dt.timedelta(0)):
    return {"id": 1, "type": "commentaire", "ident": ident, "ig_user_id": "U1",
            "username": "lea", "texte": texte, "recu_at": (MAINTENANT - il_y_a).isoformat()}


def _msg(texte, il_y_a=dt.timedelta(0)):
    return {"id": 2, "type": "message", "ident": "m1", "ig_user_id": "U1",
            "texte": texte, "recu_at": (MAINTENANT - il_y_a).isoformat()}


class TestLeMotCle:
    def test_kit_seul_ou_dans_une_phrase(self):
        for t in ("KIT", "kit", "Kit 🙏", "je veux le kit !", "KIT."):
            assert demande_kit(t), t

    def test_pas_un_mot_qui_le_contient(self):
        for t in ("kitchen", "skit", "kits", "", None, "super post"):
            assert not demande_kit(t), t


class TestLaSequence:
    def test_kit_reponse_publique_puis_privee_avec_le_lien(self):
        d = decider(_com(), None, MAINTENANT, LIEN)
        assert [a.genre for a in d.actions] == ["reponse_publique", "reponse_privee"]
        assert all(a.cible == "C1" for a in d.actions)
        assert LIEN in d.actions[1].texte
        assert d.contact["etape"] == 1

    def test_un_commentaire_sans_kit_ne_declenche_rien(self):
        assert decider(_com("super post"), None, MAINTENANT, LIEN).actions == []

    def test_un_commentaire_de_plus_de_6_jours_est_laisse(self):
        d = decider(_com(il_y_a=dt.timedelta(days=7)), None, MAINTENANT, LIEN)
        assert d.actions == []

    def test_la_reponse_qualifie_puis_on_s_arrete(self):
        d = decider(_msg("je pars de zéro"), {"etape": 1}, MAINTENANT, LIEN)
        assert d.contact["profil"] == "zero" and d.contact["etape"] == 2
        assert len(d.actions) == 1 and d.actions[0].genre == "message"
        d = decider(_msg("j'ai déjà commencé"), {"etape": 1}, MAINTENANT, LIEN)
        assert d.contact["profil"] == "commence"

    def test_une_reponse_floue_va_a_un_humain(self):
        d = decider(_msg("c'est quoi ton appli ?"), {"etape": 1}, MAINTENANT, LIEN)
        assert d.actions == [] and "humain" in d.resultat

    def test_l_offre_ne_part_qu_avec_un_lien_et_porte_publicite(self):
        sans = decider(_msg("une appli"), {"etape": 2}, MAINTENANT, LIEN)
        assert sans.actions == []
        avec = decider(_msg("une appli"), {"etape": 2}, MAINTENANT, LIEN, "https://p.test")
        assert "Publicité" in avec.actions[0].texte and avec.contact["etape"] == 3
        assert decider(_msg("merci"), {"etape": 3}, MAINTENANT, LIEN, "https://p.test").actions == []

    def test_hors_fenetre_de_24_h_on_n_ecrit_plus(self):
        d = decider(_msg("zéro", il_y_a=dt.timedelta(hours=25)), {"etape": 1}, MAINTENANT, LIEN)
        assert d.actions == []

    def test_un_inconnu_qui_ecrit_n_est_pas_traite_par_le_robot(self):
        assert decider(_msg("salut"), None, MAINTENANT, LIEN).actions == []

    def test_profil(self):
        assert profil("ZERO") == "zero"
        assert profil("débutant total") == "zero"
        assert profil("déjà une appli en cours") == "commence"
        assert profil("bof") is None


class TestRienNePartSansConfirmation:
    def _faux_rest(self, evenements):
        class Faux:
            marques: list = []
            contacts: list = []
            def a_traiter(self): return evenements
            def contact(self, _): return None
            def maj_contact(self, u, c): self.contacts.append((u, c))
            def marquer(self, i, c): self.marques.append((i, c))
        return Faux()

    def test_essai_a_blanc(self, monkeypatch):
        import ops.alluxe_ia_kit as k
        rest = self._faux_rest([_com()])
        monkeypatch.setattr(k, "Rest", lambda: rest)
        monkeypatch.setattr(k, "executer", lambda a: (_ for _ in ()).throw(AssertionError("envoi")))
        monkeypatch.setenv("ALLUXE_IA_KIT_URL", LIEN)
        assert k.traiter(confirmer=False) == 0
        assert rest.marques == [] and rest.contacts == []

    def test_sans_lien_rien_ne_part(self, monkeypatch):
        import ops.alluxe_ia_kit as k
        monkeypatch.delenv("ALLUXE_IA_KIT_URL", raising=False)
        assert k.traiter(confirmer=True) == 1

    def test_une_erreur_laisse_l_evenement_a_retenter(self, monkeypatch):
        import ops.alluxe_ia_kit as k
        rest = self._faux_rest([_com()])
        monkeypatch.setattr(k, "Rest", lambda: rest)
        def panne(a): raise RuntimeError("HTTP 500")
        monkeypatch.setattr(k, "executer", panne)
        monkeypatch.setenv("ALLUXE_IA_KIT_URL", LIEN)
        k.traiter(confirmer=True)
        (_, champs), = rest.marques
        assert "traite_at" not in champs and champs["tentatives"] == 1
        assert rest.contacts == []

    def test_envoi_reussi_marque_et_retient_la_personne(self, monkeypatch):
        import ops.alluxe_ia_kit as k
        rest = self._faux_rest([_com()])
        envoyes = []
        monkeypatch.setattr(k, "Rest", lambda: rest)
        monkeypatch.setattr(k, "executer", envoyes.append)
        monkeypatch.setenv("ALLUXE_IA_KIT_URL", LIEN)
        k.traiter(confirmer=True)
        assert len(envoyes) == 2
        assert rest.marques[0][1]["resultat"] == "kit envoyé"
        assert rest.contacts[0][1]["etape"] == 1


class TestLeReleveEtLeRepli:
    """3 oct. : Meta n'envoyait aucun commentaire au webhook (application en
    mode Développement). Le robot lit donc lui-même les commentaires, et si
    Meta refuse le message privé, il renvoie au lien de la bio au lieu de
    prétendre avoir écrit."""

    def test_le_releve_ecarte_le_compte_lui_meme(self):
        from alluxe_ia.kit import commentaires_releves
        lus = {"M1": [
            {"id": "C1", "text": "KIT", "username": "lea", "from": {"id": "U1", "username": "lea"},
             "timestamp": "2026-10-03T20:00:00+0000"},
            {"id": "C2", "text": "Envoyé en privé 👀", "username": "alluxe.ia",
             "from": {"id": "MOI", "username": "alluxe.ia"}},
            {"id": "C3", "text": "KIT", "username": "anonyme"},   # sans auteur : inutilisable
        ]}
        evs = commentaires_releves(lus, "MOI", "alluxe.ia")
        assert [(e["ident"], e["ig_user_id"], e["media_id"]) for e in evs] == [("C1", "U1", "M1")]
        assert evs[0]["recu_at"].startswith("2026-10-03")

    def test_message_prive_d_abord_puis_reponse_publique(self, monkeypatch):
        import ops.alluxe_ia_kit as k
        from alluxe_ia.kit import decider
        ordre = []
        monkeypatch.setattr(k, "executer", lambda a: ordre.append(a.genre))
        d = decider(_com(), None, MAINTENANT, LIEN)
        assert k.envoyer(d.actions) == ""
        assert ordre == ["reponse_privee", "reponse_publique"]

    def test_refus_de_meta_renvoie_a_la_bio_sans_mentir(self, monkeypatch):
        import ops.alluxe_ia_kit as k
        from alluxe_ia.kit import REPONSE_BIO, decider
        publiques = []

        def faux(a):
            if a.genre == "reponse_privee":
                raise RuntimeError("HTTP 400 sur X/messages : (#10) not allowed")
            publiques.append(a.texte)

        monkeypatch.setattr(k, "executer", faux)
        note = k.envoyer(decider(_com(), None, MAINTENANT, LIEN).actions)
        assert publiques == [REPONSE_BIO] and "repli bio" in note

    def test_une_panne_passagere_se_retente(self, monkeypatch):
        import ops.alluxe_ia_kit as k
        from alluxe_ia.kit import decider

        def panne(a):
            raise RuntimeError("HTTP 500 sur X/messages : erreur serveur")

        monkeypatch.setattr(k, "executer", panne)
        import pytest
        with pytest.raises(RuntimeError):
            k.envoyer(decider(_com(), None, MAINTENANT, LIEN).actions)
