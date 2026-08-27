"""Tests de Luna : cadre, memoire, moments, photos, avatar, application.

Le test qui compte le plus ici : `TestPlafonds`. Un registre adulte ne doit
JAMAIS franchir un canal public, et une mention de minorite doit revoquer
l'acces au lieu de simplement le contourner. Le reste peut se degrader ;
ces deux-la, non.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime

from luna import limites
from luna.avatar import demarrer_visio, expression_pour
from luna.chat import Luna
from luna.memoire import Memoire
from luna.moments import MOMENTS, moment_pour
from luna.moteurs import ErreurMoteur, Moteur
from luna.persona import LUNA
from luna.photos import SCENES, prompt_photo, scenes_autorisees
from luna.prompt import construire


def fichier_temporaire(suffixe: str = ".json") -> str:
    fd, chemin = tempfile.mkstemp(suffix=suffixe)
    os.close(fd)
    os.unlink(chemin)
    return chemin


class MoteurFactice(Moteur):
    """Moteur previsible : il rend ce qu'on lui a dit de rendre."""

    nom = "factice"
    disponible = True

    def __init__(self, reponse: str = "Coucou toi 😊", erreur: str = ""):
        self.reponse = reponse
        self.erreur = erreur
        self.dernier_systeme = ""
        self.derniers_tours: list[dict] = []

    def repondre(self, systeme: str, tours: list[dict]) -> str:
        self.dernier_systeme = systeme
        self.derniers_tours = tours
        if self.erreur:
            raise ErreurMoteur(self.erreur)
        return self.reponse


def luna_de_test(moteur=None, porte=None, heure: datetime | None = None) -> Luna:
    horloge = (lambda: heure) if heure else datetime.now
    return Luna(memoire=Memoire(fichier_temporaire()),
                porte=porte or limites.PorteAdulte(fichier_temporaire()),
                moteur=moteur or MoteurFactice(), horloge=horloge)


class TestMoments(unittest.TestCase):
    def test_la_journee_suit_l_heure(self):
        lundi = lambda h: datetime(2026, 8, 24, h)  # noqa: E731
        self.assertEqual(moment_pour(lundi(7)).cle, "matin")
        self.assertEqual(moment_pour(lundi(10)).cle, "travail")
        self.assertEqual(moment_pour(lundi(12)).cle, "pause")
        self.assertEqual(moment_pour(lundi(19)).cle, "retour")
        self.assertEqual(moment_pour(lundi(21)).cle, "soiree")
        self.assertEqual(moment_pour(lundi(2)).cle, "nuit")

    def test_le_week_end_elle_ne_travaille_pas(self):
        samedi = datetime(2026, 8, 22, 10)
        self.assertNotEqual(moment_pour(samedi).cle, "travail")

    def test_la_soiree_privee_ne_se_declenche_jamais_seule(self):
        heures = [moment_pour(datetime(2026, 8, 24, h)).cle for h in range(24)]
        self.assertNotIn("soiree_privee", heures)
        self.assertTrue(MOMENTS["soiree_privee"].sur_demande)


class TestMemoire(unittest.TestCase):
    def test_elle_retient_prenom_gouts_et_lieu(self):
        m = Memoire()
        m.apprendre("Salut, moi c'est Marc, j'adore la moto et j'habite a Lyon")
        self.assertEqual(m.prenom, "Marc")
        resume = m.resume()
        self.assertIn("Marc", resume)
        self.assertIn("moto", resume)
        self.assertIn("Lyon", resume)

    def test_l_apostrophe_manquante_ou_typographique_ne_casse_rien(self):
        for phrase in ("moi c est Paul", "moi c'est Paul", "moi c’est Paul"):
            m = Memoire()
            m.apprendre(phrase)
            self.assertEqual(m.prenom, "Paul", phrase)

    def test_pas_de_doublon(self):
        m = Memoire()
        m.apprendre("j'aime le chocolat")
        m.apprendre("j'aime le chocolat")
        gouts = [f for f in m.faits if f.categorie == "gout"]
        self.assertEqual(len(gouts), 1)

    def test_elle_se_souvient_apres_redemarrage(self):
        chemin = fichier_temporaire()
        m = Memoire(chemin)
        m.apprendre("moi c'est Sofia")
        m.noter("user", "coucou")
        m.sauver()
        self.assertEqual(Memoire(chemin).prenom, "Sofia")
        self.assertEqual(len(Memoire(chemin).historique()), 1)

    def test_oublier_efface_vraiment(self):
        chemin = fichier_temporaire()
        m = Memoire(chemin)
        m.apprendre("moi c'est Sofia")
        m.oublier()
        self.assertEqual(Memoire(chemin).prenom, "")


class TestPlafonds(unittest.TestCase):
    """Les trois filtres : demande, acces, canal. Le plus bas gagne."""

    def test_sans_verification_tout_retombe_en_tendre(self):
        porte = limites.PorteAdulte(fichier_temporaire())
        self.assertEqual(porte.registre_effectif(limites.ADULTE, "app"), limites.TENDRE)

    def test_apres_verification_l_app_privee_ouvre(self):
        porte = limites.PorteAdulte(fichier_temporaire())
        porte.confirmer(registre_max=limites.ADULTE)
        self.assertEqual(porte.registre_effectif(limites.ADULTE, "app"), limites.ADULTE)

    def test_aucun_canal_public_ne_recoit_de_contenu_sensuel(self):
        porte = limites.PorteAdulte(fichier_temporaire())
        porte.confirmer(registre_max=limites.ADULTE)
        for canal in ("instagram", "snapchat", "sms"):
            self.assertEqual(porte.registre_effectif(limites.ADULTE, canal),
                             limites.TENDRE, canal)

    def test_le_telephone_plafonne_au_sensuel(self):
        porte = limites.PorteAdulte(fichier_temporaire())
        porte.confirmer(registre_max=limites.ADULTE)
        self.assertEqual(porte.registre_effectif(limites.ADULTE, "telephone"),
                         limites.SENSUEL)

    def test_un_canal_inconnu_est_traite_comme_public(self):
        porte = limites.PorteAdulte(fichier_temporaire())
        porte.confirmer(registre_max=limites.ADULTE)
        self.assertEqual(porte.registre_effectif(limites.ADULTE, "tiktok"),
                         limites.TENDRE)

    def test_la_verification_survit_au_redemarrage(self):
        chemin = fichier_temporaire()
        limites.PorteAdulte(chemin).confirmer(registre_max=limites.ADULTE)
        self.assertTrue(limites.PorteAdulte(chemin).acces.majeur)

    def test_revoquer_reverrouille(self):
        porte = limites.PorteAdulte(fichier_temporaire())
        porte.confirmer(registre_max=limites.ADULTE)
        porte.revoquer()
        self.assertEqual(porte.registre_effectif(limites.SENSUEL, "app"), limites.TENDRE)


class TestSignaux(unittest.TestCase):
    def test_detresse_et_minorite_sont_reperees(self):
        self.assertIn("detresse", [s.cle for s in limites.analyser("j'ai envie de mourir")])
        self.assertIn("mineur", [s.cle for s in limites.analyser("j'ai 15 ans")])
        self.assertIn("argent", [s.cle for s in limites.analyser("je t'envoie mon IBAN")])
        self.assertIn("realite", [s.cle for s in limites.analyser("tu es humaine ?")])

    def test_un_message_ordinaire_ne_declenche_rien(self):
        self.assertEqual(limites.analyser("tu fais quoi ce soir ?"), [])

    def test_une_minorite_annoncee_revoque_l_acces(self):
        porte = limites.PorteAdulte(fichier_temporaire())
        porte.confirmer(registre_max=limites.ADULTE)
        luna = luna_de_test(porte=porte)
        luna.demander_registre(limites.ADULTE)
        luna.repondre("en fait j'ai 15 ans")
        self.assertFalse(porte.acces.majeur)
        self.assertEqual(luna.registre_effectif("app"), limites.TENDRE)


class TestPhotos(unittest.TestCase):
    def test_toutes_les_photos_partagent_le_meme_visage(self):
        for scene in scenes_autorisees(limites.ADULTE):
            demande = prompt_photo(scene.cle, limites.ADULTE)
            self.assertIn(LUNA.apparence.ancre, demande["prompt"], scene.cle)
            self.assertEqual(demande["graine"], LUNA.apparence.graine)

    def test_chaque_prompt_dit_que_c_est_une_fiction_adulte(self):
        for scene in SCENES:
            demande = prompt_photo(scene.cle, limites.ADULTE)
            self.assertIn("fictional", demande["prompt"])
            self.assertIn("30-year-old adult woman", demande["prompt"])
            self.assertIn("underage", demande["negatif"])

    def test_une_scene_sensuelle_est_refusee_en_registre_tendre(self):
        with self.assertRaises(PermissionError):
            prompt_photo("boudoir", limites.TENDRE)

    def test_scene_inconnue(self):
        with self.assertRaises(KeyError):
            prompt_photo("plage_nudiste", limites.ADULTE)


class TestAvatar(unittest.TestCase):
    def test_l_expression_suit_le_ton(self):
        self.assertEqual(expression_pour("haha 😂"), "rire")
        self.assertEqual(expression_pour("je pense a toi ❤️"), "tendre")
        self.assertEqual(expression_pour("bonjour"), "sourire")

    def test_l_expression_seductrice_est_bridee_en_tendre(self):
        self.assertEqual(expression_pour("viens ici 😈", limites.TENDRE), "clin")
        self.assertEqual(expression_pour("viens ici 😈", limites.SENSUEL), "seductrice")

    def test_la_visio_ne_propose_que_des_tenues_autorisees(self):
        session = demarrer_visio(MOMENTS["soiree_privee"], limites.TENDRE)
        self.assertEqual(session.tenue.registre, limites.TENDRE)

    def test_la_tenue_demandee_est_respectee_si_le_registre_suit(self):
        session = demarrer_visio(MOMENTS["soiree"], limites.SENSUEL, tenue="lingerie")
        self.assertEqual(session.tenue.cle, "lingerie")


class TestPhotoDansLaVisio(unittest.TestCase):
    """La visio doit pouvoir montrer une photo, pas seulement le dessin."""

    def test_chaque_tenue_pointe_vers_une_scene_existante(self):
        from luna.avatar import TENUES
        from luna.photos import SCENES_PAR_CLE
        for tenue in TENUES:
            self.assertTrue(tenue.scene, tenue.cle)
            self.assertIn(tenue.scene, SCENES_PAR_CLE, tenue.cle)

    def test_la_scene_d_une_tenue_ne_depasse_pas_son_registre(self):
        from luna.avatar import TENUES
        from luna.photos import SCENES_PAR_CLE
        for tenue in TENUES:
            scene = SCENES_PAR_CLE[tenue.scene]
            self.assertLessEqual(limites.rang(scene.registre),
                                 limites.rang(tenue.registre), tenue.cle)

    def test_la_visio_annonce_la_scene_a_afficher(self):
        from luna import serveur
        serveur.DOSSIER_DONNEES = tempfile.mkdtemp()
        app = serveur.Application()
        app.luna.moteur = MoteurFactice()
        self.assertEqual(app.visio({})["tenue"]["scene"],
                         app.visio({})["tenue"]["scene"])
        self.assertTrue(app.visio({})["tenue"]["scene"])

    def test_une_photo_generee_est_mise_en_cache(self):
        from luna import serveur
        serveur.DOSSIER_DONNEES = tempfile.mkdtemp()
        app = serveur.Application()
        app.luna.moteur = MoteurFactice()

        class GenerateurFactice:
            disponible = True

            def __init__(self):
                self.appels = 0

            def generer(self, prompt, negatif="", graine=0):
                self.appels += 1
                return b"\x89PNG\r\n\x1a\n-fausse-image"

        app.images = GenerateurFactice()
        premier = app.photo({"scene": "bureau"})
        second = app.photo({"scene": "bureau"})
        self.assertTrue(premier["image"].startswith("data:image/png;base64,"))
        self.assertEqual(premier["image"], second["image"])
        self.assertEqual(app.images.appels, 1, "la seconde demande doit venir du cache")
        self.assertTrue(second["cache"])

    def test_regenerer_force_une_nouvelle_image(self):
        from luna import serveur
        serveur.DOSSIER_DONNEES = tempfile.mkdtemp()
        app = serveur.Application()
        app.luna.moteur = MoteurFactice()

        class GenerateurFactice:
            disponible = True
            appels = 0

            def generer(self, prompt, negatif="", graine=0):
                type(self).appels += 1
                return b"image"

        app.images = GenerateurFactice()
        app.photo({"scene": "bureau"})
        app.photo({"scene": "bureau", "regenerer": True})
        self.assertEqual(GenerateurFactice.appels, 2)


class TestPrompt(unittest.TestCase):
    def test_le_cadre_et_la_memoire_sont_dans_le_prompt(self):
        memoire = Memoire()
        memoire.apprendre("moi c'est Marc")
        texte = construire(LUNA, MOMENTS["soiree"], memoire, limites.SENSUEL)
        self.assertIn("Luna", texte)
        self.assertIn("Marc", texte)
        self.assertIn("personnage de fiction", texte)
        self.assertIn("3114", texte)
        self.assertIn("REGISTRE : sensuel", texte)

    def test_les_signaux_sont_ajoutes_au_prompt(self):
        signaux = limites.analyser("j'ai envie de mourir")
        texte = construire(LUNA, MOMENTS["soiree"], Memoire(), limites.TENDRE, signaux)
        self.assertIn("ALERTE", texte)


class TestConversation(unittest.TestCase):
    def test_elle_repond_et_retient(self):
        moteur = MoteurFactice("Enchantee Marc 😊")
        luna = luna_de_test(moteur)
        reponse = luna.repondre("moi c'est Marc")
        self.assertEqual(reponse.texte, "Enchantee Marc 😊")
        self.assertEqual(luna.memoire.prenom, "Marc")
        self.assertEqual(len(luna.memoire.historique()), 2)

    def test_une_panne_du_moteur_ne_casse_pas_la_conversation(self):
        luna = luna_de_test(MoteurFactice(erreur="HTTP 500"))
        reponse = luna.repondre("coucou")
        self.assertIn("souci technique", reponse.texte)
        self.assertEqual(reponse.erreur, "HTTP 500")

    def test_un_message_vide_est_refuse(self):
        with self.assertRaises(ValueError):
            luna_de_test().repondre("   ")

    def test_la_soiree_privee_retombe_en_soiree_sans_acces(self):
        luna = luna_de_test()
        luna.forcer_moment("soiree_privee")
        luna.demander_registre(limites.ADULTE)
        self.assertEqual(luna.registre_effectif("app"), limites.TENDRE)
        self.assertEqual(luna.moment().cle, "soiree")

    def test_l_ouverture_change_avec_le_moment(self):
        matin = luna_de_test(heure=datetime(2026, 8, 24, 7)).ouverture()
        soir = luna_de_test(heure=datetime(2026, 8, 24, 21)).ouverture()
        self.assertEqual(matin.moment, "matin")
        self.assertEqual(soir.moment, "soiree")


class TestApplication(unittest.TestCase):
    """L'API du serveur, appelee directement — sans ouvrir de socket."""

    def application(self):
        from luna import serveur
        serveur.DOSSIER_DONNEES = tempfile.mkdtemp()
        app = serveur.Application()
        app.luna.moteur = MoteurFactice()
        return app

    def test_l_etat_decrit_tout_ce_dont_l_interface_a_besoin(self):
        etat = self.application().etat()
        for cle in ("persona", "moment", "registre", "acces", "moteur",
                    "tenues", "ambiances", "jeux", "scenes", "capacites"):
            self.assertIn(cle, etat)

    def test_la_soiree_privee_est_refusee_avant_verification(self):
        app = self.application()
        self.assertEqual(app.moment({"cle": "soiree_privee"}).get("erreur"), "acces_refuse")
        app.acces({"majeur": True, "registre_max": limites.ADULTE})
        self.assertEqual(app.moment({"cle": "soiree_privee"})["moment"]["cle"],
                         "soiree_privee")

    def test_sans_generateur_l_application_rend_le_prompt(self):
        app = self.application()
        resultat = app.photo({"scene": "matin"})
        self.assertEqual(resultat["image"], "")
        self.assertIn("prompt", resultat)

    def test_le_canal_instagram_reste_tendre_meme_verifie(self):
        app = self.application()
        app.acces({"majeur": True, "registre_max": limites.ADULTE})
        app.registre({"registre": limites.ADULTE})
        self.assertEqual(app.message({"texte": "coucou", "canal": "instagram"})["registre"],
                         limites.TENDRE)


if __name__ == "__main__":
    unittest.main()
