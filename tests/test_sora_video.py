"""Sora, et surtout LA FABRIQUE qui evite deux chemins video.

Le risque principal de ce branchement n'est pas l'API d'OpenAI : c'est
que le worker soumette une tache chez un fournisseur et la relise chez
l'autre. La video resterait alors « en cours » pour toujours, sans le
moindre message — exactement le mode de panne que ce depot a deja
rencontre cinq fois sous d'autres formes.
"""
from __future__ import annotations

import pytest

from luna.media import MediaErreur, RunwayVideo, SoraVideo, fournisseur_video


class TestLaFabriqueChoisitUnSeulFournisseur:
    def test_sora_des_qu_une_cle_openai_existe(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        assert fournisseur_video().nom == "sora"

    def test_runway_en_repli_sans_cle_openai(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert fournisseur_video().nom == "runway"

    def test_un_your_non_remplace_ne_compte_pas(self, monkeypatch):
        # Convention de ce depot : les `.env.example` portent des
        # « your_openai_api_key » que personne ne remplace. Les prendre
        # pour des cles donne un 401 la ou un fournisseur gratuit
        # fonctionnait — deja vu le 15 septembre sur Stability.
        monkeypatch.setenv("OPENAI_API_KEY", "your_openai_api_key")
        assert fournisseur_video().nom == "runway"

    def test_les_deux_repondent_a_la_meme_interface(self):
        # C'est ce qui permet au worker de n'avoir qu'un seul chemin.
        for classe in (SoraVideo, RunwayVideo):
            for methode in ("creer", "resultat", "entetes_telechargement"):
                assert callable(getattr(classe, methode, None)), \
                    f"{classe.__name__} n'expose pas {methode}"
            assert getattr(classe, "nom", "")


class TestSoraTraduitVersCeQuIlAccepte:
    def test_il_n_a_que_deux_resolutions(self):
        assert SoraVideo._taille("9:16") == "720x1280"
        assert SoraVideo._taille("16:9") == "1280x720"
        # Tout le reste retombe sur le vertical : c'est le format des
        # Reels et de TikTok, donc le defaut utile.
        assert SoraVideo._taille("3:4") == "720x1280"
        assert SoraVideo._taille("") == "720x1280"

    def test_la_duree_s_arrondit_aux_seules_permises(self):
        # 4, 8 ou 12 — une autre valeur donne un 400 chez OpenAI.
        assert SoraVideo._duree(3) == "4"
        assert SoraVideo._duree(10) == "8"
        assert SoraVideo._duree(12) == "12"
        assert SoraVideo._duree(30) == "12"
        assert SoraVideo._duree(0) == "8"


class TestLeTelechargementPorteLaCle:
    def test_sora_exige_l_autorisation_runway_non(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        # Sora rend un identifiant, et le fichier vit derriere la cle.
        assert "Authorization" in SoraVideo().entetes_telechargement()
        # Runway rend un lien signe : rien a ajouter.
        assert RunwayVideo().entetes_telechargement() == {}


class TestIlRefusePlutotQueDeProduireUneInconnue:
    def test_sans_image_de_depart_lisible_il_echoue(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        monkeypatch.setenv("LUNA_BUDGET_JOUR_EUR", "100")
        # TOUT L'INTERET DE SORA EST L'IMAGE DE DEPART : c'est elle qui
        # tient le visage de Luna. Continuer sans elle produirait une
        # video d'une femme qui n'est pas elle — pire qu'une erreur,
        # parce que ca se publie.
        with pytest.raises(MediaErreur, match="image de depart"):
            SoraVideo().creer("https://exemple.invalide/rien.png",
                              "elle marche", "9:16", 8)

    def test_sans_cle_il_le_dit(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(MediaErreur, match="OPENAI_API_KEY"):
            SoraVideo().creer("", "elle marche", "9:16", 8)
