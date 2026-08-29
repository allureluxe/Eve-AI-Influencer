"""Pionex, Binance, MoonX, OKX ont ete retires. Ils ne doivent pas revenir.

Le 29 aout, l'operateur : « supprime tout ce qui touche a Pionex, Binance,
MoonX etc. Je veux qu'il reste juste Bitvavo et IBKR, tout le reste tu
effaces pour que le bot ne bloque pas a cause d'anciennes plateformes
qu'on a essaye d'integrer. »

Le probleme n'etait pas leur presence en soi, c'est qu'il en restait
ASSEZ pour casser un demarrage sans qu'on comprenne pourquoi : des imports
vers des modules a moitie retires, des configurations livrees nommant un
broker qui n'existait plus, un installateur qui ecrivait des chemins vers
des fichiers absents.

Ces tests verrouillent l'etat propre. Ils ne verifient pas que le code est
beau : ils verifient qu'aucun chemin d'execution ne peut plus buter sur une
plateforme disparue.
"""
from __future__ import annotations

import json
import os

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.settings import BotConfig
from gold_bot.state import RACINE

RETIREES = ("pionex", "moonx", "binance", "okx", "coinbase", "bitstamp")


def _fichier(nom: str) -> str:
    return os.path.join(RACINE, nom)


# --------------------------------------------------------------------------
# Les modules
# --------------------------------------------------------------------------
def test_les_modules_des_plateformes_retirees_n_existent_plus():
    for nom in ("moonx", "pionex", "pionex_futures", "pionex_futures_hardened"):
        assert not os.path.exists(_fichier(f"gold_bot/brokers/{nom}.py")), nom
    assert not os.path.exists(_fichier("gold_bot/pionex_runtime.py"))


def test_le_paquet_brokers_s_importe_sans_elles():
    # C'est le test le plus important : un import casse ici empeche le
    # robot de demarrer, quelle que soit la configuration.
    import gold_bot.brokers as b
    assert hasattr(b, "BitvavoBroker")
    assert hasattr(b, "PaperBroker")
    for retiree in ("MoonXBroker", "BinanceBroker", "OkxBroker",
                    "PionexBroker", "PionexFuturesBroker"):
        assert not hasattr(b, retiree), f"{retiree} est encore expose"


def test_le_moteur_s_importe_sans_elles():
    import gold_bot.engine  # noqa: F401


def test_run_bot_s_importe_sans_elles():
    import run_bot  # noqa: F401


# --------------------------------------------------------------------------
# Le simulateur reste, c'est une regle de CLAUDE.md
# --------------------------------------------------------------------------
def test_le_simulateur_reste_un_broker_valide():
    """Il a deja ete retire une fois : plus de dry-run, plus de rejeu, et
    cent trente-sept tests devenus inexecutables."""
    cfg = BotConfig()
    cfg.engine.broker = "paper"
    assert not [p for p in cfg.validate() if "broker invalide" in p]


def test_bitvavo_reste_un_broker_valide():
    cfg = BotConfig()
    cfg.engine.broker = "bitvavo"
    assert not [p for p in cfg.validate() if "broker invalide" in p]


# --------------------------------------------------------------------------
# Une ancienne configuration doit echouer PROPREMENT
# --------------------------------------------------------------------------
def test_une_config_nommant_une_plateforme_retiree_est_refusee_avec_son_nom():
    for retiree in RETIREES:
        cfg = BotConfig()
        cfg.engine.broker = retiree
        problemes = [p for p in cfg.validate() if "broker invalide" in p]
        assert problemes, f"{retiree} passe encore la validation"
        # Le message doit nommer le coupable ET dire ce qui reste : sans
        # ca, « broker invalide » envoie chercher au mauvais endroit.
        assert retiree in problemes[0]
        assert "bitvavo" in problemes[0]


def test_toutes_les_configurations_livrees_sont_valides():
    """Une config livree qui ne passe pas sa propre validation est un
    demarrage impossible livre cle en main."""
    livrees = [f for f in os.listdir(RACINE)
               if f.startswith("robot.") and f.endswith(".json")]
    assert livrees, "aucune configuration livree trouvee"
    for nom in livrees:
        cfg = BotConfig.load(nom)
        assert cfg.validate() == [], f"{nom} : {cfg.validate()}"


def test_aucune_configuration_livree_ne_nomme_une_plateforme_retiree():
    for nom in os.listdir(RACINE):
        if not (nom.startswith("robot.") and nom.endswith(".json")):
            continue
        with open(_fichier(nom), encoding="utf-8") as fh:
            broker = json.load(fh).get("engine", {}).get("broker", "")
        assert broker not in RETIREES, f"{nom} nomme {broker}"


# --------------------------------------------------------------------------
# L'installateur ne doit pas ecrire de chemins morts
# --------------------------------------------------------------------------
def test_l_installateur_ne_propose_que_des_configurations_existantes():
    import re
    with open(_fichier("installer.sh"), encoding="utf-8") as fh:
        contenu = fh.read()
    for nom in set(re.findall(r"robot\.[a-z]+\.json", contenu)):
        assert os.path.exists(_fichier(nom)), (
            f"installer.sh renvoie vers {nom}, qui n'existe pas")
