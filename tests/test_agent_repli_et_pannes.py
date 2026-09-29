"""L'agent doit répondre quand son gros modèle est rationné — et ne pas radoter.

L'INCIDENT, 27 septembre 2026. Monsieur : « il répond plusieurs fois les
mêmes choses ». Lu dans la table de discussion :

    x4  (agent indisponible : HTTP 429 : Rate limit reached for model
        `openai/gpt-oss-120b`...)
    x2  Desole, je n'arrive pas a repondre proprement pour l'instant

Ce n'étaient pas des réponses répétées : c'étaient **des messages
d'erreur republiés à chaque tentative**. L'agent tourne sur le palier
gratuit de Groq avec un modèle de 120 milliards de paramètres ; quand il
est rationné, chaque essai publiait sa propre erreur. Sur une question
d'hier, sept minutes se sont écoulées avant ce message.

Deux remèdes, tous deux verrouillés ici :

1. Le débit se compte PAR MODÈLE : quand le gros est saturé, on bascule
   sur un plus petit et on répond quand même.
2. Une panne identique à la précédente n'est plus republiée.
"""
from __future__ import annotations

import unittest
from unittest import mock

from ops import agent_alluxe as agent


class TestReconnaitreUnePanne(unittest.TestCase):

    def test_les_messages_de_panne_sont_reconnus(self):
        for t in ("(agent indisponible : HTTP 429 : ...)",
                  "(panne de mon cote : ValueError : x)",
                  "Desole, je n'arrive pas a repondre proprement pour l'instant"):
            self.assertTrue(agent._est_une_panne(t), t)

    def test_une_vraie_reponse_n_est_pas_une_panne(self):
        for t in ("Monsieur, le robot tient 10 positions.",
                  "Capital 89,97 EUR.",
                  "  Je regarde tout de suite."):
            self.assertFalse(agent._est_une_panne(t), t)

    def test_le_429_est_traduit_en_francais_et_dit_que_ca_revient(self):
        m = agent._panne_lisible(agent.ErreurAgent("HTTP 429 : Rate limit"))
        self.assertNotIn("429", m)
        self.assertIn("sature", m)

    def test_une_cle_refusee_dit_que_ca_ne_se_reglera_pas_tout_seul(self):
        m = agent._panne_lisible(agent.ErreurAgent("HTTP 401 : bad key"))
        self.assertIn("renouveler", m)


class TestRepliDeModele(unittest.TestCase):

    def test_le_429_fait_basculer_sur_le_modele_suivant(self):
        essayes: list[str] = []

        def faux(messages, modele=""):
            essayes.append(modele)
            if len(essayes) == 1:
                raise agent.ErreurAgent("HTTP 429 : Rate limit reached")
            return {"choices": [{"message": {"content": "ok"}}]}

        with mock.patch.object(agent, "_appeler_moteur", faux), \
             mock.patch.dict("os.environ", {"LUNA_API_MODELE": "gros"}):
            r = agent._appeler_moteur_avec_repli([{"role": "user", "content": "x"}])
        self.assertEqual(r["choices"][0]["message"]["content"], "ok")
        self.assertEqual(essayes[0], "gros")
        self.assertEqual(len(essayes), 2, "le repli n'a pas ete tente")

    def test_une_erreur_de_cle_ne_fait_PAS_basculer(self):
        """Elle se reproduirait a l'identique : la masquer serait pire."""
        essayes: list[str] = []

        def faux(messages, modele=""):
            essayes.append(modele)
            raise agent.ErreurAgent("HTTP 401 : invalid api key")

        with mock.patch.object(agent, "_appeler_moteur", faux), \
             mock.patch.dict("os.environ", {"LUNA_API_MODELE": "gros"}):
            with self.assertRaises(agent.ErreurAgent):
                agent._appeler_moteur_avec_repli([{"role": "user", "content": "x"}])
        self.assertEqual(essayes, ["gros"])

    def test_il_existe_au_moins_un_modele_de_repli(self):
        self.assertTrue(agent.MODELES_DE_REPLI,
                        "sans repli, un rationnement redevient un silence")


if __name__ == "__main__":
    unittest.main()
