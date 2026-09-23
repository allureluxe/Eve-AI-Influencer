#!/usr/bin/env python3
"""Lance la simulation "avant de deposer" : 500 EUR virtuels, vraies
cotations Bitvavo en direct, aucun ordre reel envoye.

    python3 run_demo.py --config robot.demo.json

Cree le 18 sept. 2026 a la demande de l'operateur, pour valider la
strategie D1 Turtle sur un capital cible (500 EUR) avant de l'engager
reellement -- le compte reel etant vide a ce moment-la (retraits du
16 sept.).

Meme moteur (DualScalpingEngine) et meme configuration strategie/risque
que robot.bitvavo.json -- seul le lieu d'execution change (PaperBroker,
capital purement virtuel). Journal et etat FORCES vers des fichiers
dedies (data/state-demo.json, data/trades-demo.jsonl, voir plus bas
pourquoi ce n'est pas le suffixe d'instance habituel) : aucun risque de
melanger cette simulation avec l'echantillon reel.

Toutes les notifications (Telegram compris) sont prefixees "[DEMO]"
pour qu'elles ne se confondent jamais, dans le meme salon Telegram,
avec une alerte du robot reel.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import threading
import time
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gold_bot.engine as engine_module
from gold_bot.brokers.paper import PaperBroker
from gold_bot.dual_scalping_engine import DualScalpingEngine
from gold_bot.notifiers import Notification, Notifier
from gold_bot.settings import BotConfig
from gold_bot.universe import ACTIFS_PAR_SYMBOLE


class PaperBrokerCryptoBitvavo(PaperBroker):
    """Le simulateur n'a pas de methode `supports()` -- c'est volontaire
    (backtest.py veut pouvoir rejouer n'importe quel univers qu'on lui
    donne). Sans elle, `_filtrer_univers_sur_le_broker` (qui retire le
    forex/l'or/les indices pour le vrai BitvavoBroker) ne s'applique
    jamais, et la simulation "500 EUR sur Bitvavo" se retrouve a scanner
    XAUUSD/AUDUSD/USDJPY en plus des cryptos -- constate le 18 sept. lors
    du premier essai en direct. Cette sous-classe, LOCALE A CE LANCEUR,
    ne fait strictement rien d'autre que declarer quels symboles sont
    des cryptos (comme le ferait le vrai broker Bitvavo, sans avoir
    besoin de vraies cles ou d'un appel reseau pour ca)."""

    def supports(self, symbol: str) -> bool:
        return symbol.upper() in ACTIFS_PAR_SYMBOLE


# Meme technique que run_bitvavo.py/run_pionex.py : on ne touche pas au
# fichier partage gold_bot/engine.py ni gold_bot/brokers/paper.py, on
# remplace juste le nom que `_build_broker()` va resoudre au moment de
# construire le broker paper -- isole a ce seul processus.
engine_module.PaperBroker = PaperBrokerCryptoBitvavo


class NotifierDemo(Notifier):
    """Meme diffusion que Notifier, avec un prefixe "[DEMO]" systematique
    -- capital virtuel, mais l'operateur doit pouvoir le distinguer d'un
    coup d'oeil d'une vraie alerte, dans le meme salon Telegram."""

    def send(self, note: Notification, throttle_key: str = "",
              throttle_seconds: float = 0.0) -> None:
        if not note.title.startswith("[DEMO]"):
            note.title = f"[DEMO] {note.title}"
        super().send(note, throttle_key=throttle_key, throttle_seconds=throttle_seconds)


def _publier_la_fiche_du_compte(compte: str, cfg, capital: float | None = None,
                                balance: float | None = None) -> None:
    """Depose la methode et le capital de ce compte dans `alluxe_bot_comptes`.

    ELLE SE REPUBLIE EN BOUCLE, ET C'EST LE POINT.
    =============================================

    Elle n'etait appelee qu'au DEMARRAGE. L'application declare un compte
    « arrete » quand sa fiche n'a pas ete rafraichie depuis un quart
    d'heure -- donc les deux robots etaient affiches arretes en
    permanence alors qu'ils tournaient. Constate le 21 septembre :

        demo    vu_le = la veille 13h14   (20 heures)
        demo2   vu_le = 05h43             (3 h 30)

    Un voyant qui est toujours rouge ne dit plus rien : on cesse de le
    regarder, et le jour ou un robot tombe vraiment, personne ne le voit.

    `capital` remplit la colonne qui restait vide : l'operateur avait
    demande « le nom de la methode utilise avec le capital en direct en
    euro », et seul le capital de DEPART etait publie.

    Ne leve jamais : l'affichage ne doit pas pouvoir empecher ni
    interrompre une simulation.

    NOTE DU 21 SEPTEMBRE : la table `alluxe_bot_comptes` n'a PAS de
    colonne `capital_eur` (colonnes reelles : capital_depart, compte,
    cree_le, methode, resume_methode, vu_le). Le capital vivant y a donc
    ete retire -- l'application le reconstitue de son cote. L'ajouter
    serait une modification de schema pour un besoin non demontre ; a
    reconsiderer seulement si les onglets NON ouverts affichent un
    capital faux (ils ignorent aujourd'hui leurs positions ouvertes).
    """
    import urllib.request
    from gold_bot.methode import phrase_methode, resume_methode

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        return
    corps = {
        "compte": compte,
        "resume_methode": resume_methode(cfg),
        "methode": phrase_methode(cfg),
        "capital_depart": float(getattr(cfg.engine, "start_balance", 0.0) or 0.0),
        "vu_le": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    # Depuis la migration du 24 septembre, ces deux champs sont la
    # source de verite de l'application : equity vivante et solde liquide.
    # Au premier battement, avant que le moteur soit construit, le compte
    # vaut exactement son capital de depart et aucun gain n'est encaisse.
    if capital is not None:
        corps["capital_eur"] = round(float(capital), 2)
    if balance is not None:
        depart = float(getattr(cfg.engine, "start_balance", 0.0) or 0.0)
        corps["encaisse_eur"] = round(float(balance) - depart, 2)
    else:
        corps["encaisse_eur"] = 0.0
    # Les colonnes capital_eur/encaisse_eur sont ajoutees par
    # supabase/migrations/20260924000000_capital_comptes_demo.sql.
    # Tant que la migration n'est pas appliquee en base, la publication
    # echouera proprement dans le try/except au lieu d'arreter le moteur.
    corps = json.dumps(corps).encode()
    try:
        requete = urllib.request.Request(
            f"{url}/rest/v1/alluxe_bot_comptes", data=corps,
            headers={"apikey": cle, "authorization": f"Bearer {cle}",
                     "content-type": "application/json",
                     "prefer": "resolution=merge-duplicates"},
            method="POST")
        urllib.request.urlopen(requete, timeout=20).close()
        logging.info("fiche du compte « %s » publiee", compte)
    except Exception as exc:                                  # noqa: BLE001
        logging.warning("fiche du compte non publiee : %s", str(exc)[:160])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="robot.demo.json")
    # PLUSIEURS COMPTES DEMO EN PARALLELE.
    #
    # Demande de l'operateur le 20 sept. : « une fois la methode trouvee
    # tu vas creer un 2e compte demo sur l'appli avec 3 300 EUR ». C'est
    # la bonne facon de comparer deux methodes : les faire tourner sur le
    # MEME marche, aux MEMES heures. Les comparer l'une apres l'autre
    # melangerait l'effet du reglage et celui du marche.
    #
    # Le nom du compte suffixe TOUS les fichiers et marque chaque ligne
    # publiee. Sans ca, deux robots se marcheraient dessus exactement
    # comme la demo l'a fait avec le robot reel le 18 septembre.
    p.add_argument("--compte", default="demo",
                   help="nom du compte demo : demo, demo2... "
                        "Suffixe les fichiers et marque les publications.")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()

    compte = args.compte.strip().lower()
    if not compte.startswith("demo"):
        print(f"nom de compte refuse : « {compte} » ne commence pas par "
              "« demo ». C'est le garde-fou qui empeche cette simulation "
              "d'ecrire dans les fichiers du robot REEL.")
        return 2
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-24s %(message)s",
        datefmt="%H:%M:%S",
    )

    # FORCE des fichiers dedies -- ASSIGNATION DIRECTE, PAS setdefault().
    #
    # Trouve le 18 sept. de la pire facon, EN DEUX TEMPS :
    #
    # 1. `chemin_par_instance()` continue de lire (et donc d'ECRIRE) le
    #    fichier COMMUN tant que le fichier suffixe n'existe pas encore --
    #    pense pour migrer un robot deja en production vers plusieurs
    #    instances sans perdre son historique, PAS pour une simulation
    #    neuve. Le tout premier essai de ce script a ecrit ses positions
    #    et son capital virtuel (500 EUR) directement dans data/state.json,
    #    celui du robot reel -- 3 fausses positions et des compteurs faux
    #    a nettoyer a la main.
    #
    # 2. Le correctif immediat (`os.environ.setdefault(...)`) n'a RIEN
    #    change : `.env` (partage avec robot-dual-live.service via
    #    EnvironmentFile=) definit deja GB_STATE_FILE/GB_TRADES_FILE, et
    #    setdefault() n'ecrase jamais une valeur deja presente. La
    #    simulation a continue d'ecrire dans le fichier reel une 2e fois
    #    (account_reference/peak_equity ecrases a 500.0) avant que ce soit
    #    remarque. Seule une AFFECTATION DIRECTE, inconditionnelle,
    #    garantit que ce script n'ecrit jamais que ses propres fichiers --
    #    quoi que contienne .env ou l'environnement herite.
    os.environ["GB_STATE_FILE"] = f"data/state-{compte}.json"
    os.environ["GB_TRADES_FILE"] = f"data/trades-{compte}.jsonl"
    # 3e fuite trouvee le meme soir : `ObjectiveTracker` (gold_bot/objectives.py)
    # a SON PROPRE fichier, `data/objectives.json`, jamais isole non plus --
    # la demo y a ecrit un "objectif hebdomadaire" fictif de +170 EUR par-
    # dessus celui, reel, du robot (restaure a la main : -14,72 EUR sur 17
    # trades). Sans l'isoler, ce chiffre fictif aurait fini archive dans
    # l'historique REEL du robot au prochain changement de semaine ISO, et
    # aurait meme pu declencher une PROMOTION DE PALIER DE RISQUE reelle sur
    # un objectif entierement invente. Journal de notifications et boite
    # d'envoi isoles aussi par la meme occasion, par prudence (moins
    # critique -- ce ne sont que des lignes de texte, jamais lues pour une
    # decision -- mais autant ne plus jamais devoir chercher une 4e fuite).
    os.environ["GB_OBJECTIVE_FILE"] = f"data/objectives-{compte}.json"
    os.environ["GB_JOURNAL_FILE"] = f"data/journal-{compte}.jsonl"
    os.environ["GB_OUTBOX_FILE"] = f"data/outbox-{compte}.jsonl"
    # Le moteur lit ce nom pour marquer chaque ligne publiee. Passe par
    # l'environnement parce que `SignalPublisher` se construit tout seul
    # depuis `depuis_env()`, loin d'ici.
    os.environ["GB_COMPTE_DEMO"] = compte

    # 5e fuite, la plus visible, trouvee et d'abord colmatee en coupant
    # purement et simplement SUPABASE_URL/KEY pour ce processus :
    # `TradingEngine` publie CHAQUE ouverture/cloture de position vers la
    # table Supabase `signals` (SignalPublisher) et vers `alluxe_bot_alertes`
    # (AlluxeBotChannel) -- les memes tables que l'application publique
    # (Allure) et Alluxbot. Sans distinction d'instance, la simulation a
    # publie ses 10 positions virtuelles comme de vraies positions du robot
    # -- l'operateur a vu une position fermee a 600 % de "benefice" dans
    # l'app et a su que ca ne collait pas. 21 lignes nettoyees a la main.
    #
    # Coupure devenue OBSOLETE le meme soir : l'operateur veut suivre la
    # demo EN DIRECT dans l'app, notifications comprises. La colonne
    # `is_demo` (supabase/migrations/20260918234500_marquer_demo.sql) est
    # CONFIRMEE appliquee en base le 19 sept. (verifie via
    # information_schema.columns avant de republier) -- SUPABASE_URL/KEY
    # ne sont donc plus vides ici : le processus herite de .env comme le
    # robot reel, et chaque ligne qu'il publie porte `is_demo=true` (voir
    # `SignalPublisher.est_demo` et `AlluxeBotChannel(est_demo=True)` plus
    # bas), jamais confondue avec le reel par l'application.

    cfg = BotConfig.load(args.config)
    if cfg.engine.broker != "paper":
        logging.error("run_demo.py exige engine.broker=\"paper\" -- "
                       "%s en porte un autre, refus par securite.", args.config)
        return 2
    problems = cfg.validate()
    if problems:
        for pmsg in problems:
            logging.error("configuration : %s", pmsg)
        return 2

    from gold_bot.notifiers import (AlluxeBotChannel, ConsoleChannel,
                                    FileChannel, FirebasePushChannel)
    canaux_demo = NotifierDemo([
        ConsoleChannel(), FileChannel(),
        # Telegram retire le 19 sept. (voir notifiers.py) : l'operateur
        # supprime le compte, tout passe par l'application.
        AlluxeBotChannel(est_demo=True, compte=compte), FirebasePushChannel(),
    ])
    # CHAQUE COMPTE DIT CE QU'IL FAIT.
    #
    # L'application affiche un onglet par simulation, avec le nom de la
    # methode. Elle ne lit pas `robot.demo2.json` -- et elle ne doit
    # surtout pas recopier la description : c'est ce qui avait fait
    # afficher « canal 20 jours » pendant une semaine alors que le robot
    # tournait a 10. Le robot publie donc sa propre fiche, deduite de la
    # configuration qu'il vient reellement de charger.
    _publier_la_fiche_du_compte(compte, cfg)

    engine = DualScalpingEngine(cfg, notifier=canaux_demo)

    # Filet de securite : si un futur changement (ici ou dans
    # gold_bot/state.py / objectives.py) reintroduit un chemin partage, on
    # s'arrete tout de suite plutot que d'ecrire encore dans un fichier du
    # robot reel. "demo" doit apparaitre dans chacun des chemins reels.
    for nom, chemin in (("etat", engine.store.path), ("journal", engine.journal.path),
                        ("objectifs", engine.objectives.state_file)):
        if "demo" not in os.path.basename(chemin):
            logging.error(
                "SECURITE : le fichier de %s (%s) n'est pas isole a la "
                "simulation -- arret avant d'ecrire quoi que ce soit.",
                nom, chemin)
            return 2
    if engine.publisher.actif and not engine.publisher.est_demo:
        logging.error(
            "SECURITE : le publieur Supabase (signals) n'est pas marque "
            "is_demo -- la simulation publierait ses positions comme si "
            "elles etaient reelles. Arret.")
        return 2

    # LA FICHE SE REPUBLIE TOUTES LES CINQ MINUTES.
    #
    # `engine.run()` est une boucle bloquante : sans ce fil de fond, la
    # fiche ne serait publiee qu'au demarrage, et l'application
    # declarerait le compte arrete un quart d'heure plus tard. Cinq
    # minutes laissent trois battements avant que le voyant passe au
    # rouge -- il ne s'allumera donc que pour un vrai arret.
    #
    # Fil DEMON : il ne doit jamais retenir le processus a l'extinction.
    # Et il n'appelle que `_publier_la_fiche_du_compte`, qui avale ses
    # propres erreurs : un probleme d'affichage ne peut pas interrompre
    # une simulation en cours.
    def _battement() -> None:
        while True:
            time.sleep(300)
            try:
                compte_simule = engine.broker.account()
                capital = compte_simule.equity
                balance = compte_simule.balance
            except Exception:                                 # noqa: BLE001
                capital = None
                balance = None
            _publier_la_fiche_du_compte(compte, cfg, capital, balance)

    threading.Thread(target=_battement, daemon=True,
                     name=f"fiche-{compte}").start()

    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
