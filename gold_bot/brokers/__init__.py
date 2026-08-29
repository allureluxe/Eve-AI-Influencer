"""Lieux d'execution du robot.

DEUX PLATEFORMES, ET UN SIMULATEUR

Le 29 aout, l'operateur : « supprime tout ce qui touche a Pionex, Binance,
MoonX etc. Je veux que sur le bot il reste juste Bitvavo et IBKR, tout le
reste tu effaces pour que le bot ne bloque pas a cause d'anciennes
plateformes qu'on a essaye d'integrer. »

Ne restent donc que :

    bitvavo   la plateforme en service, argent reel
    paper     le simulateur — voir plus bas, il n'est PAS optionnel

IBKR n'a pas encore de module ici : il s'ajoutera a cote de Bitvavo, et
`router.py` / `multi.py` sont conserves pour ca — ce sont eux qui savent
faire tourner deux plateformes en parallele sans qu'une panne de l'une
arrete l'autre.

POURQUOI `paper` RESTE, MEME S'IL N'EST PAS UNE PLATEFORME

Il a deja ete retire une fois de la liste des brokers valides. Consequence
immediate : plus de dry-run, plus de rejeu historique, et aucun moteur
constructible en test. Un lieu d'execution qui n'engage rien doit toujours
etre disponible — c'est une regle de CLAUDE.md, pas une preference.

CE QUI ARRIVE A UNE ANCIENNE CONFIGURATION

Rien de silencieux. `BotConfig.validate()` refuse au demarrage tout broker
hors de la liste, en le nommant. Un `"broker": "pionex"` oublie quelque
part produit un message clair au lieu d'un plantage a l'import.
"""
from .base import AccountInfo, Broker, BrokerError
from .bitvavo import BitvavoBroker, BitvavoConfig, RegleMarche
from .bitvavo_margin import BitvavoMarginBroker
from .bitvavo_hardening import harden_bitvavo
from .paper import PaperBroker, PaperConfig

harden_bitvavo(BitvavoBroker, RegleMarche)

__all__ = [
    "Broker", "BrokerError", "AccountInfo",
    "PaperBroker", "PaperConfig",
    "BitvavoBroker", "BitvavoMarginBroker", "BitvavoConfig", "RegleMarche",
]
