"""Publication des signaux du robot vers Supabase (application Eve).

Ce module NE PREND AUCUNE DECISION DE TRADING. Il observe le moteur et
recopie ce qu'il fait dans la table `signals`, pour que l'application
mobile puisse l'afficher.

Trois regles, dans l'ordre d'importance :

1. **Le trading passe avant la publication.** Toute erreur reseau est
   avalee : si Supabase tombe, le robot continue de trader et la
   publication part dans une file d'attente sur disque, rejouee au
   cycle suivant.

2. **Un signal publie n'est jamais reecrit.** Seule sa cloture
   (`status`, `closed_at`, `result_pct`) peut etre ajoutee ensuite.
   Sans cette regle, rien n'empeche de maquiller un historique — c'est
   la base de la confiance de l'utilisateur, et c'est verrouille par un
   test.

3. **Le champ `rationale` s'ecrit en francais courant.** Il est lu par
   quelqu'un qui ne sait pas ce qu'est un ATR. Pas de jargon, pas de
   promesse de gain.
"""

from __future__ import annotations

import json
import logging
import os
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

#: Au-dela, la file d'attente cesse de grandir : on jette les plus vieux.
#: Un robot coupe du reseau pendant une semaine ne doit pas remplir le disque.
FILE_MAX = 500

#: Nombre d'echecs consecutifs avant de considerer Supabase comme absent
#: et d'espacer les tentatives (evite de bloquer le cycle de trading).
ECHECS_AVANT_PAUSE = 3
PAUSE_SECONDES = 300.0


# ---------------------------------------------------------------------
# Le texte lu par l'utilisateur
# ---------------------------------------------------------------------

#: Noms courants des cryptos, pour ne pas afficher « le ADA ».
NOMS = {
    "BTC": "Le bitcoin", "ETH": "L'ethereum", "SOL": "Le solana",
    "XRP": "Le XRP", "ADA": "Le cardano", "DOGE": "Le dogecoin",
    "LINK": "Le chainlink", "AVAX": "L'avalanche", "DOT": "Le polkadot",
    "MATIC": "Le polygon", "LTC": "Le litecoin", "ATOM": "Le cosmos",
}


def nom_courant(paire: str) -> str:
    """« BTC/EUR » -> « Le bitcoin ». Repli : « Le SYMBOLE »."""
    base = paire.split("/")[0].upper()
    return NOMS.get(base, f"Le {base}")


def paire_lisible(symbole: str, devise: str = "EUR") -> str:
    """« BTCEUR » -> « BTC/EUR ». « TRXUSD » + devise EUR -> « TRX/EUR ».

    Le robot manipule des symboles colles ; la base impose le format
    `BASE/DEVISE` (contrainte `pair ~ '^[A-Z0-9]{2,12}/[A-Z]{3,5}$'`).
    On coupe par la devise de cotation plutot que par une longueur
    fixe : l'univers va de BTC a des symboles de huit lettres.

    Le symbole interne du robot se termine TOUJOURS par « USD », meme
    quand le marche reel est cote dans une autre devise (EUR chez
    Bitvavo, achat seul) : c'est une convention de nommage, pas la
    devise reelle. Sans ce deuxieme cas, chaque signal reel partait
    vers l'application sous « TRXUSD/EUR » au lieu de « TRX/EUR » —
    toujours vrai en format, jamais vrai en lecture.
    """
    s = symbole.upper().replace("-", "").replace("/", "").replace("_", "")
    d = devise.upper()
    if d and s.endswith(d) and len(s) > len(d):
        base = s[: -len(d)]
    elif s.endswith("USD") and len(s) > 3:
        base = s[:-3]
    else:
        base = s
    return f"{base}/{d}" if d else base


def _duree_lisible(jours: float) -> str:
    if jours < 1.5:
        return "quelques heures"
    if jours < 10:
        return f"environ {round(jours)} jours"
    return f"environ {round(jours / 7)} semaines"


#: Variantes de la phrase d'ouverture (cassure du plus haut). Retour reel,
#: 14 sept. : « toujours le meme discours ... essaye de changer, pas
#: repetitif ». Meme fait a chaque fois, dit autrement -- jamais un fait
#: different, ce serait mentir sur ce que le robot a vu.
_OUVERTURES = [
    "{nom} vient de depasser son prix le plus haut des {jours} derniers jours",
    "{nom} a franchi son plus haut des {jours} derniers jours",
    "{nom} a casse son plafond des {jours} derniers jours",
    "{nom} sort par le haut du couloir qu'il tracait depuis {jours} jours",
]

_CONTINUATIONS = [
    "Quand un prix franchit ainsi son plus haut recent, le mouvement se "
    "prolonge souvent — dans notre historique, {duree}.",
    "Ce genre de cassure a tendance a continuer : sur nos trades passes, "
    "elle s'est poursuivie en moyenne {duree}.",
    "Historiquement ce type de mouvement ne s'arrete pas net chez nous : "
    "il dure encore {duree} en moyenne.",
]

_PROTECTIONS = [
    "Le stop de protection est place sous le prix d'achat : c'est le "
    "montant maximum que ce trade peut couter.",
    "Un ordre stop, place sous le prix d'entree, limite ce que ce trade "
    "peut couter au pire.",
    "La protection est posee sous le prix d'achat des le depart : elle "
    "fixe la perte maximale possible sur ce trade.",
]

#: Variantes du renfort de pyramide. Chacune garde le mot « renforcer » --
#: c'est ce que verifie le test de non-regression, et c'est le terme le
#: plus clair pour dire ce que fait ce type de signal.
_RENFORTS = [
    "{nom} continue de monter apres notre premier achat. Nous renforcons "
    "la position pour la {rang} fois.",
    "Le mouvement sur {nom} se poursuit : nous renforcons la position "
    "une {rang} fois.",
    "{nom} n'a pas ralenti depuis notre entree, nous renforcons donc la "
    "position pour la {rang} fois.",
]

_PROTECTIONS_RENFORT = [
    "Nous n'ajoutons que sur une position deja protegee : si le prix "
    "retombe, ce renfort ne peut pas nous faire perdre plus que ce qui "
    "etait deja engage.",
    "Cet ajout ne se fait que parce que la position est deja a l'abri : "
    "une baisse ne peut pas couter plus que ce qui etait deja risque.",
    "La regle ne change pas a chaque etage : on ne renforce que ce qui "
    "ne peut deja plus nous faire perdre davantage.",
]


def rediger_rationale(
    paire: str,
    canal_jours: int,
    volume_ratio: Optional[float] = None,
    etage: int = 1,
    duree_moyenne_jours: float = 6.0,
    graine: str = "",
) -> str:
    """L'explication de 2 a 3 phrases affichee dans l'application.

    Ecrite pour quelqu'un qui ne connait rien au trading : pas de R, pas
    d'ATR, pas de « cassure de canal Donchian ». Et surtout aucune
    promesse — on decrit ce qui vient de se passer, jamais ce qui va se
    passer.

    `graine` varie la formulation SANS changer les faits : un meme
    evenement (cassure, renfort, stop) se dit de plusieurs facons, tirees
    au sort de facon reproductible (le meme signal redige deux fois donne
    le meme texte). Sans elle, XTZ et BAT recevaient mot pour mot la
    meme phrase -- seul le nom changeait.
    """
    nom = nom_courant(paire)
    alea = random.Random(graine or f"{paire}:{canal_jours}:{etage}")

    if etage > 1:
        ouverture = alea.choice(_RENFORTS).format(nom=nom, rang=_rang(etage))
        protection = alea.choice(_PROTECTIONS_RENFORT)
        return f"{ouverture} {protection}"

    debut = alea.choice(_OUVERTURES).format(nom=nom, jours=canal_jours)
    if volume_ratio and volume_ratio >= 1.2:
        surplus = round((volume_ratio - 1) * 100)
        debut += f", avec {surplus} % d'echanges de plus que d'habitude"
    phrase1 = debut + "."

    phrase2 = alea.choice(_CONTINUATIONS).format(
        duree=_duree_lisible(duree_moyenne_jours))
    phrase3 = alea.choice(_PROTECTIONS)

    return " ".join([phrase1, phrase2, phrase3])


def _rang(n: int) -> str:
    return {2: "deuxieme", 3: "troisieme", 4: "quatrieme",
            5: "cinquieme"}.get(n, f"{n}e")


# ---------------------------------------------------------------------
# Le signal, tel qu'il part vers la base
# ---------------------------------------------------------------------

@dataclass
class SignalPublie:
    """Une ligne de la table `signals`."""

    reference: str          # identifiant cote robot (position_id), pas publie
    pair: str
    side: str               # buy / sell
    entry_price: float
    stop_loss: float
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    risk_reward: Optional[float] = None
    #: LE POURCENTAGE DU CAPITAL RISQUE, pas la somme engagee.
    #: Les deux se ressemblent et different d'un facteur trente : 0,6 %
    #: de risque correspond ici a ~18 % du capital engage. L'application
    #: calcule « au pire tu perds X euros » directement depuis ce champ
    #: (`perteMax` dans format.ts) ; l'interpreter comme une mise
    #: afficherait un chiffre trente fois trop grand.
    position_size_pct: Optional[float] = None
    conviction: Optional[int] = None
    rationale: str = ""
    status: str = "active"
    macro_flag: bool = False

    def vers_supabase(self, publier: bool = True) -> Dict[str, Any]:
        """La ligne telle qu'elle part vers la base.

        `publier=False` la depose en brouillon (`published_at` nul) :
        invisible de l'application, et encore modifiable. C'est ce que
        fait le mode simulation.
        """
        corps: Dict[str, Any] = {
            "reference": self.reference,
            "pair": self.pair,
            "side": self.side,
            "entry_price": round(self.entry_price, 8),
            "stop_loss": round(self.stop_loss, 8),
            "rationale": self.rationale,
            "status": self.status,
            "macro_flag": self.macro_flag,
            # NOT NULL en base : une conviction absente vaut zero, pas
            # « on ne sait pas ». Le publieur la renseigne toujours.
            "conviction": int(self.conviction or 0),
            "published_at": _iso(time.time()) if publier else None,
        }
        if self.take_profit_1 is not None:
            corps["take_profit_1"] = round(self.take_profit_1, 8)
        if self.take_profit_2 is not None:
            corps["take_profit_2"] = round(self.take_profit_2, 8)
        if self.risk_reward is not None:
            corps["risk_reward"] = round(self.risk_reward, 2)
        if self.position_size_pct is not None:
            corps["position_size_pct"] = round(self.position_size_pct, 3)
        return corps


def calculer_risk_reward(entry: float, stop: float,
                         objectif: Optional[float]) -> Optional[float]:
    """Combien on vise pour chaque euro risque. None si pas d'objectif fixe.

    Le robot arme tourne avec `tp_actif: false` — il laisse courir avec un
    stop suiveur au lieu de viser un prix. Dans ce cas il n'y a pas de
    rapport a calculer, et inventer un chiffre serait mentir a
    l'utilisateur.
    """
    risque = abs(entry - stop)
    if risque <= 0 or objectif is None or objectif <= 0:
        return None
    return abs(objectif - entry) / risque


def conviction_depuis_score(score: float) -> int:
    """Le score interne (0 a 1) devient une note sur 100.

    Le robot n'entre pas sous 0,45 : une entree tout juste acceptee vaut
    donc 0 sur l'echelle affichee, et 1,0 vaut 100. Afficher « 45 % de
    conviction » pour le minimum acceptable serait trompeur.
    """
    plancher = 0.45
    if score <= plancher:
        return 0
    return max(0, min(100, round((score - plancher) / (1.0 - plancher) * 100)))


# ---------------------------------------------------------------------
# Le transport
# ---------------------------------------------------------------------

class SupabaseIndisponible(Exception):
    """Le reseau ou la base a refuse. Jamais propagee au moteur."""


@dataclass
class SupabaseREST:
    """Le strict minimum de l'API REST de Supabase : inserer, modifier.

    Pas de dependance externe — `urllib` suffit, et le robot tourne sur
    un VPS ou chaque paquet installe est un paquet a maintenir.
    """

    url: str
    service_key: str
    timeout: float = 10.0

    def _appel(self, methode: str, chemin: str, corps: Any = None,
               entetes_sup: Optional[Dict[str, str]] = None) -> Any:
        cible = f"{self.url.rstrip('/')}/rest/v1/{chemin}"
        donnees = json.dumps(corps).encode() if corps is not None else None
        entetes = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        entetes.update(entetes_sup or {})
        req = urllib.request.Request(cible, data=donnees, headers=entetes,
                                     method=methode)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as rep:
                brut = rep.read().decode()
                return json.loads(brut) if brut.strip() else []
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:300]
            raise SupabaseIndisponible(f"HTTP {exc.code} : {detail}") from exc
        except Exception as exc:                      # reseau, DNS, timeout
            raise SupabaseIndisponible(str(exc)) from exc

    def inserer(self, table: str, ligne: Dict[str, Any]) -> Any:
        return self._appel("POST", table, ligne)

    def modifier(self, table: str, filtre: str, champs: Dict[str, Any]) -> Any:
        return self._appel("PATCH", f"{table}?{filtre}", champs)


# ---------------------------------------------------------------------
# Le publieur
# ---------------------------------------------------------------------

@dataclass
class SignalPublisher:
    """Recopie les signaux du robot dans Supabase, sans jamais le gener."""

    client: Optional[SupabaseREST] = None
    fichier_file: Path = field(
        default_factory=lambda: Path("data/signaux_en_attente.jsonl"))
    _file: List[Dict[str, Any]] = field(default_factory=list, init=False)
    _verrou: threading.Lock = field(default_factory=threading.Lock, init=False)
    _echecs: int = field(default=0, init=False)
    _pause_jusqua: float = field(default=0.0, init=False)
    #: references deja publiees -> empeche le double envoi ET la reecriture
    _publies: set = field(default_factory=set, init=False)

    def __post_init__(self) -> None:
        self._charger_file()

    # -- configuration ------------------------------------------------

    @classmethod
    def depuis_env(cls, **kw: Any) -> "SignalPublisher":
        """Construit le publieur a partir des variables d'environnement.

        Sans cle, on rend un publieur inerte : le robot tourne
        exactement comme avant. C'est le mode par defaut tant que
        l'application n'est pas deployee.
        """
        url = os.getenv("SUPABASE_URL", "").strip()
        cle = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        client = SupabaseREST(url, cle) if url and cle else None
        if client is None:
            log.info("signal_publisher : pas de cle Supabase, publication desactivee")
        return cls(client=client, **kw)

    @property
    def actif(self) -> bool:
        return self.client is not None

    # -- publication --------------------------------------------------

    def publier_ouverture(self, signal: SignalPublie,
                          brouillon: bool = False) -> bool:
        """Publie un nouveau signal. Rend True si la ligne est partie.

        Ne leve jamais : un echec part dans la file d'attente.
        """
        if not self.actif:
            return False
        with self._verrou:
            if signal.reference in self._publies:
                log.debug("signal %s deja publie, ignore", signal.reference)
                return True
            self._publies.add(signal.reference)
        return self._envoyer({
            "type": "ouverture",
            "table": "signals",
            "corps": signal.vers_supabase(publier=not brouillon),
        })

    def publier_cloture(self, reference: str, status: str,
                        closed_at: float, result_pct: float) -> bool:
        """Ferme un signal deja publie. Seule modification autorisee."""
        if not self.actif:
            return False
        if status not in ("closed_tp", "closed_sl", "cancelled"):
            raise ValueError(f"statut de cloture inconnu : {status}")
        return self._envoyer({
            "type": "cloture",
            "table": "signals",
            "filtre": f"reference=eq.{reference}",
            "corps": {
                "status": status,
                "closed_at": _iso(closed_at),
                "result_pct": round(result_pct, 3),
            },
        })

    # -- transport et file d'attente ----------------------------------

    def _envoyer(self, tache: Dict[str, Any]) -> bool:
        if time.time() < self._pause_jusqua:
            self._empiler(tache)
            return False
        try:
            self._executer(tache)
        except SupabaseIndisponible as exc:
            self._echecs += 1
            if self._echecs >= ECHECS_AVANT_PAUSE:
                self._pause_jusqua = time.time() + PAUSE_SECONDES
                log.warning("signal_publisher : Supabase muet, pause %.0f s (%s)",
                            PAUSE_SECONDES, exc)
            else:
                log.warning("signal_publisher : publication reportee (%s)", exc)
            self._empiler(tache)
            return False
        self._echecs = 0
        self._pause_jusqua = 0.0
        return True

    def _executer(self, tache: Dict[str, Any]) -> None:
        assert self.client is not None
        if tache["type"] == "ouverture":
            self.client.inserer(tache["table"], tache["corps"])
        else:
            self.client.modifier(tache["table"], tache["filtre"], tache["corps"])

    def rejouer(self) -> int:
        """Rejoue la file d'attente. Appele a chaque cycle du moteur.

        Rend le nombre de taches passees. S'arrete a la premiere qui
        echoue : l'ordre compte, une cloture ne doit pas partir avant
        son ouverture.
        """
        if not self.actif or time.time() < self._pause_jusqua:
            return 0
        passees = 0
        with self._verrou:
            file = list(self._file)
        for tache in file:
            try:
                self._executer(tache)
            except SupabaseIndisponible:
                break
            passees += 1
        if passees:
            with self._verrou:
                self._file = self._file[passees:]
                self._ecrire_file()
            log.info("signal_publisher : %d publication(s) rattrapee(s)", passees)
            self._echecs = 0
        return passees

    def _empiler(self, tache: Dict[str, Any]) -> None:
        with self._verrou:
            self._file.append(tache)
            if len(self._file) > FILE_MAX:
                jetees = len(self._file) - FILE_MAX
                self._file = self._file[-FILE_MAX:]
                log.warning("signal_publisher : file pleine, %d publication(s) perdue(s)",
                            jetees)
            self._ecrire_file()

    def _ecrire_file(self) -> None:
        try:
            self.fichier_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.fichier_file.with_suffix(".tmp")
            tmp.write_text("\n".join(json.dumps(t) for t in self._file))
            tmp.replace(self.fichier_file)
        except OSError as exc:
            log.warning("signal_publisher : file non sauvegardee (%s)", exc)

    def _charger_file(self) -> None:
        try:
            if not self.fichier_file.exists():
                return
            lignes = self.fichier_file.read_text().splitlines()
            self._file = [json.loads(l) for l in lignes if l.strip()]
            # Les ouvertures deja en file comptent comme « prises en charge » :
            # sans cela un redemarrage republierait le meme signal.
            for tache in self._file:
                if tache.get("type") == "ouverture":
                    ref = tache.get("corps", {}).get("reference")
                    if ref:
                        self._publies.add(ref)
            if self._file:
                log.info("signal_publisher : %d publication(s) en attente",
                         len(self._file))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("signal_publisher : file illisible, repartie a vide (%s)", exc)
            self._file = []


def _iso(horodatage: float) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(
        horodatage, _dt.timezone.utc).isoformat().replace("+00:00", "Z")
