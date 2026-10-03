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
