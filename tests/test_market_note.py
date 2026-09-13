"""La note du matin ne doit jamais predire un prix ni promettre un gain.

Le prompt envoye a Claude le lui interdit — mais un prompt est une
consigne, pas une garantie. Ces tests verrouillent la RELECTURE par du
code, qui est la vraie barriere : dans une application financiere
publiee sur le Play Store, une prediction de prix est un motif de
retrait, et une promesse de gain est un mensonge fait a l'utilisateur.
"""

from __future__ import annotations

import json
import unittest

from gold_bot.market_note import (NoteRefusee, Photo, RedacteurDeNote,
                                  verifier_la_note)


def _photo(**kw) -> Photo:
    base = dict(btc_prix=58420.0, btc_var_7j=3.2, btc_vs_ma50=5.1,
                eth_prix=2900.0, eth_var_7j=1.8, eth_vs_ma50=2.0,
                fear_greed=61, fear_greed_texte="avidite",
                dominance_btc=54.3, volatilite_pct=2.1)
    base.update(kw)
    return Photo(**base)


BONNE = ("Le bitcoin reprend un peu de terrain cette semaine",
         "Le bitcoin vaut ce matin 58 420 euros, soit 3,2 % de plus "
         "qu'il y a sept jours.\n\n"
         "L'ethereum suit le meme mouvement, plus doucement.\n\n"
         "Le climat general reste a l'optimisme mesure.")


class TestLaRelectureRefuseCeQuiEstInterdit(unittest.TestCase):

    def test_une_prediction_de_prix_est_refusee(self):
        for phrase in ("Le bitcoin devrait atteindre 70 000 euros.",
                       "Il montera sans doute cette semaine.",
                       "Notre objectif de 65 000 euros reste valable.",
                       "D'ici la fin du mois, le marche sera plus haut."):
            with self.assertRaises(NoteRefusee, msg=phrase):
                verifier_la_note("Un titre", phrase + " " * 40, _photo())

    def test_une_promesse_de_gain_est_refusee(self):
        for phrase in ("Ce placement est sans risque pour l'epargnant.",
                       "Un rendement garanti attend les investisseurs.",
                       "Vous allez gagner en suivant ce signal aujourd'hui.",
                       "Il faut acheter maintenant avant la hausse."):
            with self.assertRaises(NoteRefusee, msg=phrase):
                verifier_la_note("Un titre", phrase + " " * 40, _photo())

    def test_un_ton_alarmiste_est_refuse(self):
        # Faire paniquer vend autant que promettre, et fait plus de degats.
        with self.assertRaises(NoteRefusee):
            verifier_la_note(
                "Un titre",
                "Un krach imminent menace le marche, vendez tout." + " " * 40,
                _photo())

    def test_une_note_factuelle_passe(self):
        verifier_la_note(*BONNE, _photo())      # ne doit rien lever


class TestLaFormeExigee(unittest.TestCase):

    def test_le_titre_tient_en_une_phrase(self):
        with self.assertRaises(NoteRefusee):
            verifier_la_note("Premiere phrase. Deuxieme phrase.",
                             BONNE[1], _photo())

    def test_pas_plus_de_trois_paragraphes(self):
        corps = "\n\n".join(f"Paragraphe numero {i} du matin." for i in range(4))
        with self.assertRaises(NoteRefusee):
            verifier_la_note("Un titre", corps, _photo())

    def test_le_corps_respecte_le_minimum_de_la_base(self):
        # check (length(btrim(body_fr)) >= 40) dans la migration.
        with self.assertRaises(NoteRefusee):
            verifier_la_note("Un titre", "Trop court.", _photo())

    def test_un_titre_vide_est_refuse(self):
        with self.assertRaises(NoteRefusee):
            verifier_la_note("   ", BONNE[1], _photo())


class TestLAnnonceImportanteDoitEtreCitee(unittest.TestCase):
    """Le seul jour ou l'utilisateur a vraiment besoin de la note."""

    def test_une_annonce_forte_omise_fait_refuser_la_note(self):
        photo = _photo(evenements=[{"name_fr": "Inflation americaine",
                                    "impact": "high"}])
        with self.assertRaises(NoteRefusee) as ctx:
            verifier_la_note(*BONNE, photo)
        self.assertIn("Inflation americaine", str(ctx.exception))

    def test_une_annonce_forte_citee_passe(self):
        photo = _photo(evenements=[{"name_fr": "Inflation americaine",
                                    "impact": "high"}])
        # On REMPLACE le dernier paragraphe au lieu d'en ajouter un :
        # la note d'exemple en compte deja trois, qui est le maximum.
        paras = BONNE[1].split("\n\n")
        paras[-1] = "L'inflation americaine est publiee cet apres-midi."
        verifier_la_note(BONNE[0], "\n\n".join(paras), photo)

    def test_une_annonce_moyenne_n_est_pas_obligatoire(self):
        photo = _photo(evenements=[{"name_fr": "Ventes au detail",
                                    "impact": "medium"}])
        verifier_la_note(*BONNE, photo)


class TestLesJaugesAffichees(unittest.TestCase):

    def test_les_bornes_de_la_base_sont_respectees(self):
        # Une jauge qui recoit 250 sur 100 s'affiche hors de son cadre.
        extreme = _photo(btc_var_7j=400.0, btc_vs_ma50=400.0,
                         eth_var_7j=400.0, eth_vs_ma50=400.0,
                         volatilite_pct=90.0)
        self.assertLessEqual(extreme.trend_score(), 100)
        self.assertLessEqual(extreme.volatility_score(), 100)
        chute = _photo(btc_var_7j=-400.0, btc_vs_ma50=-400.0,
                       eth_var_7j=-400.0, eth_vs_ma50=-400.0)
        self.assertGreaterEqual(chute.trend_score(), -100)

    def test_sans_donnee_la_jauge_vaut_None_et_pas_zero(self):
        # Zero veut dire « marche neutre ». Absence veut dire « on ne
        # sait pas ». Les confondre affiche une information fausse.
        vide = Photo()
        self.assertIsNone(vide.trend_score())
        self.assertIsNone(vide.volatility_score())

    def test_une_hausse_donne_un_score_positif(self):
        self.assertGreater(_photo().trend_score(), 0)


class LLMFactice:
    """Un Claude de laboratoire qui rend ce qu'on lui dicte."""

    def __init__(self, reponses):
        self.reponses = list(reponses)
        self.demandes = []
        self.messages = self

    def create(self, **kw):
        self.demandes.append(kw)
        contenu = self.reponses.pop(0)

        class Bloc:
            type = "text"
            text = contenu

        class Reponse:
            content = [Bloc()]

        return Reponse()


def _json(titre, corps):
    return json.dumps({"titre": titre, "corps": corps})


class TestLeCycleDeRedaction(unittest.TestCase):

    def test_une_note_conforme_est_acceptee_du_premier_coup(self):
        llm = LLMFactice([_json(*BONNE)])
        titre, corps = RedacteurDeNote(client_llm=llm).rediger(_photo())
        self.assertEqual(titre, BONNE[0])
        self.assertEqual(len(llm.demandes), 1)

    def test_une_note_refusee_est_redemandee_avec_le_motif(self):
        llm = LLMFactice([
            _json("Un titre", "Le bitcoin devrait atteindre 70 000 euros. "
                              "Le marche est calme ce matin par ailleurs."),
            _json(*BONNE),
        ])
        titre, _ = RedacteurDeNote(client_llm=llm).rediger(_photo())
        self.assertEqual(titre, BONNE[0])
        self.assertEqual(len(llm.demandes), 2)
        # Le modele doit savoir CE QUI a ete refuse, sinon il recommence.
        self.assertIn("refusee", llm.demandes[1]["messages"][0]["content"])

    def test_deux_echecs_ne_publient_rien(self):
        mauvaise = _json("Un titre", "Un rendement garanti attend les "
                                     "investisseurs de ce marche calme.")
        llm = LLMFactice([mauvaise, mauvaise])
        with self.assertRaises(NoteRefusee):
            RedacteurDeNote(client_llm=llm).rediger(_photo())

    def test_une_reponse_illisible_est_traitee_comme_un_refus(self):
        llm = LLMFactice(["desole, je ne peux pas", "toujours pas"])
        with self.assertRaises(NoteRefusee):
            RedacteurDeNote(client_llm=llm).rediger(_photo())

    def test_sans_cle_anthropic_aucune_note_n_est_inventee(self):
        with self.assertRaises(NoteRefusee):
            RedacteurDeNote(client_llm=None).rediger(_photo())


class TestLeDepotResteUnBrouillon(unittest.TestCase):
    """Rien n'est publie sans qu'un humain ait lu."""

    class BaseFactice:
        def __init__(self):
            self.lignes = []

        def inserer(self, table, ligne):
            self.lignes.append((table, ligne))
            return [ligne]

    def test_la_date_de_publication_reste_nulle(self):
        base = self.BaseFactice()
        RedacteurDeNote(client_base=base).deposer(*BONNE, _photo())
        table, ligne = base.lignes[0]
        self.assertEqual(table, "market_notes")
        self.assertIsNone(ligne["published_at"])

    def test_les_jauges_partent_avec_la_note(self):
        base = self.BaseFactice()
        RedacteurDeNote(client_base=base).deposer(*BONNE, _photo())
        ligne = base.lignes[0][1]
        for champ in ("trend_score", "volatility_score", "fear_greed",
                      "btc_dominance"):
            self.assertIsNotNone(ligne[champ], champ)


if __name__ == "__main__":
    unittest.main()
