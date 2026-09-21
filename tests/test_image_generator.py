import pytest
import unittest

from config import IMAGE_NEGATIVE_PROMPT, IMAGE_PROMPTS, IMAGE_SEED
from image_generator import ImageGenerator


class TestImageGeneratorConfig(unittest.TestCase):
    def test_default_seed_and_negative_prompt_for_eve(self):
        self.assertEqual(IMAGE_SEED, 774921)
        self.assertIn("cgi", IMAGE_NEGATIVE_PROMPT)
        self.assertIn("smooth plastic skin", IMAGE_NEGATIVE_PROMPT)

    def test_all_default_prompts_push_photorealism(self):
        self.assertEqual(len(IMAGE_PROMPTS), 6)
        for prompt in IMAGE_PROMPTS:
            self.assertTrue(prompt.startswith("photo,"))
            self.assertIn("iPhone 15 Pro", prompt)
            self.assertIn("visible skin pores", prompt)

    def test_stability_body_includes_seed_and_negative_prompt(self):
        generator = ImageGenerator()
        body = generator._stability_body("photo, test", "cartoon, text")
        self.assertEqual(body["seed"], 774921)
        self.assertEqual(body["height"], 1024)
        self.assertEqual(body["width"], 1024)
        self.assertIn({"text": "photo, test", "weight": 1}, body["text_prompts"])
        self.assertIn({"text": "cartoon, text", "weight": -1}, body["text_prompts"])

    def test_replicate_body_uses_flux_style_controls(self):
        generator = ImageGenerator()
        body = generator._replicate_body("photo, test", "cartoon")
        self.assertEqual(body["input"]["seed"], 774921)
        self.assertEqual(body["input"]["guidance_scale"], 3.5)
        self.assertEqual(body["input"]["num_inference_steps"], 36)
        self.assertEqual(body["input"]["width"], 1024)
        self.assertEqual(body["input"]["height"], 1024)
        self.assertEqual(body["input"]["negative_prompt"], "cartoon")


class TestLeRepliSExecuteSurTousLesChemins:
    """Une panne d'un fournisseur doit passer au SUIVANT, pas tout casser.

    Le 20 septembre, Cloudflare a rendu « HTTP Error 408: Request
    Timeout » et l'erreur est remontee jusqu'a l'appelant alors que deux
    autres fournisseurs etaient configures a cote. `generer()` n'attrape
    que `ErreurMoteur` ; `_requeter_multipart` -- seule de toutes les
    methodes -- laissait filer l'`HTTPError` brute d'urllib.

    Le repli existait, il etait documente, il etait teste sur le chemin
    JSON. Il ne s'executait pas sur le chemin multipart. C'est le meme
    piege que le pyramidage et la pause du rejeu : un garde-fou se
    verifie sur CHAQUE chemin.
    """

    def test_une_erreur_http_devient_une_erreur_moteur(self, monkeypatch):
        import urllib.error
        from luna.moteurs import ErreurMoteur, GenerateurImages

        def tombe(*a, **k):
            raise urllib.error.HTTPError(
                "https://exemple", 408, "Request Timeout", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", tombe)
        with pytest.raises(ErreurMoteur):
            GenerateurImages._requeter_multipart(
                "https://exemple", "cle", {"prompt": "x"})

    def test_une_panne_reseau_devient_une_erreur_moteur(self, monkeypatch):
        import urllib.error
        from luna.moteurs import ErreurMoteur, GenerateurImages

        def tombe(*a, **k):
            raise urllib.error.URLError("connexion refusee")

        monkeypatch.setattr("urllib.request.urlopen", tombe)
        with pytest.raises(ErreurMoteur):
            GenerateurImages._requeter_multipart(
                "https://exemple", "cle", {"prompt": "x"})


class TestChaquePhotoEstPrenableParLuna:
    """Une photo sans photographe plausible trahit un faux compte.

    Remarque de l'operateur le 21 septembre : « elle fait des photos
    amateur avec son telephone, donc elle ne peut pas etre prise en
    photo dans son lit avec son telephone dans la main ». Il avait
    raison : une seule scene sur douze etait realisable par elle-meme,
    et le vocabulaire demandait explicitement un shooting professionnel
    (« travel magazine photography », « high fashion editorial »).
    """

    def test_chaque_scene_nomme_son_cadrage(self):
        from luna.photos import SCENES
        sans = [s.cle for s in SCENES if not s.cadrage]
        assert not sans, f"scenes sans cadrage : {sans}"

    def test_le_cadrage_arrive_jusqu_au_moteur(self):
        # Un cadrage qui n'est pas dans le prompt ne cadre rien.
        from luna.photos import SCENES, prompt_photo
        for s in SCENES:
            p = prompt_photo(s.cle, registre=s.registre)["prompt"]
            assert s.cadrage in p, f"{s.cle} : cadrage absent du prompt"

    def test_aucun_vocabulaire_de_studio(self):
        from luna.photos import SCENES
        interdits = ("editorial", "magazine", "luxury lifestyle",
                     "glamour photography", "fashion photography",
                     "studio", "photoshoot", "professional photographer")
        fautifs = [(s.cle, m) for s in SCENES for m in interdits
                   if m in s.decor.lower()]
        assert not fautifs, f"vocabulaire de shooting : {fautifs}"

    def test_les_scenes_sensuelles_n_ont_jamais_de_tiers(self):
        # Personne d'autre n'est dans la piece : c'est ce que la scene
        # raconte, et un photographe la contredirait.
        from luna.photos import SCENES, SENSUEL, AMIE, GROUPE
        for s in SCENES:
            if s.registre == SENSUEL:
                assert s.cadrage not in (AMIE, GROUPE), \
                    f"{s.cle} : un tiers photographie une scene intime"

    def test_luna_n_est_pas_toujours_seule(self):
        # « Elle est tres sociable, donc si elle est au cafe elle est
        # avec ses amies. » Et sept selfies miroir d'affilee, c'est
        # monotone autant qu'invraisemblable.
        from luna.photos import SCENES, TENDRE
        tendres = [s for s in SCENES if s.registre == TENDRE]
        avec = [s for s in tendres
                if any(m in s.decor for m in
                       ("friend", "classmate", "flatmate", "friends"))]
        assert len(avec) >= len(tendres) // 3, (
            f"seulement {len(avec)} scenes sur {len(tendres)} montrent "
            "quelqu'un d'autre")

    def test_les_yeux_ne_sont_pas_fluo(self):
        # L'ancienne formule « blue-green eyes with a subtle green hue »
        # rendait des yeux vert fluo, comme un personnage de jeu video.
        from luna.persona import LUNA
        ancre = LUNA.apparence.ancre.lower()
        assert "not bright green" in ancre
        assert "not glowing" in ancre
        assert "blue-green eyes" not in ancre


class TestLaCoiffureChangeDUnJourALAutre:
    """« De nos jours on ne va pas au coiffeur tous les jours. »

    L'ancre disait « long wavy platinum blonde hair » : Luna etait donc
    coiffee a l'identique sur chaque photo. La coiffure est desormais
    portee par la scene ; seules la longueur et la couleur restent dans
    l'identite, parce que c'est a elles qu'on la reconnait.
    """

    def test_chaque_scene_a_sa_coiffure(self):
        from luna.photos import SCENES
        sans = [s.cle for s in SCENES if not s.coiffure]
        assert not sans, f"scenes sans coiffure : {sans}"

    def test_la_coiffure_arrive_jusqu_au_moteur(self):
        from luna.photos import SCENES, prompt_photo
        for s in SCENES:
            p = prompt_photo(s.cle, registre=s.registre)["prompt"]
            assert s.coiffure in p, f"{s.cle} : coiffure absente du prompt"

    def test_plusieurs_coiffures_differentes(self):
        # Une seule coiffure repetee partout ne vaudrait pas mieux que
        # l'ancre figee qu'on vient de retirer.
        from luna.photos import SCENES
        assert len({s.coiffure for s in SCENES}) >= 5

    def test_l_identite_ne_porte_plus_de_mise_en_pli(self):
        from luna.persona import LUNA
        ancre = LUNA.apparence.ancre.lower()
        assert "wavy platinum" not in ancre
        # Les racines, elles, restent : elles ne dependent pas de la
        # scene mais de son budget.
        assert "regrowth at the roots" in ancre
