"""L'agenda economique tel que l'application le montre.

CE MODULE NE DECIDE RIEN. Il traduit et publie ce que `gold_bot.news`
fait deja.

Pourquoi ce n'est pas un deuxieme agenda
----------------------------------------
Le robot possede depuis longtemps un calendrier complet : Finnhub, FMP,
Trading Economics, un calendrier local et les recurrences, fusionnes et
dedoublonnes dans `NewsFilter`. C'est lui qui bloque reellement les
entrees.

Ecrire ici un second agenda aurait produit exactement le defaut que ce
depot a deja rencontre cinq fois : **une mesure — ou ici un affichage —
qui decrit autre chose que ce qui tourne.** L'application aurait
annonce « aucun signal entre 14h15 et 15h00 » pendant que le robot, lui,
suivait ses propres fenetres. Un utilisateur qui verifie une fois perd
confiance pour toujours.

Donc : `eve_policy` est **calculee a partir de la configuration reelle
du filtre**. Si quelqu'un change `high_before`, le texte affiche change
avec lui. Il ne peut pas mentir.

La difference avec la specification, et pourquoi elle reste
-----------------------------------------------------------
La specification de l'application demandait une fenetre de -15 min a
+30 min. Le robot arme tourne en **-20 / +20**, avec une reouverture
possible en « mode cassure » entre +6 et +45 min apres l'annonce.

Aligner le robot sur la specification aurait modifie sa logique de
trading — ce que la consigne interdit explicitement, et ce qu'aucune
mesure ne justifie. On a donc fait l'inverse : **c'est le texte affiche
qui suit le robot.** La regle publiee decrit -20/+20 parce que c'est ce
qui se passe.
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .news import IMPACT_LOW, EconomicEvent, NewsFilter
from .signal_publisher import SupabaseIndisponible, SupabaseREST

log = logging.getLogger(__name__)

#: Seuls ces pays interessent l'utilisateur francophone. Le reste du
#: monde bouge les cryptos aussi, mais afficher trente lignes par jour
#: rend l'agenda illisible — et un agenda illisible n'est pas consulte.
PAYS_RETENUS = {"USD": "Etats-Unis", "EUR": "Zone euro"}


# ---------------------------------------------------------------------
# Traduction
# ---------------------------------------------------------------------
#: Le nom d'origine est en anglais et en jargon. « Non-Farm Payrolls »
#: ne veut rien dire pour l'utilisateur vise. La cle est cherchee en
#: minuscules et par inclusion, parce que les fournisseurs ecrivent
#: « US CPI YoY », « CPI y/y » ou « Core CPI » pour la meme chose.
TRADUCTIONS = {
    "non-farm payroll": "Emploi americain",
    "nonfarm payroll": "Emploi americain",
    "unemployment rate": "Taux de chomage",
    "initial jobless": "Inscriptions au chomage",
    "core cpi": "Inflation americaine (hors energie)",
    "cpi": "Inflation",
    "ppi": "Prix a la production",
    "pce": "Inflation mesuree par la Fed",
    "fomc": "Decision de taux de la Fed",
    "fed interest rate": "Decision de taux de la Fed",
    "fed chair": "Discours du president de la Fed",
    "powell": "Discours du president de la Fed",
    "ecb interest rate": "Decision de taux de la BCE",
    "ecb press": "Conference de presse de la BCE",
    "lagarde": "Discours de la presidente de la BCE",
    "gdp": "Croissance economique",
    "retail sales": "Ventes au detail",
    "ism manufacturing": "Activite industrielle americaine",
    "ism services": "Activite des services americains",
    "pmi": "Indice d'activite",
    "consumer confidence": "Confiance des menages",
    "michigan": "Confiance des menages americains",
    "durable goods": "Commandes de biens durables",
    "trade balance": "Balance commerciale",
    "crude oil inventories": "Stocks de petrole americains",
}


def traduire(titre: str) -> str:
    """« Non-Farm Payrolls » -> « Emploi americain ».

    Repli sur le nom d'origine : afficher l'anglais est desagreable,
    inventer une traduction fausse est pire.
    """
    bas = titre.lower()
    # Les cles longues d'abord : « core cpi » doit gagner contre « cpi ».
    for motif in sorted(TRADUCTIONS, key=len, reverse=True):
        if motif in bas:
            return TRADUCTIONS[motif]
    return titre.strip()


# ---------------------------------------------------------------------
# La regle affichee, deduite du comportement reel
# ---------------------------------------------------------------------

def _heure(horodatage: float, decalage_min: int) -> str:
    """Heure de Paris, format « 14h30 »."""
    quand = dt.datetime.fromtimestamp(horodatage, dt.timezone.utc) \
        + dt.timedelta(minutes=decalage_min)
    try:
        from zoneinfo import ZoneInfo
        quand = quand.astimezone(ZoneInfo("Europe/Paris"))
    except Exception:                                       # noqa: BLE001
        pass
    return quand.strftime("%Hh%M")


def redaction_politique(evenement: EconomicEvent, filtre: NewsFilter) -> str:
    """Ce que le robot fait autour de cet evenement, en francais.

    Le texte est construit a partir de `filtre.config` : il ne peut pas
    decrire une regle que le robot n'applique pas.
    """
    cfg = filtre.config
    if filtre.is_major(evenement):
        debut = _heure(evenement.ts, -cfg.high_before)
        fin = _heure(evenement.ts, +cfg.high_after)
        texte = (f"Aucun nouvel achat entre {debut} et {fin}. "
                 f"Les positions deja ouvertes gardent leur protection "
                 f"et ne sont pas fermees.")
        if cfg.allow_breakout:
            reprise = _heure(evenement.ts, +cfg.breakout_from)
            texte += (f" Si un mouvement franc se dessine apres {reprise}, "
                      f"le robot peut de nouveau acheter.")
        return texte
    if evenement.impact == IMPACT_LOW:
        return "Sans effet attendu sur les decisions du robot."
    return ("Le robot continue d'acheter normalement, avec une vigilance "
            "accrue sur les protections.")


# ---------------------------------------------------------------------
# Le service
# ---------------------------------------------------------------------

@dataclass
class AgendaEconomique:
    """Traduit l'agenda du robot et le publie pour l'application."""

    filtre: NewsFilter
    client: Optional[SupabaseREST] = None
    #: Classe d'actif utilisee pour choisir les devises pertinentes.
    #: La crypto reagit surtout au dollar et a l'euro.
    classe: str = "crypto"

    @classmethod
    def depuis_env(cls, filtre: Optional[NewsFilter] = None) -> "AgendaEconomique":
        import os
        url = os.getenv("SUPABASE_URL", "").strip()
        cle = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        return cls(filtre=filtre or NewsFilter(),
                   client=SupabaseREST(url, cle) if url and cle else None)

    # -- ce que le robot consulte -------------------------------------

    def is_blackout(self, quand: Optional[dt.datetime] = None,
                    symbole: str = "") -> bool:
        """Le robot a-t-il le droit d'ouvrir maintenant ?

        Delegue au filtre reel. Cette fonction existe pour que
        l'application et le robot repondent a la meme question avec le
        meme code — pas pour ajouter une regle.
        """
        instant = (quand.timestamp() if quand else time.time())
        try:
            return bool(self.filtre.check(self.classe, symbole, now=instant).blocked)
        except Exception as exc:                            # noqa: BLE001
            # UNE PANNE D'AGENDA NE BLOQUE PAS LE ROBOT.
            # Le calendrier est un confort ; le refuser en cas de doute
            # figerait le robot des que Finnhub tousse.
            log.warning("agenda indisponible, aucun blocage applique : %s", exc)
            return False

    def evenement_fort_a_venir(self, horizon_heures: float = 24.0,
                               maintenant: Optional[float] = None) -> Optional[EconomicEvent]:
        """Une annonce a fort impact dans l'horizon d'un signal.

        Sert a poser `macro_flag` : l'utilisateur voit alors que son
        trade traverse une publication importante.
        """
        instant = maintenant if maintenant is not None else time.time()
        try:
            self.filtre.refresh()
        except Exception:                                   # noqa: BLE001
            return None
        limite = instant + horizon_heures * 3600
        for ev in self.filtre.relevant(self.classe):
            if instant <= ev.ts <= limite and self.filtre.is_major(ev):
                return ev
        return None

    # -- ce que l'application affiche ---------------------------------

    def evenements(self, jours: int = 30,
                   maintenant: Optional[float] = None) -> List[Dict[str, Any]]:
        """Les lignes prêtes pour la table `economic_events`."""
        instant = maintenant if maintenant is not None else time.time()
        try:
            self.filtre.refresh()
        except Exception as exc:                            # noqa: BLE001
            log.warning("agenda non rafraichi : %s", exc)
        limite = instant + jours * 86400
        lignes: List[Dict[str, Any]] = []
        vus = set()
        for ev in sorted(self.filtre.events, key=lambda e: e.ts):
            if not (instant <= ev.ts <= limite):
                continue
            if ev.currency not in PAYS_RETENUS:
                continue
            if ev.impact == IMPACT_LOW:
                continue                     # illisible, et sans effet
            cle = (int(ev.ts // 900), ev.currency, traduire(ev.title))
            if cle in vus:
                continue
            vus.add(cle)
            lignes.append({
                "event_time": _iso(ev.ts),
                "name_fr": traduire(ev.title),
                "country": PAYS_RETENUS[ev.currency],
                "impact": "high" if self.filtre.is_major(ev) else "medium",
                "eve_policy": redaction_politique(ev, self.filtre),
                "actual": ev.actual,
                "forecast": ev.forecast,
                "previous": ev.previous,
            })
        return lignes

    def publier(self, jours: int = 30) -> int:
        """Ecrit l'agenda dans Supabase. Rend le nombre de lignes.

        `upsert` sur la contrainte (event_time, country, name_fr) : un
        evenement dont le chiffre publie arrive plus tard est mis a
        jour, pas duplique. Le `on_conflict` est obligatoire — sans lui
        PostgREST ne vise que la cle primaire, qui est un uuid tire au
        hasard : chaque passage aurait cree des doublons.

        Contrairement aux signaux, l'agenda N'EST PAS immuable : un
        chiffre revise doit pouvoir se corriger.
        """
        if self.client is None:
            return 0
        lignes = self.evenements(jours)
        if not lignes:
            return 0
        try:
            self.client._appel(
                "POST",
                "economic_events?on_conflict=event_time,country,name_fr",
                lignes,
                {"Prefer": "resolution=merge-duplicates,return=minimal"})
        except SupabaseIndisponible as exc:
            log.warning("agenda non publie : %s", exc)
            return 0
        log.info("agenda : %d evenement(s) publie(s)", len(lignes))
        return len(lignes)


def _iso(horodatage: float) -> str:
    return dt.datetime.fromtimestamp(
        horodatage, dt.timezone.utc).isoformat().replace("+00:00", "Z")
