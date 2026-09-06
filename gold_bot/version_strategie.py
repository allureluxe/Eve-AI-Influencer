"""Depuis quand la strategie EN COURS est-elle celle-la ?

POURQUOI CE MODULE EXISTE
-------------------------
Le journal des trades est cumulatif. Le palier de croissance et le plan
lisaient donc TOUT l'historique, sans distinguer les configurations.

Observe le 30 aout, quelques minutes apres le passage au M30 : le plan
annoncait « 8 trades, 0,0 % de reussite, esperance -0,109 R » et refusait
de promouvoir le risque. Ces huit trades venaient de la configuration
PRECEDENTE, celle qui avait perdu 90 EUR. La nouvelle n'en avait fait
aucun.

Deux consequences, et la seconde est la pire :

  - le palier reste verrouille par des pertes qui ne le concernent pas ;
  - l'operateur lit « 0 % de reussite » et croit que la strategie qu'il
    vient d'armer perd, alors qu'elle n'a pas encore trade.

Un echantillon ne veut dire quelque chose que s'il mesure UNE strategie.
Ce module date donc le dernier changement de reglage decisif, et tout ce
qui juge la performance compte a partir de la.

CE QUI COMPTE COMME UN CHANGEMENT
---------------------------------
Uniquement les reglages qui changent la NATURE des trades : l'unite de
temps, le stop, l'objectif, le plafond de cout, le mode de decision, le
lieu d'execution. Pas le risque par trade — il ne change que la taille,
pas la qualite du signal, et le palier a justement pour role de le faire
varier sans invalider l'echantillon.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from .state import ancrer, chemin_par_instance

logger = logging.getLogger(__name__)


def empreinte(config) -> str:
    """Signature courte des reglages qui definissent la strategie."""
    s, t, e = config.strategy, config.trade, config.engine
    parts: list[Any] = [
        e.broker, s.mode, s.entry_tf, s.trigger_tf, s.context_tf, s.bias_tf,
        s.min_confirmations, round(float(s.min_score), 4),
        round(float(s.max_cost_ratio_pct), 4),
        round(float(s.max_spread_atr_ratio), 4),
        round(float(s.min_atr_price_ratio), 6),
        bool(s.allow_counter_trend), bool(s.require_mtf_alignment),
        round(float(t.atr_stop_mult), 4), round(float(t.tp_r_multiple), 4),
        round(float(t.time_stop_minutes), 2),
    ]
    brut = "|".join(str(p) for p in parts)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()[:12]


def _chemin(instance: str = "") -> str:
    return chemin_par_instance("data/strategie.json", "GB_STRATEGIE_FILE", instance)


def depuis_quand(config, instance: str = "", maintenant: float | None = None) -> float:
    """Horodatage du debut de la strategie courante."""
    return marqueur(config, instance, maintenant)[0]


def marqueur(config, instance: str = "",
             maintenant: float | None = None) -> tuple[float, bool]:
    """(debut de la strategie courante, a-t-elle change a cet appel ?).

    Met a jour le fichier si l'empreinte a change. Retourne 0.0 quand le
    marqueur ne peut pas etre ecrit — dans ce cas tout l'historique est
    compte, ce qui est le comportement d'avant : degrade, jamais bloquant.
    """
    maintenant = maintenant or time.time()
    signature = empreinte(config)
    chemin = _chemin(instance or config.engine.broker)

    connu = {}
    try:
        with open(chemin, "r", encoding="utf-8") as fh:
            connu = json.load(fh) or {}
    except (OSError, ValueError):
        connu = {}

    if connu.get("empreinte") == signature and connu.get("depuis"):
        return float(connu["depuis"]), False

    ancienne = connu.get("empreinte")
    contenu = {"empreinte": signature, "depuis": maintenant,
               "unite": config.strategy.entry_tf, "broker": config.engine.broker}
    try:
        os.makedirs(os.path.dirname(ancrer(chemin)) or ".", exist_ok=True)
        with open(chemin, "w", encoding="utf-8") as fh:
            json.dump(contenu, fh, indent=2)
    except OSError as exc:
        logger.warning("marqueur de strategie non ecrit (%s) : %s", chemin, exc)
        return 0.0, False

    if ancienne:
        logger.warning(
            "STRATEGIE MODIFIEE (%s -> %s, unite %s) : l'echantillon de "
            "performance repart de zero. Les trades precedents ne jugent "
            "plus la configuration en service.",
            ancienne, signature, config.strategy.entry_tf)
    else:
        logger.info("strategie %s (unite %s) : debut de l'echantillon",
                    signature, config.strategy.entry_tf)
    return maintenant, bool(ancienne)
