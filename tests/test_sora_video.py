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
    def test_sora_quand_il_est_explicitement_rearme(self, monkeypatch):
        # AVANT LE 26 SEPTEMBRE, ce test disait « sora des qu'une cle
        # OpenAI existe ». C'etait vrai, et ca ne l'est plus : l'API
        # video de Sora a ferme le 24. L'assertion decrivait un monde
        # revolu, pas un defaut de code — on la corrige, on ne la
        # supprime pas.
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        monkeypatch.setenv("LUNA_SORA_ACTIF", "1")
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
    def test_sans_image_de_depart_lisible_il_echoue(self, monkeypatch, tmp_path):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        monkeypatch.setenv("LUNA_SORA_ACTIF", "1")
        monkeypatch.setenv("LUNA_BUDGET_JOUR_EUR", "100")
        # LE COMPTEUR DE TEST N'EST PAS CELUI DE PRODUCTION. Sans cette
        # ligne, ce test ecrivait dans `data/depenses_luna.json` — 2,40
        # EUR fantomes inscrits le 26 septembre, qui auraient bloque les
        # vraies depenses du jour.
        monkeypatch.setenv("LUNA_DEPENSES_FICHIER", str(tmp_path / "d.json"))
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


class TestUnEchecNeCONSOMMEPasLeBudget:
    """L'argent jamais depense ne doit pas etre compte.

    Ce test existe parce que la premiere version reservait le cout EN
    TETE de `creer`, avant meme de telecharger l'image de depart. Un
    echec a ce stade laissait la depense inscrite : 2,40 EUR fantomes le
    26 septembre, pour zero euro reellement engage.
    """

    def test_une_image_de_depart_illisible_ne_coute_rien(
            self, monkeypatch, tmp_path):
        from luna.budget import Depenses

        compteur = tmp_path / "d.json"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        monkeypatch.setenv("LUNA_SORA_ACTIF", "1")
        monkeypatch.setenv("LUNA_BUDGET_JOUR_EUR", "100")
        monkeypatch.setenv("LUNA_DEPENSES_FICHIER", str(compteur))

        with pytest.raises(MediaErreur, match="image de depart"):
            SoraVideo().creer("https://exemple.invalide/rien.png",
                              "elle marche", "9:16", 8)

        assert Depenses().total_du_jour() == 0.0, \
            "un echec avant l'appel a l'API ne doit rien consommer"


class TestSoraEstFermeDepuisLe24Septembre:
    """OpenAI l'annonce lui-meme : `shutdown_date: 2026-09-24`.

    Le piege etait que `sora-2` et `sora-2-pro` restent listes dans
    `/v1/models` alors que `/v1/videos` rend 404. Un catalogue qui liste
    un modele ne prouve pas que le service existe.
    """

    def test_la_fabrique_ne_choisit_PAS_sora_par_defaut(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        monkeypatch.setenv("RUNWAYML_API_SECRET", "rw-vraie")
        monkeypatch.delenv("LUNA_SORA_ACTIF", raising=False)
        assert fournisseur_video().nom == "runway", (
            "sans ce verrou, chaque video echouerait en 404 alors que "
            "Runway attend a cote, configure et fonctionnel")

    def test_on_peut_le_rearmer_le_jour_du_successeur(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        monkeypatch.setenv("LUNA_SORA_ACTIF", "1")
        assert fournisseur_video().nom == "sora"

    def test_la_date_de_fermeture_est_ecrite_dans_le_code(self):
        # Pour que personne ne le rebranche en croyant l'avoir invente.
        assert SoraVideo.FERME_LE == "2026-09-24"


class TestUn404NeCoutePasLePlafondDuJour:
    def test_un_refus_http_rend_la_reservation(self, monkeypatch, tmp_path):
        from luna.budget import Depenses

        compteur = tmp_path / "d.json"
        monkeypatch.setenv("OPENAI_API_KEY", "sk-vraie")
        monkeypatch.setenv("LUNA_SORA_ACTIF", "1")
        monkeypatch.setenv("LUNA_BUDGET_JOUR_EUR", "10")
        monkeypatch.setenv("LUNA_DEPENSES_FICHIER", str(compteur))
        monkeypatch.setenv("LUNA_COUT_VIDEO_SECONDE_EUR", "0.10")

        sora = SoraVideo()
        monkeypatch.setattr(sora, "_multipart", lambda *a, **k: (_ for _ in ()).throw(
            MediaErreur("Sora HTTP 404: ")))
        # L'image de depart doit passer : on la court-circuite.
        monkeypatch.setattr("urllib.request.urlopen",
                            lambda *a, **k: _FauxFlux())

        with pytest.raises(MediaErreur, match="404"):
            sora.creer("https://exemple/x.png", "elle marche", "9:16", 4)

        assert Depenses().total_du_jour() == 0.0, (
            "un endpoint ferme n'a rien produit, donc rien ne doit etre "
            "compte — sinon quelques 404 vident le plafond du jour")


class _FauxFlux:
    def read(self):
        return b"\x89PNG fausse image"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
