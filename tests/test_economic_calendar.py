"""L'agenda affiche doit decrire ce que le robot fait REELLEMENT.

Le defaut que ces tests empechent est celui que ce depot a deja
rencontre cinq fois : un texte, un chiffre ou une mesure qui decrit
autre chose que le code qui tourne. Ici la consequence serait directe —
l'application promet « aucun achat entre 14h15 et 15h00 », le robot
achete a 14h50, et l'utilisateur ne fait plus confiance a rien.
"""

from __future__ import annotations

import datetime as dt
import time
import unittest

from gold_bot.economic_calendar import (AgendaEconomique, redaction_politique,
                                        traduire)
from gold_bot.news import (IMPACT_HIGH, IMPACT_LOW, IMPACT_MEDIUM,
                           EconomicEvent, NewsFilter)


def _filtre(evenements) -> NewsFilter:
    """Un filtre nourri a la main, sans appel reseau."""
    f = NewsFilter(sources=[])
    f.events = sorted(evenements, key=lambda e: e.ts)
    f._last_refresh = time.time()      # empeche tout rafraichissement
    return f


def _ev(quand: float, titre: str = "US CPI", impact: str = IMPACT_HIGH,
        devise: str = "USD") -> EconomicEvent:
    return EconomicEvent(ts=quand, title=titre, currency=devise, impact=impact)


class TestLaTraduction(unittest.TestCase):

    def test_les_noms_connus_deviennent_du_francais(self):
        self.assertEqual(traduire("Non-Farm Payrolls"), "Emploi americain")
        self.assertEqual(traduire("FOMC Rate Decision"),
                         "Decision de taux de la Fed")

    def test_le_nom_le_plus_precis_gagne(self):
        # « core cpi » contient « cpi » : sans tri par longueur, la
        # traduction generique ecraserait la precise.
        self.assertEqual(traduire("US Core CPI YoY"),
                         "Inflation americaine (hors energie)")

    def test_un_nom_inconnu_reste_tel_quel(self):
        # Inventer une traduction est pire que d'afficher l'anglais.
        self.assertEqual(traduire("Tankan Large Manufacturers Index"),
                         "Tankan Large Manufacturers Index")


class TestLaRegleAfficheeSuitLeRobot(unittest.TestCase):
    """Le point le plus important du module."""

    def test_les_heures_annoncees_sont_celles_de_la_configuration(self):
        f = _filtre([])
        f.config.high_before = 20
        f.config.high_after = 20
        f.config.allow_breakout = False
        # 14h30 heure de Paris, un jour d'hiver (UTC+1).
        quand = dt.datetime(2026, 1, 15, 13, 30, tzinfo=dt.timezone.utc).timestamp()
        texte = redaction_politique(_ev(quand), f)
        self.assertIn("14h10", texte)      # -20 min
        self.assertIn("14h50", texte)      # +20 min

    def test_changer_la_configuration_change_le_texte(self):
        # LA GARANTIE ANTI-DERIVE : si un jour quelqu'un elargit la
        # fenetre du robot, l'application le dit sans qu'on y touche.
        quand = dt.datetime(2026, 1, 15, 13, 30, tzinfo=dt.timezone.utc).timestamp()
        f = _filtre([])
        f.config.allow_breakout = False
        f.config.high_before, f.config.high_after = 20, 20
        avant = redaction_politique(_ev(quand), f)
        f.config.high_before, f.config.high_after = 45, 60
        apres = redaction_politique(_ev(quand), f)
        self.assertNotEqual(avant, apres)
        self.assertIn("13h45", apres)
        self.assertIn("15h30", apres)

    def test_la_reprise_en_cassure_est_annoncee_quand_elle_est_armee(self):
        # Le robot peut racheter apres l'impulsion. Ne pas le dire
        # ferait passer un achat legitime pour une regle violee.
        quand = dt.datetime(2026, 1, 15, 13, 30, tzinfo=dt.timezone.utc).timestamp()
        f = _filtre([])
        f.config.allow_breakout = True
        self.assertIn("mouvement franc", redaction_politique(_ev(quand), f))

    def test_le_texte_promet_de_ne_pas_fermer_les_positions_ouvertes(self):
        # Exigence de la specification, et comportement reel du filtre :
        # il bloque les ENTREES, il ne ferme rien.
        quand = time.time() + 3600
        self.assertIn("ne sont pas fermees",
                      redaction_politique(_ev(quand), _filtre([])))

    def test_un_evenement_sans_effet_le_dit(self):
        texte = redaction_politique(
            _ev(time.time(), "Some Minor Index", IMPACT_LOW), _filtre([]))
        self.assertIn("Sans effet", texte)


class TestLeSilenceAutourDesAnnonces(unittest.TestCase):

    def test_le_robot_est_bloque_pendant_la_fenetre(self):
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre([_ev(maintenant + 300)]))
        agenda.filtre.config.allow_breakout = False
        self.assertTrue(agenda.is_blackout(
            dt.datetime.fromtimestamp(maintenant, dt.timezone.utc)))

    def test_le_robot_est_libre_loin_de_toute_annonce(self):
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre([_ev(maintenant + 86400)]))
        self.assertFalse(agenda.is_blackout(
            dt.datetime.fromtimestamp(maintenant, dt.timezone.utc)))

    def test_une_panne_d_agenda_ne_fige_pas_le_robot(self):
        # UN AGENDA EST UN CONFORT, PAS UNE PROTECTION VITALE.
        # Refuser par prudence quand Finnhub tousse arreterait le robot
        # pour une raison qui n'a rien a voir avec le marche.
        class Cassé(NewsFilter):
            def check(self, *a, **k):
                raise RuntimeError("fournisseur muet")

        agenda = AgendaEconomique(filtre=Cassé(sources=[]))
        self.assertFalse(agenda.is_blackout())


class TestCeQuiRemonteVersLApplication(unittest.TestCase):

    def test_seuls_les_etats_unis_et_la_zone_euro_sont_retenus(self):
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre([
            _ev(maintenant + 3600, "US CPI", IMPACT_HIGH, "USD"),
            _ev(maintenant + 7200, "ECB Rate", IMPACT_HIGH, "EUR"),
            _ev(maintenant + 9000, "Tankan", IMPACT_HIGH, "JPY"),
        ]))
        pays = {l["country"] for l in agenda.evenements(maintenant=maintenant)}
        self.assertEqual(pays, {"Etats-Unis", "Zone euro"})

    def test_les_evenements_sans_impact_sont_ecartes(self):
        # Trente lignes par jour rendent l'agenda illisible, et un
        # agenda illisible n'est pas consulte.
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre([
            _ev(maintenant + 3600, "US CPI", IMPACT_HIGH, "USD"),
            _ev(maintenant + 3700, "Minor Thing", IMPACT_LOW, "USD"),
        ]))
        lignes = agenda.evenements(maintenant=maintenant)
        self.assertEqual(len(lignes), 1)

    def test_chaque_ligne_porte_les_champs_de_la_table(self):
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre(
            [_ev(maintenant + 3600, "Non-Farm Payrolls")]))
        ligne = agenda.evenements(maintenant=maintenant)[0]
        for champ in ("event_time", "name_fr", "country", "impact",
                      "eve_policy", "actual", "forecast", "previous"):
            self.assertIn(champ, ligne)
        self.assertEqual(ligne["name_fr"], "Emploi americain")
        self.assertEqual(ligne["impact"], "high")

    def test_le_passe_n_est_pas_republie(self):
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre([
            _ev(maintenant - 7200, "US CPI"),
            _ev(maintenant + 7200, "FOMC Rate Decision"),
        ]))
        lignes = agenda.evenements(maintenant=maintenant)
        self.assertEqual([l["name_fr"] for l in lignes],
                         ["Decision de taux de la Fed"])

    def test_les_doublons_de_fournisseurs_sont_fusionnes(self):
        # Finnhub dit « US CPI », FMP dit « CPI y/y » : meme annonce.
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre([
            _ev(maintenant + 3600, "US CPI m/m", IMPACT_MEDIUM),
            _ev(maintenant + 3660, "CPI y/y", IMPACT_MEDIUM),
        ]))
        self.assertEqual(len(agenda.evenements(maintenant=maintenant)), 1)


class TestLeDrapeauMacroSurLesSignaux(unittest.TestCase):

    def test_une_annonce_forte_dans_l_horizon_est_signalee(self):
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre(
            [_ev(maintenant + 6 * 3600, "FOMC Rate Decision")]))
        self.assertIsNotNone(
            agenda.evenement_fort_a_venir(maintenant=maintenant))

    def test_rien_a_signaler_quand_l_agenda_est_calme(self):
        maintenant = time.time()
        agenda = AgendaEconomique(filtre=_filtre(
            [_ev(maintenant + 10 * 86400, "FOMC Rate Decision")]))
        self.assertIsNone(
            agenda.evenement_fort_a_venir(maintenant=maintenant))


if __name__ == "__main__":
    unittest.main()
