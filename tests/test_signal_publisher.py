"""La publication vers l'application ne doit jamais gener le trading.

Trois choses sont verrouillees ici, dans l'ordre d'importance :

1. Supabase injoignable => le robot continue et rien n'est perdu.
2. Un signal publie n'est jamais reecrit.
3. Un signal part avec tous ses champs, et son texte est lisible.
"""

from __future__ import annotations

import json
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from gold_bot.signal_publisher import (SignalPublie, SignalPublisher,
                                       SupabaseIndisponible,
                                       calculer_risk_reward,
                                       conviction_depuis_score, nom_courant,
                                       paire_lisible, rediger_rationale)


class ClientFactice:
    """Un Supabase de laboratoire : on lui dit quand tomber en panne."""

    def __init__(self, en_panne: bool = False) -> None:
        self.en_panne = en_panne
        self.inserts: list = []
        self.patchs: list = []

    def inserer(self, table, ligne):
        if self.en_panne:
            raise SupabaseIndisponible("panne simulee")
        self.inserts.append((table, ligne))
        return [ligne]

    def modifier(self, table, filtre, champs):
        if self.en_panne:
            raise SupabaseIndisponible("panne simulee")
        self.patchs.append((table, filtre, champs))
        return [champs]


def _signal(ref: str = "pos-1") -> SignalPublie:
    return SignalPublie(
        reference=ref, pair="BTC/EUR", side="buy",
        entry_price=58420.0, stop_loss=56100.0, take_profit_1=63000.0,
        risk_reward=calculer_risk_reward(58420.0, 56100.0, 63000.0),
        position_size_pct=0.6, conviction=72,
        rationale=rediger_rationale("BTC/EUR", 10, volume_ratio=1.4),
    )


class TestUnSignalPartAvecTousSesChamps(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.client = ClientFactice()
        self.pub = SignalPublisher(
            client=self.client,
            fichier_file=Path(self.tmp.name) / "file.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tous_les_champs_de_la_table_sont_renseignes(self):
        self.assertTrue(self.pub.publier_ouverture(_signal()))
        table, ligne = self.client.inserts[0]
        self.assertEqual(table, "signals")
        for champ in ("reference", "pair", "side", "entry_price", "stop_loss",
                      "take_profit_1", "risk_reward", "position_size_pct",
                      "conviction", "rationale", "status", "macro_flag",
                      "published_at"):
            self.assertIn(champ, ligne, f"champ manquant : {champ}")

    def test_la_conviction_est_toujours_presente_car_NOT_NULL_en_base(self):
        # Un signal sans score connu doit quand meme s'inserer : la colonne
        # est NOT NULL, une absence ferait echouer l'insert en silence.
        s = _signal()
        s.conviction = None
        self.pub.publier_ouverture(s)
        self.assertEqual(self.client.inserts[0][1]["conviction"], 0)

    def test_la_date_de_publication_est_posee(self):
        self.pub.publier_ouverture(_signal())
        self.assertIsNotNone(self.client.inserts[0][1]["published_at"])

    def test_le_mode_brouillon_laisse_la_date_nulle(self):
        # Un brouillon reste invisible de l'application ET modifiable.
        self.pub.publier_ouverture(_signal(), brouillon=True)
        self.assertIsNone(self.client.inserts[0][1]["published_at"])

    def test_le_format_de_paire_respecte_la_contrainte_de_la_base(self):
        import re
        motif = re.compile(r"^[A-Z0-9]{2,12}/[A-Z]{3,5}$")
        for symbole, devise in [("BTCEUR", "EUR"), ("LINKUSD", "USD"),
                                ("1INCHEUR", "EUR"), ("PEPEEUR", "EUR")]:
            self.assertRegex(paire_lisible(symbole, devise), motif)

    def test_le_symbole_interne_finit_toujours_en_usd_meme_coteEUR(self):
        # Le robot achete sur Bitvavo au comptant (EUR), mais son symbole
        # interne garde le suffixe USD par convention de nommage. Sans
        # traiter ce cas, chaque signal reel partait sous "TRXUSD/EUR"
        # au lieu de "TRX/EUR" -- toujours valide pour la contrainte de
        # la base, jamais lisible pour l'utilisateur.
        self.assertEqual(paire_lisible("TRXUSD", "EUR"), "TRX/EUR")
        self.assertEqual(paire_lisible("1INCHUSD", "EUR"), "1INCH/EUR")
        # La devise reelle reste prioritaire quand elle correspond deja.
        self.assertEqual(paire_lisible("BTCEUR", "EUR"), "BTC/EUR")
        self.assertEqual(paire_lisible("LINKUSD", "USD"), "LINK/USD")


class TestLeTextePourLUtilisateur(unittest.TestCase):

    def test_pas_un_mot_de_jargon(self):
        texte = rediger_rationale("BTC/EUR", 10, volume_ratio=1.4).lower()
        for mot in ("atr", "donchian", "canal", " r ", "multiple",
                    "drawdown", "sharpe", "quorum"):
            self.assertNotIn(mot, texte, f"jargon detecte : {mot!r}")

    def test_aucune_promesse_de_gain(self):
        # Interdit par le prompt 9 et par la conformite Play Store.
        for etage in (1, 2):
            texte = rediger_rationale("ETH/EUR", 10, etage=etage).lower()
            for promesse in ("garanti", "assure", "certain", "va monter",
                             "profit garanti", "sans risque"):
                self.assertNotIn(promesse, texte)

    def test_deux_a_quatre_phrases(self):
        # Une quatrieme phrase (14 sept.) decrit ce qui definit la
        # crypto -- SOL en a une fiche dediee, elle apparait toujours.
        texte = rediger_rationale("SOL/EUR", 10, volume_ratio=1.4)
        phrases = [p for p in texte.split(".") if p.strip()]
        self.assertIn(len(phrases), (2, 3, 4), f"{len(phrases)} phrases : {texte}")

    def test_la_base_exige_au_moins_vingt_caracteres(self):
        # check (length(btrim(rationale)) >= 20) dans la migration.
        self.assertGreaterEqual(len(rediger_rationale("XRP/EUR", 10).strip()), 20)

    def test_les_noms_sont_ceux_du_grand_public(self):
        self.assertEqual(nom_courant("BTC/EUR"), "Le bitcoin")
        # Repli sur le symbole quand la crypto n'est pas connue du grand
        # public : mieux vaut « Le PENDLE » qu'une invention.
        self.assertEqual(nom_courant("PENDLE/EUR"), "Le PENDLE")

    def test_un_renfort_de_pyramide_s_explique_differemment(self):
        texte = rediger_rationale("BTC/EUR", 10, etage=3)
        self.assertIn("renfor", texte.lower())

    def test_deux_signaux_sur_la_meme_crypto_ne_se_disent_pas_pareil(self):
        # 14 sept., retour reel : « toujours le meme discours ... essaye
        # de changer, pas repetitif » -- XTZ et BAT recevaient mot pour
        # mot la meme phrase, seul le nom changeait.
        textes = {rediger_rationale("XTZ/EUR", 10, graine=f"pos{i}")
                  for i in range(10)}
        self.assertGreater(len(textes), 1,
            "dix signaux sur la meme crypto donnent tous le meme texte")

    def test_le_meme_signal_redige_deux_fois_donne_le_meme_texte(self):
        # La variation doit venir de la graine, pas du hasard pur : un
        # signal qu'on republierait (retry reseau) ne doit pas changer
        # de formulation en cours de route.
        a = rediger_rationale("SOL/EUR", 10, graine="position-42")
        b = rediger_rationale("SOL/EUR", 10, graine="position-42")
        self.assertEqual(a, b)

    def test_aucune_formulation_ne_double_larticle_du_nom(self):
        # nom_courant() rend toujours "Le X" ou "L'x" -- une ouverture
        # du genre "Le prix de {nom}" produirait "Le prix de Le XTZ".
        for paire in ("BTC/EUR", "ETH/EUR", "XTZ/EUR", "AVAX/EUR"):
            for i in range(30):
                texte = rediger_rationale(paire, 10, graine=f"{paire}{i}").lower()
                self.assertNotIn("de le ", texte)
                self.assertNotIn("de l'", texte)


class TestLesChiffresAffiches(unittest.TestCase):

    def test_le_rapport_est_nul_quand_il_n_y_a_pas_d_objectif(self):
        # LE ROBOT ARME TOURNE SANS OBJECTIF DE PRIX (tp_actif: false).
        # Inventer un rapport « 2 pour 1 » serait un chiffre faux affiche
        # a l'utilisateur — donc None, et l'application n'affiche rien.
        self.assertIsNone(calculer_risk_reward(100.0, 95.0, None))

    def test_le_rapport_se_calcule_sur_la_distance_au_stop(self):
        self.assertAlmostEqual(calculer_risk_reward(100.0, 95.0, 110.0), 2.0)

    def test_la_conviction_part_du_seuil_d_entree_pas_de_zero(self):
        # Le robot n'entre pas sous 0,45. Afficher « 45 sur 100 » pour une
        # entree tout juste acceptee ferait croire a une demi-conviction.
        self.assertEqual(conviction_depuis_score(0.45), 0)
        self.assertEqual(conviction_depuis_score(1.00), 100)
        self.assertEqual(conviction_depuis_score(0.725), 50)


class TestLaPanneNeGenePasLeRobot(unittest.TestCase):

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.chemin = Path(self.tmp.name) / "file.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_supabase_muet_ne_leve_aucune_exception(self):
        pub = SignalPublisher(client=ClientFactice(en_panne=True),
                              fichier_file=self.chemin)
        self.assertFalse(pub.publier_ouverture(_signal()))
        self.assertFalse(pub.publier_cloture("pos-1:1", "closed_tp", 0.0, 4.2))

    def test_ce_qui_n_est_pas_parti_est_rejoue_ensuite(self):
        client = ClientFactice(en_panne=True)
        pub = SignalPublisher(client=client, fichier_file=self.chemin)
        pub.publier_ouverture(_signal())
        pub.publier_cloture("pos-1:1", "closed_tp", 1_700_000_000.0, 4.2)
        self.assertEqual(client.inserts, [])

        client.en_panne = False
        self.assertEqual(pub.rejouer(), 2)
        self.assertEqual(len(client.inserts), 1)
        self.assertEqual(len(client.patchs), 1)
        self.assertEqual(pub.rejouer(), 0, "rejoue deux fois")

    def test_la_file_survit_a_un_redemarrage(self):
        client = ClientFactice(en_panne=True)
        SignalPublisher(client=client, fichier_file=self.chemin) \
            .publier_ouverture(_signal())

        client.en_panne = False
        repris = SignalPublisher(client=client, fichier_file=self.chemin)
        self.assertEqual(repris.rejouer(), 1)

    def test_un_redemarrage_ne_republie_pas_ce_qui_attend_deja(self):
        # Sans cette memoire, un robot relance pendant une panne inserait
        # le meme signal une deuxieme fois — et l'index unique de la base
        # ferait echouer le rattrapage de tout ce qui suit.
        client = ClientFactice(en_panne=True)
        SignalPublisher(client=client, fichier_file=self.chemin) \
            .publier_ouverture(_signal())

        repris = SignalPublisher(client=client, fichier_file=self.chemin)
        repris.publier_ouverture(_signal())
        lignes = [l for l in self.chemin.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lignes), 1)

    def test_l_ordre_est_respecte_au_rattrapage(self):
        # Une cloture qui partirait avant son ouverture ne trouverait
        # aucune ligne a modifier, et le signal resterait actif pour
        # toujours dans l'application.
        client = ClientFactice(en_panne=True)
        pub = SignalPublisher(client=client, fichier_file=self.chemin)
        pub.publier_ouverture(_signal())
        pub.publier_cloture("pos-1:1", "closed_sl", 1.0, -1.5)
        taches = [json.loads(l) for l in self.chemin.read_text().splitlines()
                  if l.strip()]
        self.assertEqual([t["type"] for t in taches], ["ouverture", "cloture"])

    def test_sans_cle_le_publieur_est_inerte(self):
        pub = SignalPublisher(client=None, fichier_file=self.chemin)
        self.assertFalse(pub.actif)
        self.assertFalse(pub.publier_ouverture(_signal()))
        self.assertFalse(self.chemin.exists(), "ecrit alors qu'il est inerte")


class TestUnSignalPublieNEstJamaisReecrit(unittest.TestCase):
    """La regle la plus importante du module.

    Un historique retouchable rend la courbe de performance de
    l'application — et donc l'abonnement qu'elle justifie — sans valeur.
    Le verrou definitif est le declencheur `signals_immuables` en base
    (migration 20260913090000) ; ici on verifie que le robot lui-meme ne
    tente jamais autre chose qu'une cloture.
    """

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.client = ClientFactice()
        self.pub = SignalPublisher(
            client=self.client,
            fichier_file=Path(self.tmp.name) / "file.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_la_cloture_ne_touche_que_trois_champs(self):
        self.pub.publier_ouverture(_signal())
        self.pub.publier_cloture("pos-1:1", "closed_tp", 1_700_000_000.0, 4.2)
        _, filtre, champs = self.client.patchs[0]
        self.assertEqual(filtre, "reference=eq.pos-1:1")
        self.assertEqual(set(champs), {"status", "closed_at", "result_pct"})

    def test_republier_le_meme_signal_ne_fait_rien(self):
        self.pub.publier_ouverture(_signal())
        self.pub.publier_ouverture(_signal())     # prix change entre-temps
        self.assertEqual(len(self.client.inserts), 1)

    def test_un_statut_de_cloture_inconnu_est_refuse(self):
        # « active » n'est pas une cloture : laisser passer rouvrirait un
        # signal ferme.
        with self.assertRaises(ValueError):
            self.pub.publier_cloture("pos-1:1", "active", 0.0, 0.0)

    def test_chaque_etage_de_pyramide_est_un_signal_distinct(self):
        # Un renfort n'est pas une modification du premier achat : c'est
        # une nouvelle ligne, sinon la base la refuserait.
        self.pub.publier_ouverture(_signal("pos-1:1"))
        self.pub.publier_ouverture(_signal("pos-1:2"))
        self.assertEqual(len(self.client.inserts), 2)


class TestLeMoteurPubliePourDeVraiUnePositionReelle(unittest.TestCase):
    """Le 13 septembre, en production : chaque ouverture echouait avec

        'Position' object has no attribute 'position_id'

    parce que `_publier_le_signal` lisait `pos.position_id` alors que le
    champ s'appelle `id` sur `gold_bot.core.Position`. L'erreur etait
    avalee par le `try/except` protecteur (a raison : publier ne doit
    jamais casser un ordre reel), donc RIEN ne remontait sauf un warning
    dans les journaux — aucun test ne construisait de vraie `Position` et
    ne l'envoyait dans le moteur, seulement dans `SignalPublisher`
    directement. Ce test appelle le meme chemin que l'ouverture reelle.
    """

    def setUp(self) -> None:
        import os

        self._env_a_restaurer = {
            cle: os.environ.pop(cle, None)
            for cle in ("BITVAVO_API_KEY", "BITVAVO_API_SECRET",
                        "OKX_API_KEY", "GB_STATE_FILE", "GB_TRADES_FILE")
        }
        self._tmp = TemporaryDirectory()
        self._cwd_avant = os.getcwd()
        os.chdir(self._tmp.name)

    def tearDown(self) -> None:
        import os

        os.chdir(self._cwd_avant)
        self._tmp.cleanup()
        for cle, valeur in self._env_a_restaurer.items():
            if valeur is not None:
                os.environ[cle] = valeur

    def _moteur(self):
        from gold_bot.engine import TradingEngine
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load()
        cfg.engine.broker = "bitvavo"
        cfg.engine.dry_run = True
        return TradingEngine(cfg)

    def test_ouvrir_une_vraie_position_ne_leve_pas_et_publie(self):
        from gold_bot.core import Position, Side

        moteur = self._moteur()
        client = ClientFactice()
        moteur.publisher = SignalPublisher(
            client=client, fichier_file=Path("signaux_test.jsonl"))

        pos = Position(
            id="TRXUSD", symbol="TRXUSD", side=Side.BUY, volume=140.106203,
            entry_price=0.29334, stop_loss=0.28634, take_profit=0.0,
            opened_at=time.time(),
        )
        ev = SimpleNamespace(
            symbol="TRXUSD", side=Side.BUY, score=0.62, threshold=0.45,
            setup="donchian_cassure", components=[])
        sizing = SimpleNamespace(risk_pct=0.51, risk_amount=1.18, lots=pos.volume)

        # Ne doit lever aucune exception : c'est exactement ce que le
        # try/except de _publier_le_signal masquait le 13 septembre.
        moteur._publier_le_signal(ev, pos, sizing)

        self.assertEqual(len(client.inserts), 1, "rien n'a ete publie")
        table, ligne = client.inserts[0]
        self.assertEqual(table, "signals")
        self.assertEqual(ligne["reference"], "TRXUSD:1")
        # La devise exacte depend de l'univers charge (ici minimal, sans
        # fetch Bitvavo reel) -- voir test_le_symbole_interne_finit_toujours_en_usd_meme_coteEUR
        # pour la preuve precise du format "TRX/EUR".
        self.assertTrue(ligne["pair"].startswith("TRX/"))
        self.assertEqual(ligne["side"], "buy")
        self.assertIsNotNone(ligne["published_at"])


class TestLeBeneficeReelEstPublie(unittest.TestCase):
    """Le chiffre exact, pose UNE fois, frais deduits.

    L'application reconstituait le benefice a l'arrivee, a partir du
    pourcentage publie : `volume x prix d'achat x result_pct`. C'est le
    gain du PRIX, sans les frais que le robot a pourtant payes.

    Releve par l'operateur le 22 septembre en comparant ses ecrans au
    serveur : la demo 2 affichait 128,28 EUR encaisses pour 117,08
    reels. Sept trades suffisaient a creuser 11,20 EUR — 7,93 de frais
    et 3,27 d'arrondis sur les pourcentages.
    """

    def setUp(self) -> None:
        self._dossier = TemporaryDirectory()
        self.addCleanup(self._dossier.cleanup)
        self.chemin = Path(self._dossier.name) / "file.jsonl"

    def test_le_profit_part_avec_la_cloture(self):
        client = ClientFactice()
        pub = SignalPublisher(client=client, fichier_file=self.chemin)
        pub.publier_cloture("pos-1:1", "closed_tp", 1_700_000_000.0, 4.2,
                            profit_eur=36.55)
        _, _, champs = client.patchs[0]
        self.assertEqual(champs["profit_eur"], 36.55)

    def test_sans_profit_la_colonne_n_est_pas_envoyee(self):
        """Une cloture sans montant ne doit pas ecrire NULL par-dessus.

        Les appelants qui ne le passent pas encore ne doivent rien
        casser : l'absence de cle laisse la colonne telle quelle.
        """
        client = ClientFactice()
        pub = SignalPublisher(client=client, fichier_file=self.chemin)
        pub.publier_cloture("pos-1:1", "closed_tp", 1_700_000_000.0, 4.2)
        _, _, champs = client.patchs[0]
        self.assertNotIn("profit_eur", champs)

    def test_une_pyramide_ne_compte_son_benefice_QU_UNE_FOIS(self):
        """Le piege que cette colonne aurait cree sans precaution.

        Une pyramide publie une ligne PAR ETAGE et elles se ferment
        toutes ensemble. Si chacune portait le benefice entier, une
        pyramide a quatre etages serait comptee quatre fois par
        l'application, qui additionne les lignes. L'etage 1 porte le
        montant, les suivants zero.
        """
        client = ClientFactice()
        pub = SignalPublisher(client=client, fichier_file=self.chemin)
        montants = []
        for etage in range(1, 5):
            pub.publier_cloture(f"pos-9:{etage}", "closed_tp",
                                1_700_000_000.0, 4.2,
                                profit_eur=120.0 if etage == 1 else 0.0)
        for _, _, champs in client.patchs:
            montants.append(champs["profit_eur"])
        self.assertEqual(montants, [120.0, 0.0, 0.0, 0.0])
        self.assertEqual(sum(montants), 120.0,
                         "le benefice d'une pyramide est compte plusieurs fois")


if __name__ == "__main__":
    unittest.main()
