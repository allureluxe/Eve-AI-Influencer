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
import logging
import os
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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="robot.demo.json")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
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
    os.environ["GB_STATE_FILE"] = "data/state-demo.json"
    os.environ["GB_TRADES_FILE"] = "data/trades-demo.jsonl"
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
    os.environ["GB_OBJECTIVE_FILE"] = "data/objectives-demo.json"
    os.environ["GB_JOURNAL_FILE"] = "data/journal-demo.jsonl"
    os.environ["GB_OUTBOX_FILE"] = "data/outbox-demo.jsonl"

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
    # demo EN DIRECT dans l'app, notifications comprises. Tout le code cote
    # Python est pret (`SignalPublisher.est_demo`, `AlluxeBotChannel(est_demo=True)`
    # plus bas) mais la colonne `is_demo` elle-meme
    # (supabase/migrations/20260918234500_marquer_demo.sql) n'est PAS ENCORE
    # appliquee a la base reelle -- bloque sur un jeton
    # SUPABASE_ACCESS_TOKEN expire. Republier maintenant enverrait
    # `is_demo` a une table qui ne connait pas cette colonne. Les deux
    # lignes ci-dessous restent donc vides JUSQU'A CE QUE la migration soit
    # confirmee appliquee -- a retirer a ce moment-la, pas avant.
    os.environ["SUPABASE_URL"] = ""
    os.environ["SUPABASE_SERVICE_KEY"] = ""

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

    from gold_bot.notifiers import (AlluxeBotChannel, ConsoleChannel, FileChannel,
                                    FirebasePushChannel, TelegramChannel)
    canaux_demo = NotifierDemo([
        ConsoleChannel(), FileChannel(),
        TelegramChannel(), AlluxeBotChannel(est_demo=True), FirebasePushChannel(),
    ])
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

    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
