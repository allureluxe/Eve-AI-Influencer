"""Execution sur Bitvavo (comptant, en euros).

Choisi apres le retrait de Binance du marche europeen : Bitvavo est agree
MiCA par l'AFM (Pays-Bas), donc utilisable par un resident francais sans
sortir du cadre europeen, et cote nativement en EUR — pas de conversion
parasite entre le capital et les paires tradees.

Trois consequences structurelles, qu'il vaut mieux connaitre que subir.

1. ON NE PEUT QU'ACHETER
   Comme tout comptant, pas de vente a decouvert. Le robot ignore ses
   signaux de vente et ne travaille que dans les phases de hausse.

2. LES FRAIS IMPOSENT UNE ECHELLE DE TEMPS PLUS LENTE QUE BINANCE
   Palier de base (moins de 100 000 EUR sur 30 jours) : 0,15 % maker,
   0,25 % taker. Le robot entre et sort au marche, donc taker des deux
   cotes : 0,50 % d'aller-retour, contre 0,20 % sur Binance.

       cout / risque = frais aller-retour / (distance du stop en % du prix)

   Pour maintenir ce rapport sous 15 % — au-dela, les frais mangent la
   moitie de l'esperance — il faut :

       stop minimum = 0,50 % / 0,15 = 3,3 % du prix

   Soit H4, pas H1. Ce n'est pas un reglage a forcer, c'est de
   l'arithmetique. Le meme calcul sur Binance donnait 1,3 % et autorisait
   H1 ; ici la contrainte est 2,5 fois plus dure.

   Le tarif reel du compte est lu au demarrage sur /account/fees : si le
   volume fait descendre le palier, le robot en profite sans qu'on touche
   au code.

3. IL N'Y A PAS D'OCO SUR BITVAVO
   Bitvavo expose market, limit, stopLoss, stopLossLimit, takeProfit et
   takeProfitLimit — mais aucun ordre lie « l'un annule l'autre ».

   On pourrait deposer un stop ET un objectif separement : rien ne les
   relie, donc si le premier part, le second survit et vendra plus tard
   des actifs qui ne lui appartiennent plus — potentiellement ceux d'une
   position rouverte entre-temps sur le meme marche. Ce risque-la est
   inacceptable.

   Le choix retenu : SEUL LE STOP est depose sur la plateforme, sous forme
   de stopLossLimit. L'objectif est gere par le robot. Consequence assumee
   et dissymetrique dans le bon sens — si le robot s'arrete, la perte
   reste bornee par un ordre reel qui vit sans lui ; ce qu'on perd, c'est
   au pire une prise de benefice, jamais la protection.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from ..core import ClosedTrade, Position, Side, Tick
from ..universe import CATALOGUE_CRYPTO, Instrument
from .base import AccountInfo, Broker, BrokerError

logger = logging.getLogger(__name__)

BASE = "https://api.bitvavo.com/v2"

# Le catalogue suit l'univers du robot, il n'est pas tenu a la main ici :
# une seconde liste divergerait silencieusement de la premiere.
ACTIFS = {f"{actif}USD": actif for actif in CATALOGUE_CRYPTO}

# Bitvavo est un marche europeen : sa devise naturelle est l'euro.
DEVISE_DEFAUT = os.getenv("BITVAVO_QUOTE_ASSET", "EUR").upper()

# Palier de base. Remplaces au demarrage par le tarif reel du compte.
FRAIS_TAKER = 0.0025
FRAIS_MAKER = 0.0015

# Fenetre d'acceptation de l'horodatage, en millisecondes.
FENETRE_DEFAUT = 10000

# « You do not have sufficient balance to complete this operation. »
# Vendre un actif qu'on ne detient plus : la position a ete liquidee sur la
# plateforme sans que le robot le sache.
CODE_SOLDE_INSUFFISANT = 216


def code_erreur(exc: BaseException) -> int:
    """Code d'erreur Bitvavo porte par le message (« ... [216] ... »).

    Le code voyage dans le texte de l'exception plutot que dans un attribut :
    l'extraire ici evite de comparer des phrases, que Bitvavo peut reformuler.
    """
    trouve = re.search(r"\[(\d+)\]", str(exc))
    return int(trouve.group(1)) if trouve else 0


def marche(symbole: str, devise: str = "") -> Optional[str]:
    """Code Bitvavo d'un symbole du robot.

    Exemple : marche("BTCUSD", "EUR") -> "BTC-EUR"
    """
    actif = ACTIFS.get(symbole.upper())
    if not actif:
        return None
    return f"{actif}-{(devise or DEVISE_DEFAUT).upper()}"


def formater(valeur: float, decimales: int = 12) -> str:
    """Ecrit un nombre en decimal simple, jamais en notation scientifique.

    `str(1e-05)` donne « 1e-05 », que Bitvavo refuse. Les montants partent
    donc toujours par ici.
    """
    texte = f"{valeur:.{max(0, decimales)}f}"
    if "." in texte:
        texte = texte.rstrip("0").rstrip(".")
    return texte or "0"


@dataclass(slots=True)
class BitvavoConfig:
    api_key: str = ""
    api_secret: str = ""
    quote_asset: str = DEVISE_DEFAUT
    window: int = FENETRE_DEFAUT
    timeout: float = 15.0
    dry_run: bool = True
    fee_rate: float = FRAIS_TAKER
    stop_move_threshold_r: float = 0.15
    # Identifiant numerique du robot qui passe l'ordre. Bitvavo l'exige
    # depuis MiCA, au titre de la tracabilite : chaque ordre doit pouvoir
    # etre rattache a l'operateur — humain ou automate — qui l'a emis.
    # Sans lui : « 400 [203] operatorId parameter is required ».
    operator_id: int = 1

    @classmethod
    def from_env(cls) -> "BitvavoConfig":
        return cls(
            api_key=os.getenv("BITVAVO_API_KEY", "").strip(),
            api_secret=os.getenv("BITVAVO_API_SECRET", "").strip(),
            quote_asset=os.getenv("BITVAVO_QUOTE_ASSET", DEVISE_DEFAUT).upper(),
            window=int(os.getenv("BITVAVO_WINDOW", str(FENETRE_DEFAUT)) or FENETRE_DEFAUT),
            timeout=float(os.getenv("BITVAVO_TIMEOUT", "15") or 15),
            dry_run=os.getenv("BITVAVO_DRY_RUN", "1").strip() not in ("0", "false", "False", ""),
            fee_rate=float(os.getenv("BITVAVO_FEE_RATE", str(FRAIS_TAKER)) or FRAIS_TAKER),
            stop_move_threshold_r=float(
                os.getenv("BITVAVO_STOP_MOVE_THRESHOLD_R", "0.15") or 0.15),
            operator_id=int(os.getenv("BITVAVO_OPERATOR_ID", "1") or 1),
        )


@dataclass(slots=True)
class RegleMarche:
    """Contraintes reelles de Bitvavo pour un marche."""

    market: str
    price_precision: int = 5      # CHIFFRES SIGNIFICATIFS, pas decimales
    amount_decimals: int = 8
    min_amount: float = 0.0
    min_notional: float = 5.0

    def arrondir_quantite(self, quantite: float) -> float:
        """Arrondi VERS LE BAS au pas de l'actif.

        Vers le bas et jamais vers le haut : un arrondi genereux ferait
        depasser a chaque ordre le risque calcule en amont.
        """
        if quantite <= 0:
            return 0.0
        facteur = 10 ** max(0, self.amount_decimals)
        return math.floor(quantite * facteur) / facteur

    def arrondir_prix(self, prix: float) -> float:
        """Arrondi au nombre de chiffres SIGNIFICATIFS impose par Bitvavo.

        Piege classique de cette plateforme : `pricePrecision` ne compte pas
        les decimales mais les chiffres significatifs. Avec 5, le BTC a
        61 234,7 s'ecrit 61 235 et le PEPE a 0,000012345 garde ses cinq
        chiffres utiles. Traiter ce champ comme un nombre de decimales
        casserait l'un ou l'autre bout du catalogue.
        """
        if prix <= 0 or not math.isfinite(prix):
            return prix
        exposant = math.floor(math.log10(abs(prix)))
        decimales = max(0, self.price_precision - 1 - exposant)
        return round(prix, min(decimales, 12))


class BitvavoBroker(Broker):
    """Achat au comptant sur Bitvavo, stop depose sur la plateforme."""

    name = "bitvavo"
    is_live = True
    supports_short = False        # le comptant ne permet pas la vente a decouvert

    def __init__(self, config: Optional[BitvavoConfig] = None) -> None:
        self.config = config or BitvavoConfig.from_env()
        self.base = BASE
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = {}
        self._closed: list[ClosedTrade] = []
        self._regles: dict[str, RegleMarche] = {}
        self._account = AccountInfo(0.0, 0.0, self.config.quote_asset)
        self._soldes: dict[str, float] = {}
        self._stops: dict[str, str] = {}
        # Niveau de declenchement REELLEMENT depose chez Bitvavo, par marche.
        # Il ne peut pas etre deduit de Position.stop_loss : le gestionnaire
        # de position ecrit son nouveau niveau dans cet objet avant que le
        # broker soit appele (cf. modify_position).
        self._stop_pose: dict[str, float] = {}
        self._last_error = ""
        self._quota_restant = 1000
        self._quota_reset = 0.0

    # ------------------------------------------------------------------
    @property
    def mode(self) -> str:
        return "simulation (dry-run)" if self.config.dry_run else "REEL"

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def symbol_for(self, symbol: str) -> str:
        code = marche(symbol, self.config.quote_asset)
        if not code:
            raise BrokerError(f"{symbol} n'est pas disponible sur Bitvavo")
        return code

    def supports(self, symbol: str) -> bool:
        """L'instrument est-il reellement cotable dans la devise choisie ?

        Bitvavo ne liste pas tout le catalogue crypto, et surtout pas l'or :
        une fois les marches charges, ils font foi. Tant qu'ils ne le sont
        pas, on ne prejuge de rien — sinon le demarrage viderait l'univers.
        """
        if symbol.upper() not in ACTIFS:
            return False
        if not self._regles:
            return True
        return marche(symbol, self.config.quote_asset) in self._regles

    def regle(self, symbol: str) -> RegleMarche:
        code = self.symbol_for(symbol)
        return self._regles.get(code, RegleMarche(market=code))

    # ------------------------------------------------------------------
    # Signature et appels
    # ------------------------------------------------------------------
    def _signer(self, horodatage: int, methode: str, chemin: str,
                corps: Optional[dict]) -> str:
        """HMAC-SHA256 de : horodatage + methode + /v2 + chemin + corps.

        Le corps doit etre serialise exactement comme il sera envoye, d'ou
        les separateurs compacts : un espace de difference et la signature
        ne correspond plus.
        """
        message = f"{horodatage}{methode}/v2{chemin}"
        if corps:
            message += json.dumps(corps, separators=(",", ":"))
        return hmac.new(self.config.api_secret.encode("utf-8"),
                        message.encode("utf-8"), hashlib.sha256).hexdigest()

    def _appel(self, methode: str, chemin: str, params: Optional[dict] = None,
               corps: Optional[dict] = None, signe: bool = True) -> Any:
        """Appel REST signe, avec lecture du quota et des erreurs Bitvavo."""
        requete = chemin
        if params:
            requete += "?" + "&".join(f"{c}={v}" for c, v in params.items())

        entetes = {"User-Agent": "gold-bot/1.0", "Accept": "application/json"}
        donnees = None
        if corps:
            donnees = json.dumps(corps, separators=(",", ":")).encode("utf-8")
            entetes["Content-Type"] = "application/json"

        if signe:
            if not (self.config.api_key and self.config.api_secret):
                raise BrokerError("BITVAVO_API_KEY et BITVAVO_API_SECRET absents")
            horodatage = int(time.time() * 1000)
            entetes.update({
                "bitvavo-access-key": self.config.api_key,
                "bitvavo-access-signature": self._signer(horodatage, methode, requete, corps),
                "bitvavo-access-timestamp": str(horodatage),
                "bitvavo-access-window": str(self.config.window),
            })

        self._attendre_le_quota()

        req = urllib.request.Request(self.base + requete, data=donnees,
                                     headers=entetes, method=methode)
        ctx = ssl.create_default_context()
        ca = os.getenv("GB_CA_BUNDLE") or "/root/.ccr/ca-bundle.crt"
        if os.path.exists(ca):
            try:
                ctx.load_verify_locations(ca)
            except Exception:  # pragma: no cover - environnement sans bundle
                pass
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout, context=ctx) as resp:
                self._noter_le_quota(dict(resp.headers))
                brut = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            code, message = self._lire_erreur(detail)
            if code == 105:
                # Quota depasse : Bitvavo indique dans le message l'instant
                # de levee. On le retient pour ne pas insister.
                self._quota_restant = 0
                self._quota_reset = self._instant_de_levee(message)
            raise BrokerError(
                f"Bitvavo {exc.code} sur {methode} {chemin}"
                + (f" [{code}] {message}" if message else "")) from exc
        except Exception as exc:  # noqa: BLE001
            raise BrokerError(f"Bitvavo injoignable sur {chemin} : {exc}") from exc

        try:
            reponse = json.loads(brut)
        except json.JSONDecodeError as exc:
            raise BrokerError(f"Bitvavo: reponse illisible sur {chemin}") from exc
        if isinstance(reponse, dict) and "errorCode" in reponse:
            raise BrokerError(f"Bitvavo [{reponse['errorCode']}] "
                              f"{reponse.get('error', '')} sur {chemin}")
        return reponse

    @staticmethod
    def _lire_erreur(brut: str) -> tuple[int, str]:
        try:
            data = json.loads(brut)
        except Exception:  # noqa: BLE001
            return 0, brut[:200]
        return int(data.get("errorCode", 0) or 0), str(data.get("error", ""))[:200]

    @staticmethod
    def _instant_de_levee(message: str) -> float:
        """Extrait l'horodatage de levee du bannissement, en secondes.

        Le message a la forme « ... at 1700000000000. » ; en cas de doute on
        retombe sur une minute d'attente plutot que de marteler l'API.
        """
        for morceau in message.replace(".", " ").split():
            if morceau.isdigit() and len(morceau) >= 13:
                return int(morceau) / 1000.0
        return time.time() + 60.0

    def _noter_le_quota(self, entetes: dict) -> None:
        bas = {c.lower(): v for c, v in entetes.items()}
        if "bitvavo-ratelimit-remaining" in bas:
            try:
                self._quota_restant = int(bas["bitvavo-ratelimit-remaining"])
            except ValueError:
                pass
        if "bitvavo-ratelimit-resetat" in bas:
            try:
                self._quota_reset = int(bas["bitvavo-ratelimit-resetat"]) / 1000.0
            except ValueError:
                pass

    def _attendre_le_quota(self) -> None:
        """Ne pas envoyer une requete qu'on sait refusee.

        Bitvavo accorde un budget de 1000 points par minute et bannit
        temporairement au-dela. Le robot scanne des dizaines de marches : la
        marge de securite evite qu'un cycle un peu large ne coupe l'acces
        au moment ou une position a besoin d'etre fermee.
        """
        if self._quota_restant > 5:
            return
        attente = self._quota_reset - time.time()
        if attente <= 0:
            self._quota_restant = 1000
            return
        logger.warning("quota Bitvavo epuise : pause de %.1f s", attente)
        time.sleep(min(attente, 60.0))
        self._quota_restant = 1000

    # ------------------------------------------------------------------
    def connect(self) -> bool:
        cfg = self.config
        if cfg.dry_run and not (cfg.api_key and cfg.api_secret):
            logger.warning("Bitvavo en simulation sans cle : solde fictif")
            solde = float(os.getenv("BITVAVO_DRYRUN_EQUITY", "50") or 50)
            self._account = AccountInfo(solde, solde, cfg.quote_asset)
            try:
                self._charger_regles()
            except BrokerError as exc:
                logger.warning("marches Bitvavo non charges : %s", str(exc)[:150])
            return True
        if not (cfg.api_key and cfg.api_secret):
            self._last_error = "BITVAVO_API_KEY et BITVAVO_API_SECRET absents"
            logger.error("connexion Bitvavo impossible : %s", self._last_error)
            return False
        try:
            self._charger_regles()
            self._charger_frais()
            self.sync()
            if cfg.dry_run:
                logger.warning("Bitvavo en simulation : lecture reelle, "
                               "aucun ordre ne sera envoye")
            logger.info("Bitvavo connecte [%s] : %.2f %s",
                        self.mode, self._account.equity, cfg.quote_asset)
            if not cfg.dry_run:
                logger.warning("MODE REEL : les ordres engagent de l'argent veritable")
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            logger.error("connexion Bitvavo echouee : %s", str(exc)[:250])
            return False

    def healthy(self) -> bool:
        return not self._last_error

    # ------------------------------------------------------------------
    def _charger_regles(self) -> None:
        """Contraintes reelles de la plateforme, lues et non devinees."""
        marches = self._appel("GET", "/markets", signe=False)
        decimales = self._decimales_des_actifs()
        attendus = {marche(sym, self.config.quote_asset) for sym in ACTIFS}
        for ligne in marches if isinstance(marches, list) else []:
            code = ligne.get("market")
            if code not in attendus or ligne.get("status") != "trading":
                continue
            base_asset = str(ligne.get("base", "")).upper()
            self._regles[code] = RegleMarche(
                market=code,
                price_precision=int(ligne.get("pricePrecision", 5) or 5),
                amount_decimals=decimales.get(base_asset, 8),
                min_amount=float(ligne.get("minOrderInBaseAsset", 0) or 0),
                min_notional=float(ligne.get("minOrderInQuoteAsset", 5) or 5),
            )
        logger.info("marches Bitvavo charges : %d cotable(s) en %s",
                    len(self._regles), self.config.quote_asset)

    def _decimales_des_actifs(self) -> dict[str, int]:
        """Precision de quantite propre a chaque actif.

        Elle ne figure pas dans /markets : c'est /assets qui la porte. Sans
        elle on arrondirait toutes les quantites a huit decimales, ce que
        certains actifs refusent.
        """
        try:
            actifs = self._appel("GET", "/assets", signe=False)
        except BrokerError as exc:
            logger.warning("precision des actifs non lue (%s) : 8 decimales par defaut",
                           str(exc)[:120])
            return {}
        return {str(a.get("symbol", "")).upper(): int(a.get("decimals", 8) or 8)
                for a in actifs if isinstance(a, dict)}

    def _charger_frais(self) -> None:
        """Lit le palier tarifaire reel du compte plutot que de le supposer."""
        try:
            frais = self._appel("GET", "/account/fees")
        except BrokerError as exc:
            logger.warning("tarif Bitvavo non lu (%s) : palier de base retenu",
                           str(exc)[:120])
            return
        taker = frais.get("taker") if isinstance(frais, dict) else None
        if taker is None:
            return
        try:
            self.config.fee_rate = float(taker)
        except (TypeError, ValueError):
            return
        logger.info("tarif Bitvavo du compte : taker %.4f %% — "
                    "stop minimum conseille %.2f %% du prix",
                    self.config.fee_rate * 100,
                    (2 * self.config.fee_rate / 0.15) * 100)

    def notionnel_minimum(self) -> float:
        """Ticket d'entree median impose par la plateforme.

        Sert a estimer combien de positions le capital permet de tenir. La
        mediane suffit : chaque ordre est de toute facon verifie
        individuellement contre le minimum de son propre marche au moment de
        l'execution.
        """
        valeurs = sorted(r.min_notional for r in self._regles.values() if r.min_notional > 0)
        if not valeurs:
            return 5.0
        return valeurs[len(valeurs) // 2]

    def apply_market_rules(self, universe) -> list[str]:
        modifies: list[str] = []
        for inst in universe:
            code = marche(inst.symbol, self.config.quote_asset)
            regle = self._regles.get(code) if code else None
            if regle is None:
                continue
            pas = 10 ** -max(0, regle.amount_decimals)
            minimum = regle.min_amount or pas
            if abs(inst.min_lot - minimum) > 1e-12 or abs(inst.lot_step - pas) > 1e-12:
                modifies.append(f"{inst.symbol} lot min {inst.min_lot} -> {minimum}")
                inst.min_lot = minimum
                inst.lot_step = pas
        for ligne in modifies:
            logger.info("contrainte alignee sur Bitvavo : %s", ligne)
        return modifies

    # ------------------------------------------------------------------
    def sync(self) -> None:
        """Lit les soldes et reconstitue la valeur du compte en devise.

        En comptant il n'existe pas de « position » cote plateforme : on
        detient des actifs. Le capital total est donc le solde en euros plus
        la valeur de marche de ce qui est detenu.
        """
        soldes = self._appel("GET", "/balance")
        self._soldes = {}
        disponible = 0.0
        quote = self.config.quote_asset
        for ligne in soldes if isinstance(soldes, list) else []:
            actif = str(ligne.get("symbol", "")).upper()
            libre = float(ligne.get("available", 0) or 0)
            bloque = float(ligne.get("inOrder", 0) or 0)
            if libre + bloque > 0:
                self._soldes[actif] = libre + bloque
            if actif == quote:
                disponible = libre

        total = self._soldes.get(quote, 0.0)
        prix_tous = self._prix_du_marche()
        for actif, quantite in self._soldes.items():
            if actif == quote:
                continue
            prix = prix_tous.get(f"{actif}-{quote}")
            if prix:
                total += quantite * prix

        self._account = AccountInfo(equity=total, balance=total, currency=quote,
                                    margin_used=max(0.0, total - disponible),
                                    margin_free=disponible, leverage=1.0)
        self._last_error = ""
        self._reconcilier(prix_tous)

    # ------------------------------------------------------------------
    # Rapprochement des positions avec les avoirs reels
    # ------------------------------------------------------------------
    def _reconcilier(self, prix_tous: dict[str, float]) -> None:
        """Detecte les positions liquidees sur la plateforme sans le robot.

        Le stop est un ordre reel depose chez Bitvavo (cf. l'en-tete du
        module) : quand il se declenche, l'actif part sans que le robot en
        soit averti. Rien, jusqu'ici, ne le lui apprenait.

        Observe en production le 23 aout : ETH vendu par son stop a 15h20,
        puis « [216] insufficient balance » toutes les vingt secondes
        jusqu'au soir. Trois degats, du moins grave au plus grave : un
        journal illisible, une place de position occupee pour rien, et
        surtout une perte jamais comptabilisee — donc invisible pour le
        plafond de pertes journalieres et pour la ponderation adaptative.
        Un coupe-circuit aveugle sur ses propres pertes ne protege personne.

        Le solde fait donc foi, a chaque cycle : ce que le compte ne detient
        plus n'est plus une position ouverte.
        """
        if self.config.dry_run:
            return
        for position in list(self._positions.values()):
            actif = ACTIFS.get(position.symbol.upper(), "")
            if not actif:
                continue
            detenu = self._soldes.get(actif, 0.0)
            # Marge de tolerance : les frais preleves en actif et les
            # arrondis de la plateforme grignotent quelques fractions de
            # pourcent. En dessous, on n'invente pas une liquidation.
            if detenu >= position.volume * 0.98:
                continue
            code = self.symbol_for(position.symbol)
            prix = prix_tous.get(code) or position.stop_loss
            self._liquidation_externe(position, detenu, prix)

    def _liquidation_externe(self, position: Position, detenu: float,
                             prix_marche: float) -> Optional[ClosedTrade]:
        """Comptabilise ce que la plateforme a vendu sans passer par le robot.

        Renvoie le trade ferme, ou None si la position n'a pas assez bouge
        pour conclure. Le reliquat invendable — trop petit pour repasser le
        minimum du marche — compte comme ferme : le garder ouvert
        reproduirait exactement la boucle qu'on corrige.
        """
        regle = self.regle(position.symbol)
        code = regle.market
        reste = max(0.0, regle.arrondir_quantite(detenu))
        invendable = (reste < regle.min_amount
                      or reste * max(prix_marche, 0.0) < regle.min_notional)
        quantite = position.volume if invendable else round(position.volume - reste, 12)
        if quantite <= 0:
            return None

        sortie, servi, frais = self._ventes_depuis(code, position.opened_at)
        if not sortie:
            # Sans historique lisible, le stop est l'explication la plus
            # probable : on retient son niveau plutot que d'inventer un prix
            # flatteur. L'estimation est signalee dans le journal.
            sortie = position.stop_loss or prix_marche
            frais = (position.entry_price + sortie) * quantite * self.config.fee_rate
            estime = " (prix estime au stop)"
        else:
            estime = ""
        if servi and 0 < servi < quantite:
            quantite = servi

        brut = (sortie - position.entry_price) * quantite
        trade = ClosedTrade(
            position_id=position.id, symbol=position.symbol, side=Side.BUY,
            volume=quantite, entry_price=position.entry_price,
            exit_price=regle.arrondir_prix(sortie),
            opened_at=position.opened_at, closed_at=time.time(),
            profit=round(brut - frais, 6),
            r_multiple=round(position.r_multiple(sortie), 3),
            reason="stop declenche sur la plateforme",
            tp_extensions=position.tp_extensions,
            max_favorable_r=round(position.r_multiple(position.max_favorable), 3),
            partial=not invendable)
        self._closed.append(trade)

        if invendable:
            self._positions.pop(position.id, None)
            # Un reliquat d'ordre peut survivre a un stop partiellement
            # servi : il vendrait plus tard des actifs d'une autre position.
            self._annuler_stop(position.symbol)
        else:
            position.volume = reste

        logger.warning(
            "RAPPROCHEMENT %s : vendu %s hors du robot -> %+.4f %s%s | "
            "position %s",
            code, formater(quantite), trade.profit, self.config.quote_asset,
            estime, "fermee" if invendable else f"reduite a {formater(reste)}")
        return trade

    def _ventes_depuis(self, code: str, depuis: float) -> tuple[float, float, float]:
        """Prix moyen, quantite et frais des ventes reelles sur ce marche.

        Le vrai prix d'execution du stop plutot qu'une approximation : c'est
        lui qui decide si le trade est comptabilise en perte juste ou en
        perte inventee. `depuis` est en secondes, Bitvavo compte en
        millisecondes.
        """
        try:
            lignes = self._appel("GET", "/trades",
                                 params={"market": code, "limit": 100})
        except BrokerError as exc:
            logger.warning("executions %s illisibles : %s", code, str(exc)[:120])
            return 0.0, 0.0, 0.0
        quantite = valeur = frais = 0.0
        for ligne in lignes if isinstance(lignes, list) else []:
            if str(ligne.get("side", "")).lower() != "sell":
                continue
            try:
                instant = float(ligne.get("timestamp", 0) or 0) / 1000.0
                q = float(ligne.get("amount", 0) or 0)
                prix = float(ligne.get("price", 0) or 0)
            except (TypeError, ValueError):
                continue
            if q <= 0 or prix <= 0 or instant < depuis:
                continue
            quantite += q
            valeur += q * prix
            try:
                frais += abs(float(ligne.get("fee", 0) or 0))
            except (TypeError, ValueError):
                pass
        return (valeur / quantite if quantite else 0.0), quantite, frais

    def _prix_du_marche(self) -> dict[str, float]:
        """Tous les derniers prix en un appel plutot qu'un par actif detenu."""
        try:
            lignes = self._appel("GET", "/ticker/price", signe=False)
        except BrokerError:
            return {}
        prix: dict[str, float] = {}
        for ligne in lignes if isinstance(lignes, list) else []:
            try:
                prix[str(ligne["market"])] = float(ligne["price"])
            except (KeyError, TypeError, ValueError):
                continue
        return prix

    def _prix(self, code: str) -> Optional[float]:
        try:
            data = self._appel("GET", "/ticker/price", params={"market": code}, signe=False)
            return float(data["price"])
        except Exception:  # noqa: BLE001
            return None

    def account(self) -> AccountInfo:
        return self._account

    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def reprendre(self, position: Position) -> bool:
        """Redeclare une position memorisee apres un redemarrage.

        Bitvavo ne connait que des avoirs : au demarrage le robot repart
        avec zero position, alors que l'actif est toujours la et que son
        stop dort chez la plateforme. Tout ce que le robot est seul a
        assurer — l'objectif, le break-even, le trailing, le compte des
        places occupees — s'arretait donc au premier redemarrage, sans le
        moindre message. Les redemarrages du 23 aout tombent en plein
        milieu des trades de la journee.

        La position est reprise meme si l'actif a disparu entre-temps : le
        rapprochement du cycle suivant comptabilisera la sortie sur les
        executions reelles, plutot que de perdre le trade en silence.
        """
        if not self.supports(position.symbol):
            return False
        if position.id in self._positions:
            return True
        self._positions[position.id] = position
        logger.info("gestion reprise sur %s : %s a %s, stop %s",
                    self.symbol_for(position.symbol), formater(position.volume),
                    formater(position.entry_price), formater(position.stop_loss))
        return True

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
        if regle.min_amount and quantite < regle.min_amount:
            raise BrokerError(
                f"quantite {formater(quantite)} sous le minimum "
                f"{formater(regle.min_amount)} sur {code}")
        if quantite <= 0:
            raise BrokerError(f"quantite nulle apres arrondi sur {code}")

        reference = self._prix(code) or (stop_loss + take_profit) / 2.0
        notionnel = quantite * reference
        if notionnel < regle.min_notional:
            raise BrokerError(
                f"notionnel {notionnel:.2f} {self.config.quote_asset} sous le minimum "
                f"{regle.min_notional} sur {code}")
        # Les frais se prelevent en plus du notionnel : un ordre calibre au
        # centime pres sur le solde disponible serait refuse pour quelques
        # centimes de commission.
        marge = self._account.margin_free
        if marge > 0 and notionnel > marge * 0.995:
            raise BrokerError(
                f"notionnel {notionnel:.2f} au-dela du disponible "
                f"{marge:.2f} {self.config.quote_asset}, frais compris")

        if self.config.dry_run:
            logger.warning("[DRY-RUN] achat %s %s, SL %s TP %s",
                           code, formater(quantite), formater(stop_loss),
                           formater(take_profit))
            reponse = {"filledAmount": formater(quantite),
                       "filledAmountQuote": formater(notionnel), "orderId": ""}
        else:
            reponse = self._appel("POST", "/order", corps={
                "market": code, "side": "buy", "orderType": "market",
                "amount": formater(quantite, regle.amount_decimals),
                "operatorId": self.config.operator_id,
            })

        rempli = self._prix_moyen(reponse) or reference
        obtenu = float(reponse.get("filledAmount", quantite) or quantite)

        position = Position(
            id=instrument.symbol, symbol=instrument.symbol, side=Side.BUY,
            volume=obtenu, entry_price=regle.arrondir_prix(rempli),
            stop_loss=regle.arrondir_prix(stop_loss),
            take_profit=regle.arrondir_prix(take_profit),
            opened_at=time.time(), broker_ref=str(reponse.get("orderId", "")), comment=comment)
        self._positions[instrument.symbol] = position
        self._instruments[instrument.symbol] = instrument

        self._poser_stop(position)
        logger.info("ACHAT [%s] %s %s @ %s | SL %s TP %s (objectif suivi par le robot)",
                    self.mode, code, formater(obtenu), formater(position.entry_price),
                    formater(position.stop_loss), formater(position.take_profit))
        return position

    @staticmethod
    def _prix_moyen(reponse: dict) -> Optional[float]:
        """Prix moyen reellement obtenu, calcule sur les executions."""
        remplis = reponse.get("fills") or []
        if remplis:
            total_q = sum(float(f["amount"]) for f in remplis)
            total_v = sum(float(f["amount"]) * float(f["price"]) for f in remplis)
            if total_q > 0:
                return total_v / total_q
        try:
            q = float(reponse.get("filledAmount", 0) or 0)
            v = float(reponse.get("filledAmountQuote", 0) or 0)
        except (TypeError, ValueError):
            return None
        return v / q if q > 0 else None

    # ------------------------------------------------------------------
    def _poser_stop(self, position: Position) -> None:
        """Depose le stop sur la plateforme, en stopLossLimit.

        La limite est placee legerement sous le declenchement pour que
        l'ordre parte meme si le prix glisse : une limite posee pile au
        niveau du stop peut rester non servie exactement quand elle compte.

        Faute d'OCO chez Bitvavo, l'objectif n'est PAS depose ici — voir
        l'en-tete du module. Si le stop ne peut pas etre pose, la position
        est refermee immediatement : une position sans protection est
        inacceptable.
        """
        if self.config.dry_run:
            return
        code = self.symbol_for(position.symbol)
        regle = self.regle(position.symbol)
        declenchement = regle.arrondir_prix(position.stop_loss)
        limite = regle.arrondir_prix(position.stop_loss * 0.998)
        try:
            reponse = self._appel("POST", "/order", corps={
                "market": code, "side": "sell", "orderType": "stopLossLimit",
                "operatorId": self.config.operator_id,
                "amount": formater(regle.arrondir_quantite(position.volume),
                                   regle.amount_decimals),
                "price": formater(limite),
                "triggerType": "price",
                "triggerReference": "lastTrade",
                "triggerAmount": formater(declenchement),
            })
            self._stops[position.symbol] = str(reponse.get("orderId", ""))
            self._stop_pose[position.symbol] = declenchement
        except BrokerError as exc:
            logger.error("stop non pose sur %s : %s", code, str(exc)[:200])
            logger.error("fermeture immediate : une position sans stop est inacceptable")
            self.close_position(position.id, reason="stop impossible a poser")
            raise

    def _annuler_stop(self, symbol: str) -> None:
        """Retire les ordres en attente sur ce marche.

        On annule tout le marche et pas seulement l'identifiant retenu : un
        ordre orphelin laisse par un redemarrage vendrait sinon des actifs
        qui appartiennent desormais a une autre position.
        """
        if self.config.dry_run:
            self._stops.pop(symbol, None)
            self._stop_pose.pop(symbol, None)
            return
        try:
            self._appel("DELETE", "/orders",
                        params={"market": self.symbol_for(symbol),
                                "operatorId": self.config.operator_id})
        except BrokerError as exc:
            logger.warning("annulation des ordres sur %s : %s", symbol, str(exc)[:120])
        self._stops.pop(symbol, None)
        self._stop_pose.pop(symbol, None)

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        position = self._positions.get(position_id)
        if position is None:
            return False
        regle = self.regle(position.symbol)
        seuil = (position.initial_risk * self.config.stop_move_threshold_r
                 if position.initial_risk else 0.0)

        # L'objectif n'est pas depose sur la plateforme : le deplacer ne
        # coute donc aucun appel reseau et ne justifie pas de reposer le stop.
        if take_profit is not None:
            position.take_profit = regle.arrondir_prix(take_profit)

        if stop_loss is None:
            return True

        # LE NIVEAU DE REFERENCE EST CELUI DE LA PLATEFORME, PAS CELUI DE
        # L'OBJET POSITION.
        #
        # Le gestionnaire de position ecrit son nouveau stop dans
        # Position.stop_loss avant d'emettre l'action, et cet objet est
        # celui-la meme que le broker detient. Comparer l'un a l'autre
        # revenait donc a comparer une valeur a elle-meme : l'ecart valait
        # toujours zero, « bouge » toujours faux, et l'ordre n'etait JAMAIS
        # repose. La methode renvoyait True — succes — sans avoir rien
        # envoye.
        #
        # Consequence observee le 23 aout : le robot croyait son stop
        # remonte a +3,6R sur HBAR (passe par +4,9R) pendant que Bitvavo
        # tenait toujours l'ordre initial a -1R. Le break-even, le stop
        # suiveur et le verrouillage sur extension etaient tous inoperants
        # en reel — et invisibles, puisque le simulateur, lui, applique le
        # deplacement sans condition.
        pose = self._stop_pose.get(position.symbol)
        nouveau = regle.arrondir_prix(stop_loss)
        bouge = pose is None or abs(nouveau - pose) > seuil
        position.stop_loss = nouveau
        if not bouge:
            return True

        self._annuler_stop(position.symbol)
        try:
            self._poser_stop(position)
        except BrokerError:
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

        # Le stop immobilise la quantite : il doit partir avant la vente.
        self._annuler_stop(position.symbol)

        if self.config.dry_run:
            logger.warning("[DRY-RUN] vente %s %s (%s)", code, formater(quantite), reason)
            reponse = {"filledAmount": formater(quantite),
                       "filledAmountQuote": formater(
                           quantite * (self._prix(code) or position.entry_price))}
        else:
            try:
                reponse = self._appel("POST", "/order", corps={
                    "market": code, "side": "sell", "orderType": "market",
                    "amount": formater(quantite, regle.amount_decimals),
                    "operatorId": self.config.operator_id,
                })
            except BrokerError as exc:
                if code_erreur(exc) != CODE_SOLDE_INSUFFISANT:
                    raise
                # On vend un actif qu'on ne detient plus : le stop est parti
                # de son cote. Relancer l'ordre au cycle suivant echouerait
                # a l'identique, indefiniment. On solde la position sur ce
                # que le compte detient reellement, et l'affaire est close.
                logger.warning("%s : solde insuffisant, la position a ete "
                               "liquidee sur la plateforme", code)
                deja = len(self._closed)
                self.sync()   # le rapprochement s'y fait, sur les soldes reels
                if position.id in self._positions:
                    detenu = self._soldes.get(
                        ACTIFS.get(position.symbol.upper(), ""), 0.0)
                    return self._liquidation_externe(
                        position, detenu, self._prix(code) or position.stop_loss)
                for ferme in self._closed[deja:]:
                    if ferme.position_id == position.id:
                        return ferme
                return None

        sortie = self._prix_moyen(reponse) or position.entry_price
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
        else:
            self._poser_stop(position)

        logger.info("VENTE [%s] %s %s -> %+.4f %s (frais %.4f) | %s",
                    self.mode, code, formater(quantite), profit,
                    self.config.quote_asset, frais, reason)
        return trade

    def closed_trades(self) -> list[ClosedTrade]:
        return list(self._closed)

    # ------------------------------------------------------------------
    def tick(self, symbol: str) -> Optional[Tick]:
        try:
            data = self._appel("GET", "/ticker/book",
                               params={"market": self.symbol_for(symbol)}, signe=False)
            tailles = (data.get("bidSize"), data.get("askSize"))
            return Tick(time.time(), float(data["bid"]), float(data["ask"]),
                        *(float(t) if t not in (None, "") else None for t in tailles))
        except Exception:  # noqa: BLE001
            return None
