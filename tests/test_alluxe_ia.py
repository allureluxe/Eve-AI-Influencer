"""alluxe.ia : le compte Instagram de Luna repris en page d'IA pratique
(decision de l'operateur du 2 oct. 2026).

Trois garanties :
  - chaque post de alluxe_ia/posts.json se rend en slides 1080 x 1350 ;
  - un carrousel se publie en trois temps (enfants, parent, publication) ;
  - RIEN ne part sur Instagram sans --confirmer, et un post deja publie
    n'est jamais reposte.
"""
from __future__ import annotations

import json
import os

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

pytest.importorskip("PIL")

from alluxe_ia.slides import HAUTEUR, LARGEUR, Post, couper, rendre, titre_police  # noqa: E402

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _posts() -> list[Post]:
    with open(os.path.join(RACINE, "alluxe_ia", "posts.json"), encoding="utf-8") as f:
        return [Post.depuis(p) for p in json.load(f)]


class TestLesPostsSeRendent:

    def test_chaque_post_donne_des_slides_au_bon_format(self):
        for post in _posts():
            images = rendre(post)
            assert 2 <= len(images) <= 10, f"{post.id} : {len(images)} slides"
            for img in images:
                assert img.size == (LARGEUR, HAUTEUR)

    def test_chaque_post_finit_par_un_mot_cle(self):
        for post in _posts():
            assert post.slides[-1].type == "appel" and post.slides[-1].mot_cle, post.id

    def test_les_identifiants_sont_uniques(self):
        ids = [p.id for p in _posts()]
        assert len(ids) == len(set(ids))

    def test_la_ponctuation_ne_commence_jamais_une_ligne(self):
        lignes = couper("Produis une fiche avec exactement ces rubriques : 1. une "
                        "phrase « fais-moi un résumé » ici", titre_police(60), 500)
        for ligne in lignes:
            assert not ligne.startswith((":", "»", "?", "!", ";")), lignes
            assert not ligne.endswith("«"), lignes


class TestLeCarrousel:

    def test_trois_temps_et_legende_sur_le_parent_seulement(self, monkeypatch):
        import ops.instagram as ig
        appels = []

        def faux(methode, chemin, **params):
            appels.append((methode, chemin, params))
            if methode == "GET":
                return {"status_code": "FINISHED"}
            if chemin.endswith("/media_publish"):
                return {"id": "POST"}
            return {"id": f"C{len(appels)}"}

        monkeypatch.setattr(ig, "_appel", faux)
        monkeypatch.setattr(ig, "_compte", lambda: "ME")
        urls = [f"https://x.test/{i}.jpg" for i in range(3)]
        assert ig.publier_carrousel(urls, "ma legende") == "POST"

        posts = [a for a in appels if a[0] == "POST"]
        enfants = [a for a in posts if a[2].get("is_carousel_item") == "true"]
        parent = [a for a in posts if a[2].get("media_type") == "CAROUSEL"]
        assert len(enfants) == 3
        assert all("caption" not in a[2] for a in enfants)
        assert len(parent) == 1 and parent[0][2]["caption"] == "ma legende"
        assert parent[0][2]["children"].count(",") == 2
        assert posts[-1][1] == "ME/media_publish"

    def test_refuse_une_image_seule_ou_privee(self):
        import ops.instagram as ig
        with pytest.raises(ig.InstagramErreur):
            ig.publier_carrousel(["https://x.test/1.jpg"])
        with pytest.raises(ig.InstagramErreur):
            ig.publier_carrousel(["https://x.test/1.jpg", "http://x.test/2.jpg"])


class TestRienNePartSansConfirmation:

    def _module(self, monkeypatch, tmp_path):
        import ops.alluxe_ia as a
        monkeypatch.setattr(a, "SORTIE", str(tmp_path))
        monkeypatch.setattr(a, "JOURNAL", str(tmp_path / "publies.json"))
        return a

    def test_l_essai_a_blanc_ne_touche_pas_a_instagram(self, monkeypatch, tmp_path):
        a = self._module(monkeypatch, tmp_path)
        import ops.instagram as ig

        def interdit(*_, **__):
            raise AssertionError("Instagram appele pendant un essai a blanc")

        monkeypatch.setattr(ig, "publier_carrousel", interdit)
        monkeypatch.setattr(a, "televerser", interdit)
        a.publier_post(_posts()[0], confirmer=False)
        assert (tmp_path / _posts()[0].id / "01.jpg").exists()

    def test_un_post_publie_n_est_jamais_reposte(self, monkeypatch, tmp_path):
        a = self._module(monkeypatch, tmp_path)
        post = _posts()[0]
        a.noter_publication(post.id, "123")
        with pytest.raises(SystemExit):
            a.publier_post(post, confirmer=True)


class TestLePackGratuit:

    def test_le_kit_tire_ses_prompts_des_posts(self):
        from alluxe_ia.pack import THEMES, prompts_choisis
        ids = {p.id for p in _posts()}
        assert set(THEMES) <= ids, f"posts absents : {set(THEMES) - ids}"
        prompts = prompts_choisis()
        assert len(prompts) >= 10
        assert len({p for _, _, p in prompts}) == len(prompts)
        assert all(p.strip() for _, _, p in prompts)

    def test_chaque_post_renvoie_au_lien_de_la_bio(self):
        """4 oct. : Meta masque les commentaires a l'application (mode
        Developpement), le kit ne peut pas partir en prive. Decision de
        l'operateur : le kit est en lien dans la bio. Aucun post ne doit
        plus promettre un envoi en message prive."""
        for post in _posts():
            assert post.slides[-1].mot_cle == "Lien en bio", post.id
            assert "bio" in post.legende, post.id
            assert "Commente KIT" not in post.legende and "en privé" not in post.legende, post.id

    def test_la_publication_quotidienne_ne_publie_qu_avec_confirmation(self):
        with open(os.path.join(RACINE, "systemd", "alluxe-ia-publication.service"),
                  encoding="utf-8") as f:
            service = f.read()
        assert "suivant --confirmer" in service
        with open(os.path.join(RACINE, "systemd", "alluxe-ia-publication.timer"),
                  encoding="utf-8") as f:
            assert "Persistent=false" in f.read(), (
                "un rattrapage publierait deux posts d'affilee")


class TestLeReel:

    def test_premiere_image_pleine_et_format_vertical(self):
        from alluxe_ia.reel import HAUTEUR as H, LARGEUR as L, REELS, images
        temps = REELS["01-tout-construit"]["temps"]
        premiere = next(images(temps))
        assert premiere.size == (L, H) == (1080, 1920)
        # Miniature du Reel : le texte doit déjà être là sur la 1re image.
        assert premiere.convert("L").getextrema()[1] > 200

    def test_le_reel_finit_sur_le_lien_en_bio(self):
        from alluxe_ia.reel import REELS
        for r in REELS.values():
            assert r["temps"][-1].mot_cle == "Lien en bio"
            assert "bio" in r["legende"] and "en privé" not in r["legende"]
            assert 7 <= sum(t.duree for t in r["temps"]) <= 30


class TestLaMusiqueDesReels:
    """4 oct. : le 1er Reel, muet, a fait 5 vues. Plus jamais de Reel silencieux."""

    def test_la_musique_n_est_pas_muette_et_ne_sature_pas(self):
        import numpy as np
        from alluxe_ia.musique import TAUX, composer
        st = composer(8.0, "essai")
        assert st.shape == (8 * TAUX, 2)
        rms = float(np.sqrt(np.mean(st ** 2)))
        assert 0.05 < rms < 0.5, rms
        assert np.max(np.abs(st)) < 1.0
        # Le son est là dès la première seconde (pas un long fondu).
        assert np.sqrt(np.mean(st[TAUX // 2:TAUX] ** 2)) > 0.03

    def test_une_variante_par_reel_toujours_la_meme(self):
        import numpy as np
        from alluxe_ia.musique import composer
        assert np.array_equal(composer(3.0, "a"), composer(3.0, "a"))
        assert not np.array_equal(composer(3.0, "a"), composer(3.0, "b"))

    def test_le_reel_n_utilise_plus_de_piste_muette(self):
        import alluxe_ia.reel as r
        source = open(r.__file__, encoding="utf-8").read()
        assert "anullsrc" not in source
        assert "ecrire_wav(" in source


class TestLeReelConversation:
    """4 oct. : le Reel « conversation animée » remplace le texte sur fond fixe."""

    def test_chaque_instant_se_dessine_au_bon_format(self):
        from alluxe_ia.reel_chat import DUREE, image
        t = 0.0
        while t <= DUREE:
            assert image(t).size == (1080, 1920)
            t += 0.1

    def test_l_image_bouge_d_un_instant_a_l_autre(self):
        from PIL import ImageChops
        from alluxe_ia.reel_chat import image
        # Même entre deux étapes de la scène, le fond dérive : jamais d'image figée.
        assert ImageChops.difference(image(7.0), image(7.5)).getbbox() is not None


class TestLeStyleVif:
    """4 oct. : couvertures pleine couleur, une par post, pour une grille de
    profil multicolore. Deux posts qui se suivent n'ont jamais la même."""

    def test_chaque_post_se_rend_en_vif(self):
        from alluxe_ia import slides
        ancien = slides.THEME
        try:
            slides.utiliser_theme("vif")
            for post in _posts():
                for img in rendre(post):
                    assert img.size == (LARGEUR, HAUTEUR), post.id
        finally:
            slides.utiliser_theme(ancien)

    def test_deux_posts_voisins_n_ont_jamais_la_meme_couleur(self):
        from alluxe_ia.slides import couleur_du_post
        ids = [p.id for p in _posts()]
        for a, b in zip(ids, ids[1:]):
            assert couleur_du_post(a) != couleur_du_post(b), (a, b)

    def test_chaque_post_a_une_etiquette(self):
        for post in _posts():
            assert post.etiquette, post.id

    def test_le_chiffre_vient_du_titre(self):
        from alluxe_ia.slides import Slide, _chiffre
        p = Post(id="99-x", legende="", slides=[Slide("couverture", titre="656 tests verts.")])
        assert _chiffre(p) == "656"
        p.slides[0].titre = "Crée ton assistant en 5 minutes"
        assert _chiffre(p) == ""


class TestLesFondsPhoto:
    """4 oct. : une scène par post, sans visage ni texte. Une couverture
    sans photo garde sa couleur ; avec photo, elle se rend au même format."""

    def test_chaque_post_a_sa_scene(self):
        from alluxe_ia.fonds import SCENES
        assert {p.id for p in _posts()} <= set(SCENES)

    def test_aucune_scene_ne_demande_de_visage(self):
        from alluxe_ia.fonds import STYLE, prompt
        assert "No people, no faces" in STYLE
        assert "no text" in prompt("03-108-rejetees")

    def test_la_couverture_photo_se_rend(self, tmp_path):
        from PIL import Image
        from alluxe_ia import slides
        photo = tmp_path / "fond.jpg"
        Image.new("RGB", (832, 1216), (90, 120, 160)).save(photo)
        post = _posts()[2]
        img = slides._couverture_photo(post, post.slides[0], len(post.slides), str(photo))
        assert img.size == (LARGEUR, HAUTEUR)
        # Le bas est assombri : le titre blanc doit s'y lire.
        assert sum(img.getpixel((LARGEUR - 40, HAUTEUR - 300))) < 3 * 90

    def test_chaque_post_a_sa_recherche_pexels(self):
        from alluxe_ia.fonds import RECHERCHE
        assert {p.id for p in _posts()} <= set(RECHERCHE)


class TestLeReelSurPhoto:

    def test_premiere_image_du_reel_vif(self):
        from alluxe_ia.reel import REELS, images_vif
        for rid, r in REELS.items():
            flux = images_vif(rid)
            if flux is None:      # pas encore de photo : l'ancien fond reste
                continue
            premiere = next(flux)
            assert premiere.size == (1080, 1920), rid
            assert premiere.convert("L").getextrema()[1] > 200, rid
