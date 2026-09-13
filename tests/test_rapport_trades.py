"""Le rapport doit etre lisible par quelqu'un qui ne connait rien au trading.

C'est une exigence explicite de l'operateur, repetee plusieurs fois :
« parle-moi en euros, ça je comprends ». Un rapport truffe de R, d'ATR
et de « supertrend » est un rapport qu'on cesse de lire — et un
operateur qui ne lit plus son rapport ne voit pas venir les problemes.
"""

from __future__ import annotations

import unittest

from gold_bot.rapport_trades import bilan, nom_court, raison_lisible


class FauxTrade:
    def __init__(self, symbol, profit, reason, closed_at=0.0):
        self.symbol, self.profit = symbol, profit
        self.reason, self.closed_at = reason, closed_at


class TestLaTraductionDesRaisons(unittest.TestCase):

    def test_aucun_jargon_ne_survit(self):
        # Les vraies raisons trouvees dans le journal du robot.
        brutes = [
            "stop declenche sur la plateforme",
            "stop deja atteint",
            "stop temporel : 360 min sans progression (-0.84R)",
            "prise partielle de 30% a 1.01R",
            "retournement confirme a +0.26R (dynamique -0.60 : "
            "supertrend retourne contre la position)",
            "perte anormale -1.50R : sortie de securite",
            "micro-profit +1.60R : dynamique faible (+0.17), gain encaisse",
        ]
        for b in brutes:
            texte = raison_lisible(b, -1.0).lower()
            for mot in ("r)", "atr", "supertrend", "dynamique", "0.84",
                        "micro-profit", "anormale"):
                self.assertNotIn(mot, texte, f"{mot!r} survit dans {texte!r}")

    def test_le_meme_stop_se_dit_autrement_selon_le_resultat(self):
        # LE POINT LE PLUS IMPORTANT DU MODULE.
        # Le robot remonte sa protection : un stop touche sur une
        # position gagnante n'est pas un echec, c'est le mecanisme qui
        # a fonctionne. Sur un rapport ou 80 % des sorties sont des
        # stops, les confondre donne l'impression d'un robot qui se
        # fait sortir en permanence.
        brute = "stop declenche sur la plateforme"
        self.assertIn("encaisse", raison_lisible(brute, +1.00))
        self.assertIn("protection", raison_lisible(brute, -1.33))

    def test_sans_resultat_connu_on_reste_neutre(self):
        self.assertEqual(raison_lisible("stop deja atteint"),
                         "protection touchee")

    def test_le_delai_est_dit_en_heures_pas_en_minutes(self):
        # « 360 min » ne parle a personne ; « 6 heures » si.
        self.assertIn("6 heures",
                      raison_lisible("stop temporel : 360 min sans progression"))
        self.assertIn("3 heures",
                      raison_lisible("stop temporel : 180 min sans progression"))

    def test_une_raison_inconnue_est_rendue_telle_quelle(self):
        # Inventer une explication fausse est pire que d'afficher du
        # texte technique.
        self.assertEqual(raison_lisible("motif totalement nouveau"),
                         "motif totalement nouveau")

    def test_une_raison_vide_ne_casse_rien(self):
        self.assertEqual(raison_lisible(""), "sortie")
        self.assertEqual(raison_lisible(None), "sortie")


class TestLesNoms(unittest.TestCase):

    def test_les_cryptos_connues_portent_leur_nom(self):
        self.assertEqual(nom_court("TRXUSD"), "Tron")
        self.assertEqual(nom_court("ETHEUR"), "Ethereum")

    def test_une_crypto_inconnue_garde_son_symbole(self):
        # Mieux que d'inventer un nom.
        self.assertEqual(nom_court("POWRUSD"), "POWR")

    def test_la_devise_est_retiree_meme_quand_elle_est_longue(self):
        self.assertEqual(nom_court("BTCUSDT"), "Bitcoin")


class TestLeBilan(unittest.TestCase):

    def test_rien_de_ferme_ne_produit_aucune_ligne(self):
        # Une section « 0 trade » repetee toutes les demi-heures fait du
        # bruit et finit par faire ignorer le rapport entier.
        self.assertEqual(bilan([]), [])

    def test_le_total_et_le_compte_sont_justes(self):
        trades = [FauxTrade("BTCEUR", 1.50, "stop deja atteint", 3),
                  FauxTrade("ETHEUR", -0.80, "stop deja atteint", 2),
                  FauxTrade("SOLEUR", 0.30, "stop deja atteint", 1)]
        tete = bilan(trades)[0]
        self.assertIn("3 trades fermes", tete)
        self.assertIn("+1,00 EUR", tete)
        self.assertIn("2 gagnants sur 3", tete)

    def test_les_plus_recents_sont_montres_en_premier(self):
        # LE DEFAUT QUE CE TEST EMPECHE : couper la liste AVANT de la
        # trier garderait les plus anciens — l'inverse de ce qu'on veut.
        trades = [FauxTrade(f"C{i}EUR", 1.0, "stop deja atteint", i)
                  for i in range(20)]
        lignes = bilan(trades, detail_max=3)
        self.assertIn("C19", lignes[1])
        self.assertIn("C18", lignes[2])
        self.assertIn("C17", lignes[3])
        self.assertIn("17 autres", lignes[-1])

    def test_le_total_porte_sur_tous_les_trades_pas_seulement_les_montres(self):
        trades = [FauxTrade(f"C{i}EUR", 1.0, "stop deja atteint", i)
                  for i in range(20)]
        self.assertIn("+20,00 EUR", bilan(trades, detail_max=3)[0])

    def test_un_seul_trade_se_dit_au_singulier(self):
        tete = bilan([FauxTrade("BTCEUR", 1.0, "stop deja atteint")])[0]
        self.assertIn("1 trade ferme", tete)
        self.assertNotIn("gagnant", tete)      # inutile sur un seul

    def test_chaque_ligne_porte_des_euros_un_nom_et_une_raison(self):
        ligne = bilan([FauxTrade("TRXUSD", -0.42,
                                 "stop temporel : 180 min sans progression")])[1]
        self.assertIn("-0.42", ligne)
        self.assertIn("Tron", ligne)
        self.assertIn("3 heures", ligne)


if __name__ == "__main__":
    unittest.main()
