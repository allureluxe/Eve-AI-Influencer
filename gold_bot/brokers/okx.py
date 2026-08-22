"""Execution sur OKX Europe (comptant, en euros).

OKX Europe Limited est agree CASP par la MFSA (Malte) au titre de MiCA
depuis janvier 2025, avec passeport sur les 30 pays de l'EEE. Un resident
francais peut donc l'utiliser dans le cadre europeen.

Ce qui le distingue de Bitvavo, et pourquoi ce connecteur existe.

1. LES FRAIS RENDENT LE H1 POSSIBLE
   Palier de base : 0,08 % maker, 0,10 % taker. Le robot entre et sort au
   marche, donc taker des deux cotes : 0,20 % d'aller-retour, contre
   0,50 % chez Bitvavo.

       cout / risque = frais aller-retour / (distance du stop en % du prix)

   Pour tenir sous 15 % :

       stop minimum = 0,20 % / 0,15 = 1,3 % du prix

   Soit H1, et non H4. C'est le meme tarif que celui de Binance avant son
   retrait : l'echelle de temps qui fonctionnait la-bas redevient
   accessible ici. La difference n'est pas cosmetique — elle separe
   plusieurs trades par jour de quelques-uns par semaine.

2. LE STOP ET L'OBJECTIF TIENNENT SUR LA PLATEFORME
   OKX accepte de rattacher un stop ET un objectif a l'ordre d'entree
   (`attachAlgoOrds`), et annule automatiquement l'un quand l'autre se
   declenche. C'est le comportement OCO qui manque a Bitvavo, ou seul le
   stop peut etre depose. Ici la position reste bornee DES DEUX COTES
   meme si le robot s'arrete.

3. ON NE PEUT TOUJOURS QU'ACHETER
   Le comptant ne permet pas la vente a decouvert, ici comme ailleurs.
   Le robot ecarte ses signaux de vente.

Trois pieges propres a l'API v5, tous corriges plus bas :

  - l'horodatage signe est une date ISO 8601 en millisecondes, pas un
    nombre de millisecondes depuis 1970 comme partout ailleurs ;
  - une reponse HTTP 200 peut porter un echec : c'est le champ `code` du
    corps qui fait foi, « 0 » seul valant succes ;
  - sur un achat au marche au comptant, `sz` designe par defaut un montant
    en devise de cotation et non une quantite d'actif. `tgtCcy` est donc
    toujours precise explicitement.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import logging
import math
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from ..core import ClosedTrade, Position, Side, Tick
from ..universe import CATALOGUE_CRYPTO, Instrument
from .base import AccountInfo, Broker, BrokerError

logger = logging.getLogger(__name__)

# Les clients de l'EEE peuvent se voir servir par un domaine dedie
# (eea.okx.com). OKX_API_URL permet d'en changer sans toucher au code.
BASE = os.getenv("OKX_API_URL", "https://www.okx.com").rstrip("/")

# Le catalogue suit l'univers du robot : une liste tenue a la main ici
# divergerait des le premier actif ajoute.
ACTIFS = {f"{actif}USD": actif for actif in CATALOGUE_CRYPTO}

DEVISE_DEFAUT = os.getenv("OKX_QUOTE_ASSET", "EUR").upper()

# Palier de base. Remplace au demarrage par le tarif reel du compte.
FRAIS_TAKER = 0.0010
FRAIS_MAKER = 0.0008


def marche(symbole: str, devise: str = "") -> Optional[str]:
    """Code OKX d'un symbole du robot.

    Exemple : marche("BTCUSD", "EUR") -> "BTC-EUR"
    """
    actif = ACTIFS.get(symbole.upper())
    if not actif:
        return None
    return f"{actif}-{(devise or DEVISE_DEFAUT).upper()}"


def formater(valeur: float, decimales: int = 12) -> str:
    """Ecrit un nombre en decimal simple, jamais en notation scientifique.

    `str(1e-05)` donne « 1e-05 », qu'OKX refuse. Les montants partent donc
    toujours par ici.
    """
    texte = f"{valeur:.{max(0, decimales)}f}"
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte or "0"


def horodatage_iso() -> str:
    """Date ISO 8601 en millisecondes, terminee par Z.

    OKX signe cette chaine, pas un nombre de millisecondes depuis 1970.
    Envoyer l'un a la place de l'autre donne une signature invalide sans
    message explicite.
    """
    maintenant = datetime.datetime.now(datetime.timezone.utc)
    return maintenant.strftime("%Y-%m-%dT%H:%M:%S.") + f"{maintenant.microsecond // 1000:03d}Z"


def decimales_du_pas(pas: float) -> int:
    """Nombre de decimales significatives d'un pas de cotation."""
    if pas <= 0:
        return 8
    texte = f"{pas:.12f}".rstrip("0")
    return len(texte.split(".")[1]) if "." in texte else 0


@dataclass(slots=True)
class OkxConfig:
    api_key: str = ""
    api_secret: str = ""
    passphrase: str = ""
    quote_asset: str = DEVISE_DEFAUT
    timeout: float = 15.0
    dry_run: bool = True
    demo: bool = False
    fee_rate: float = FRAIS_TAKER
    stop_move_threshold_r: float = 0.15

    @classmethod
    def from_env(cls) -> "OkxConfig":
        return cls(
            api_key=os.getenv("OKX_API_KEY", "").strip(),
            api_secret=os.getenv("OKX_API_SECRET", "").strip(),
            passphrase=os.getenv("OKX_PASSPHRASE", "").strip(),
            quote_asset=os.getenv("OKX_QUOTE_ASSET", DEVISE_DEFAUT).upper(),
            timeout=float(os.getenv("OKX_TIMEOUT", "15") or 15),
            dry_run=os.getenv("OKX_DRY_RUN", "1").strip() not in ("0", "false", "False", ""),
            demo=os.getenv("OKX_DEMO", "0").strip() in ("1", "true", "True"),
            fee_rate=float(os.getenv("OKX_FEE_RATE", str(FRAIS_TAKER)) or FRAIS_TAKER),
            stop_move_threshold_r=float(os.getenv("OKX_STOP_MOVE_THRESHOLD_R", "0.15") or 0.15),
        )


@dataclass(slots=True)
class RegleInstrument:
    """Contraintes reelles d'OKX pour un instrument."""

    inst_id: str
    tick_size: float = 0.01      # pas de prix
    lot_size: float = 1e-8       # pas de quantite
    min_size: float = 0.0        # quantite minimale

    def arrondir_quantite(self, quantite: float) -> float:
        """Arrondi VERS LE BAS au pas de la plateforme.

        Vers le bas et jamais vers le haut : un arrondi genereux ferait
        depasser a chaque ordre le risque calcule en amont.
        """
        if quantite <= 0 or self.lot_size <= 0:
            return max(0.0, quantite)
        pas = math.floor(quantite / self.lot_size + 1e-9)
        return round(pas * self.lot_size, 12)

    def arrondir_prix(self, prix: float) -> float:
        if prix <= 0 or self.tick_size <= 0:
            return prix
        return round(round(prix / self.tick_size) * self.tick_size, 12)

    @property
    def decimales_quantite(self) -> int:
        return decimales_du_pas(self.lot_size)

    @property
    def decimales_prix(self) -> int:
        return decimales_du_pas(self.tick_size)


class OkxBroker(Broker):
    """Achat au comptant sur OKX, stop et objectif attaches a l'ordre."""

    name = "okx"
    is_live = True
    supports_short = False        # le comptant ne permet pas la vente a decouvert

    def __init__(self, config: Optional[OkxConfig] = None) -> None:
        self.config = config or OkxConfig.from_env()
        self.base = BASE
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = {}
        self._closed: list[ClosedTrade] = []
        self._regles: dict[str, RegleInstrument] = {}
        self._account = AccountInfo(0.0, 0.0, self.config.quote_asset)
        self._soldes: dict[str, float] = {}
        self._last_error = ""

    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        if self.config.dry_run:
            return "simulation (dry-run)"
        return "demo (argent fictif)" if self.config.demo else "REEL"

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def symbol_for(self, symbol: str) -> str:
        code = marche(symbol, self.config.quote_asset)
        if not code:
            raise BrokerError(f"{symbol} n'est pas disponible sur OKX")
        return code

    def supports(self, symbol: str) -> bool:
        """L'instrument est-il reellement cotable dans la devise choisie ?

        Tant que les instruments ne sont pas charges, on ne prejuge de
        rien : filtrer trop tot viderait l'univers entier.
        """
        if symbol.upper() not in ACTIFS:
            return False
        if not self._regles:
            return True
        return marche(symbol, self.config.quote_asset) in self._regles

    def regle(self, symbol: str) -> RegleInstrument:
        code = self.symbol_for(symbol)
        return self._regles.get(code, RegleInstrument(inst_id=code))

    # ------------------------------------------------------------------
    # Signature et appels
    # ------------------------------------------------------------------
    def _signer(self, horodatage: str, methode: str, chemin: str, corps: str) -> str:
        """base64(HMAC-SHA256(secret, horodatage + METHODE + chemin + corps)).

        Le chemin inclut la chaine de requete, et le corps doit etre
        serialise exactement comme il sera envoye.
        """
        message = f"{horodatage}{methode.upper()}{chemin}{corps}"
        signature = hmac.new(self.config.api_secret.encode("utf-8"),
                             message.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _appel(self, methode: str, chemin: str, params: Optional[dict] = None,
               corps: Optional[Any] = None, signe: bool = True) -> list:
        """Appel REST v5. Retourne le contenu de `data`, jamais l'enveloppe.

        OKX repond HTTP 200 meme sur un echec metier : c'est le champ
        `code` qui fait foi. Le confondre avec le statut HTTP ferait passer
        un ordre refuse pour un ordre accepte.
        """
        requete = chemin
        if params:
            utiles = {c: v for c, v in params.items() if v not in (None, "")}
            if utiles:
                requete += "?" + "&".join(f"{c}={v}" for c, v in utiles.items())

        texte_corps = ""
        donnees = None
        if corps is not None:
            texte_corps = json.dumps(corps, separators=(",", ":"))
            donnees = texte_corps.encode("utf-8")

        entetes = {"User-Agent": "gold-bot/1.0", "Content-Type": "application/json"}
        if self.config.demo:
            entetes["x-simulated-trading"] = "1"
        if signe:
            if not (self.config.api_key and self.config.api_secret and self.config.passphrase):
                raise BrokerError(
                    "OKX_API_KEY, OKX_API_SECRET et OKX_PASSPHRASE sont tous les trois "
                    "necessaires : OKX demande une phrase secrete en plus de la cle")
            horodatage = horodatage_iso()
            entetes.update({
                "OK-ACCESS-KEY": self.config.api_key,
                "OK-ACCESS-SIGN": self._signer(horodatage, methode, requete, texte_corps),
                "OK-ACCESS-TIMESTAMP": horodatage,
                "OK-ACCESS-PASSPHRASE": self.config.passphrase,
            })

        req = urllib.request.Request(self.base + requete, data=donnees,
                                     headers=entetes, method=methode.upper())
        ctx = ssl.create_default_context()
        ca = os.getenv("GB_CA_BUNDLE") or "/root/.ccr/ca-bundle.crt"
        if os.path.exists(ca):
            try:
                ctx.load_verify_locations(ca)
            except Exception:  # pragma: no cover - environnement sans bundle
                pass
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout, context=ctx) as resp:
                brut = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            code, message = self._lire_erreur(detail)
            raise BrokerError(
                f"OKX {exc.code} sur {methode} {chemin}"
                + (f" [{code}] {message}" if message else "")) from exc
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(f"OKX injoignable sur {chemin} : {exc}") from exc

        return self._extraire(brut, chemin)

    @staticmethod
    def _extraire(brut: str, chemin: str) -> list:
        """Valide l'enveloppe v5 et rend le contenu de `data`."""
        try:
            reponse = json.loads(brut)
        except json.JSONDecodeError as exc:
            raise BrokerError(f"OKX: reponse illisible sur {chemin}") from exc
        if not isinstance(reponse, dict):
            raise BrokerError(f"OKX: reponse inattendue sur {chemin}")

        code = str(reponse.get("code", ""))
        donnees = reponse.get("data") or []
        if code != "0":
            # Sur un ordre refuse, le detail utile est dans data[0], pas
            # dans le message d'enveloppe qui reste generique.
            detail = ""
            if isinstance(donnees, list) and donnees and isinstance(donnees[0], dict):
                sous_code = donnees[0].get("sCode", "")
                sous_message = donnees[0].get("sMsg", "")
                if sous_message:
                    detail = f" ({sous_code} {sous_message})"
            raise BrokerError(
                f"OKX [{code}] {reponse.get('msg', '')}{detail} sur {chemin}")
        return donnees if isinstance(donnees, list) else [donnees]

    @staticmethod
    def _lire_erreur(brut: str) -> tuple[str, str]:
        try:
            data = json.loads(brut)
        except Exception:  # noqa: BLE001
            return "", brut[:200]
        return str(data.get("code", "")), str(data.get("msg", ""))[:200]

    # ------------------------------------------------------------------
    def connect(self) -> bool:
        cfg = self.config
        if cfg.dry_run and not (cfg.api_key and cfg.api_secret and cfg.passphrase):
            logger.warning("OKX en simulation sans cle : solde fictif")
            solde = float(os.getenv("OKX_DRYRUN_EQUITY", "100") or 100)
            self._account = AccountInfo(solde, solde, cfg.quote_asset)
            try:
                self._charger_regles()
            except BrokerError as exc:
                logger.warning("instruments OKX non charges : %s", str(exc)[:150])
            return True
        if not (cfg.api_key and cfg.api_secret and cfg.passphrase):
            self._last_error = ("OKX_API_KEY, OKX_API_SECRET ou OKX_PASSPHRASE absent "
                                "(les trois sont necessaires)")
            logger.error("connexion OKX impossible : %s", self._last_error)
            return False
        try:
            self._charger_regles()
            self._charger_frais()
            self.sync()
            if cfg.dry_run:
                logger.warning("OKX en simulation : lecture reelle, "
                               "aucun ordre ne sera envoye")
            logger.info("OKX connecte [%s] : %.2f %s",
                        self.mode, self._account.equity, cfg.quote_asset)
            if not cfg.dry_run and not cfg.demo:
                logger.warning("MODE REEL : les ordres engagent de l'argent veritable")
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("connexion OKX echouee : %s", str(exc)[:250])
            return False

    def healthy(self) -> bool:
        return not self._last_error

    # ------------------------------------------------------------------
    def _charger_regles(self) -> None:
        """Contraintes reelles de la plateforme, lues et non devinees."""
        instruments = self._appel("GET", "/api/v5/public/instruments",
                                  params={"instType": "SPOT"}, signe=False)
        attendus = {marche(sym, self.config.quote_asset) for sym in ACTIFS}
        for ligne in instruments:
            code = ligne.get("instId")
            if code not in attendus or ligne.get("state") != "live":
                continue
            self._regles[code] = RegleInstrument(
                inst_id=code,
                tick_size=float(ligne.get("tickSz", 0.01) or 0.01),
                lot_size=float(ligne.get("lotSz", 1e-8) or 1e-8),
                min_size=float(ligne.get("minSz", 0) or 0),
            )
        logger.info("instruments OKX charges : %d cotable(s) en %s",
                    len(self._regles), self.config.quote_asset)

    def _charger_frais(self) -> None:
        """Lit le palier tarifaire reel du compte plutot que de le supposer."""
        try:
            taux = self._appel("GET", "/api/v5/account/trade-fee",
                               params={"instType": "SPOT"})
        except BrokerError as exc:
            logger.warning("tarif OKX non lu (%s) : palier de base retenu",
                           str(exc)[:120])
            return
        if not taux:
            return
        # OKX exprime ses frais en negatif : -0.001 signifie 0,1 % preleve.
        try:
            taker = abs(float(taux[0].get("taker", 0) or 0))
        except (TypeError, ValueError, IndexError):
            return
        if taker <= 0:
            return
        self.config.fee_rate = taker
        logger.info("tarif OKX du compte : taker %.4f %% — "
                    "stop minimum conseille %.2f %% du prix",
                    taker * 100, (2 * taker / 0.15) * 100)

    def notionnel_minimum(self) -> float:
        """Ticket d'entree median impose par la plateforme, en devise.

        OKX exprime son minimum en quantite d'actif (`minSz`) et non en
        montant : il faut donc le convertir au prix courant. Sans prix
        disponible, on retombe sur une estimation prudente plutot que de
        laisser le moteur croire qu'il peut ouvrir des positions infimes.
        """
        prix = self._prix_du_marche()
        montants = []
        for code, regle in self._regles.items():
            if regle.min_size <= 0:
                continue
            valeur = prix.get(code)
            if valeur:
                montants.append(regle.min_size * valeur)
        if not montants:
            return 5.0
        montants.sort()
        return max(montants[len(montants) // 2], 1.0)

    def apply_market_rules(self, universe) -> list[str]:
        modifies: list[str] = []
        for inst in universe:
            code = marche(inst.symbol, self.config.quote_asset)
            regle = self._regles.get(code) if code else None
            if regle is None:
                continue
            minimum = regle.min_size or regle.lot_size
            if (abs(inst.min_lot - minimum) > 1e-12
                    or abs(inst.lot_step - regle.lot_size) > 1e-12):
                modifies.append(f"{inst.symbol} lot min {inst.min_lot} -> {minimum}")
                inst.min_lot = minimum
                inst.lot_step = regle.lot_size
        for ligne in modifies:
            logger.info("contrainte alignee sur OKX : %s", ligne)
        return modifies

    # ------------------------------------------------------------------
    def sync(self) -> None:
        """Lit les soldes et reconstitue la valeur du compte en devise.

        Au comptant il n'existe pas de « position » cote plateforme : on
        detient des actifs. Le capital total est donc le solde en euros
        plus la valeur de marche de ce qui est detenu.
        """
        comptes = self._appel("GET", "/api/v5/account/balance")
        self._soldes = {}
        disponible = 0.0
        quote = self.config.quote_asset

        details = comptes[0].get("details", []) if comptes else []
        for ligne in details:
            actif = str(ligne.get("ccy", "")).upper()
            try:
                total = float(ligne.get("eq", 0) or 0)
                libre = float(ligne.get("availBal", 0) or 0)
            except (TypeError, ValueError):
                continue
            if total > 0:
                self._soldes[actif] = total
            if actif == quote:
                disponible = libre

        total_compte = self._soldes.get(quote, 0.0)
        prix_tous = self._prix_du_marche()
        for actif, quantite in self._soldes.items():
            if actif == quote:
                continue
            prix = prix_tous.get(f"{actif}-{quote}")
            if prix:
                total_compte += quantite * prix

        self._account = AccountInfo(equity=total_compte, balance=total_compte,
                                    currency=quote,
                                    margin_used=max(0.0, total_compte - disponible),
                                    margin_free=disponible, leverage=1.0)
        self._last_error = ""

    def _prix_du_marche(self) -> dict[str, float]:
        """Tous les derniers prix du comptant en un seul appel."""
        try:
            lignes = self._appel("GET", "/api/v5/market/tickers",
                                 params={"instType": "SPOT"}, signe=False)
        except BrokerError:
            return {}
        prix: dict[str, float] = {}
        for ligne in lignes:
            try:
                valeur = float(ligne["last"])
            except (KeyError, TypeError, ValueError):
                continue
            if valeur > 0:
                prix[str(ligne["instId"])] = valeur
        return prix

    def _prix(self, code: str) -> Optional[float]:
        try:
            data = self._appel("GET", "/api/v5/market/ticker",
                               params={"instId": code}, signe=False)
            return float(data[0]["last"])
        except Exception:  # noqa: BLE001
            return None

    def account(self) -> AccountInfo:
        return self._account

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    # ------------------------------------------------------------------
    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if side is not Side.BUY:
            raise BrokerError(
                "le comptant ne permet que l'achat : la vente a decouvert est impossible")
        if not stop_loss:
            raise BrokerError("ouverture refusee : stop-loss obligatoire")

        code = self.symbol_for(instrument.symbol)
        regle = self.regle(instrument.symbol)
        quantite = regle.arrondir_quantite(lots)
        if quantite <= 0:
            raise BrokerError(f"quantite nulle apres arrondi sur {code}")
        if regle.min_size and quantite < regle.min_size:
            raise BrokerError(
                f"quantite {formater(quantite)} sous le minimum "
                f"{formater(regle.min_size)} sur {code}")

        reference = self._prix(code) or (stop_loss + take_profit) / 2.0
        notionnel = quantite * reference
        # Les frais se prelevent en plus du notionnel : un ordre calibre au
        # centime pres sur le solde disponible serait refuse.
        marge = self._account.margin_free
        if marge > 0 and notionnel > marge * 0.995:
            raise BrokerError(
                f"notionnel {notionnel:.2f} au-dela du disponible "
                f"{marge:.2f} {self.config.quote_asset}, frais compris")

        stop = regle.arrondir_prix(stop_loss)
        objectif = regle.arrondir_prix(take_profit)

        if self.config.dry_run:
            logger.warning("[DRY-RUN] achat %s %s, SL %s TP %s",
                           code, formater(quantite), formater(stop), formater(objectif))
            reponse = [{"ordId": "", "sz": formater(quantite)}]
        else:
            reponse = self._appel("POST", "/api/v5/trade/order", corps={
                "instId": code,
                "tdMode": "cash",
                "side": "buy",
                "ordType": "market",
                # Sans tgtCcy, `sz` designerait un montant en euros et non
                # une quantite d'actif : l'ordre serait bon mais faux.
                "tgtCcy": "base_ccy",
                "sz": formater(quantite, regle.decimales_quantite),
                # Stop ET objectif attaches a l'entree : OKX annule l'un
                # quand l'autre part. La position reste bornee des deux
                # cotes meme si le robot s'arrete. « -1 » = sortie au marche.
                "attachAlgoOrds": [{
                    "slTriggerPx": formater(stop, regle.decimales_prix),
                    "slOrdPx": "-1",
                    "slTriggerPxType": "last",
                    "tpTriggerPx": formater(objectif, regle.decimales_prix),
                    "tpOrdPx": "-1",
                    "tpTriggerPxType": "last",
                }],
            })

        identifiant = str(reponse[0].get("ordId", "")) if reponse else ""
        rempli = self._prix_execute(code, identifiant) or reference

        position = Position(
            id=instrument.symbol, symbol=instrument.symbol, side=Side.BUY,
            volume=quantite, entry_price=regle.arrondir_prix(rempli),
            stop_loss=stop, take_profit=objectif,
            opened_at=time.time(), broker_ref=identifiant, comment=comment)
        self._positions[instrument.symbol] = position
        self._instruments[instrument.symbol] = instrument

        logger.info("ACHAT [%s] %s %s @ %s | SL %s TP %s (attaches a l'ordre)",
                    self.mode, code, formater(quantite), formater(position.entry_price),
                    formater(stop), formater(objectif))
        return position

    def _prix_execute(self, code: str, identifiant: str) -> Optional[float]:
        """Prix moyen reellement obtenu, relu sur la plateforme.

        Un ordre au marche ne renvoie pas son prix : il faut le redemander.
        """
        if not identifiant or self.config.dry_run:
            return None
        try:
            data = self._appel("GET", "/api/v5/trade/order",
                               params={"instId": code, "ordId": identifiant})
            prix = float(data[0].get("avgPx", 0) or 0)
            return prix if prix > 0 else None
        except Exception:  # noqa: BLE001
            return None

    # ------------------------------------------------------------------
    def _annuler_protections(self, symbol: str) -> None:
        """Retire les ordres conditionnels en attente sur cet instrument.

        Les stops attaches survivent a la position s'ils ne sont pas
        annules : un ordre orphelin vendrait plus tard des actifs
        appartenant a une autre position.
        """
        if self.config.dry_run:
            return
        code = self.symbol_for(symbol)
        try:
            en_cours = self._appel("GET", "/api/v5/trade/orders-algo-pending",
                                   params={"instType": "SPOT", "instId": code,
                                           "ordType": "oco"})
        except BrokerError as exc:
            logger.warning("protections illisibles sur %s : %s", code, str(exc)[:120])
            return
        a_annuler = [{"instId": code, "algoId": o["algoId"]}
                     for o in en_cours if o.get("algoId")]
        if not a_annuler:
            return
        try:
            self._appel("POST", "/api/v5/trade/cancel-algos", corps=a_annuler)
        except BrokerError as exc:
            logger.warning("annulation des protections sur %s : %s", code, str(exc)[:120])

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        position = self._positions.get(position_id)
        if position is None:
            return False
        regle = self.regle(position.symbol)
        seuil = (position.initial_risk * self.config.stop_move_threshold_r
                 if position.initial_risk else 0.0)

        bouge = False
        if stop_loss is not None:
            bouge = bouge or abs(stop_loss - position.stop_loss) > seuil
            position.stop_loss = regle.arrondir_prix(stop_loss)
        if take_profit is not None:
            bouge = bouge or abs(take_profit - position.take_profit) > seuil
            position.take_profit = regle.arrondir_prix(take_profit)
        if not bouge or self.config.dry_run:
            return True

        code = self.symbol_for(position.symbol)
        try:
            en_cours = self._appel("GET", "/api/v5/trade/orders-algo-pending",
                                   params={"instType": "SPOT", "instId": code,
                                           "ordType": "oco"})
            if not en_cours:
                return False
            self._appel("POST", "/api/v5/trade/amend-algos", corps=[{
                "instId": code,
                "algoId": en_cours[0]["algoId"],
                "newSlTriggerPx": formater(position.stop_loss, regle.decimales_prix),
                "newTpTriggerPx": formater(position.take_profit, regle.decimales_prix),
            }])
        except BrokerError as exc:
            logger.warning("protection non deplacee sur %s : %s", code, str(exc)[:150])
            return False
        return True

    # ------------------------------------------------------------------
    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        position = self._positions.get(position_id)
        if position is None:
            return None
        code = self.symbol_for(position.symbol)
        regle = self.regle(position.symbol)
        quantite = regle.arrondir_quantite(min(volume or position.volume, position.volume))
        if quantite <= 0:
            return None
        partielle = quantite < position.volume - 1e-12

        # Les protections immobilisent la quantite : elles partent d'abord.
        self._annuler_protections(position.symbol)

        if self.config.dry_run:
            logger.warning("[DRY-RUN] vente %s %s (%s)", code, formater(quantite), reason)
            sortie = self._prix(code) or position.entry_price
        else:
            reponse = self._appel("POST", "/api/v5/trade/order", corps={
                "instId": code, "tdMode": "cash", "side": "sell",
                "ordType": "market", "tgtCcy": "base_ccy",
                "sz": formater(quantite, regle.decimales_quantite),
            })
            identifiant = str(reponse[0].get("ordId", "")) if reponse else ""
            sortie = (self._prix_execute(code, identifiant)
                      or self._prix(code) or position.entry_price)

        brut = (sortie - position.entry_price) * quantite
        frais = (position.entry_price + sortie) * quantite * self.config.fee_rate
        profit = brut - frais

        trade = ClosedTrade(
            position_id=position.id, symbol=position.symbol, side=Side.BUY,
            volume=quantite, entry_price=position.entry_price,
            exit_price=regle.arrondir_prix(sortie),
            opened_at=position.opened_at, closed_at=time.time(),
            profit=round(profit, 6), r_multiple=round(position.r_multiple(sortie), 3),
            reason=reason, tp_extensions=position.tp_extensions,
            max_favorable_r=round(position.r_multiple(position.max_favorable), 3),
            partial=partielle)
        self._closed.append(trade)

        position.volume = round(position.volume - quantite, 12)
        if position.volume <= 1e-12:
            self._positions.pop(position_id, None)

        logger.info("VENTE [%s] %s %s -> %+.4f %s (frais %.4f) | %s",
                    self.mode, code, formater(quantite), profit,
                    self.config.quote_asset, frais, reason)
        return trade

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed)

    # ------------------------------------------------------------------
    def tick(self, symbol: str) -> Optional[Tick]:
        try:
            data = self._appel("GET", "/api/v5/market/ticker",
                               params={"instId": self.symbol_for(symbol)}, signe=False)
            ligne = data[0]
            return Tick(time.time(), float(ligne["bidPx"]), float(ligne["askPx"]))
        except Exception:  # noqa: BLE001
            return None
