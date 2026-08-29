"""Univers d'instruments scannes par le robot.

Le robot est libre du choix du produit : il evalue tous les instruments
actifs et ne prend que la meilleure opportunite validee. L'or reste
prioritaire (poids de conviction plus eleve), mais si aucun facteur n'est
valide sur XAUUSD il bascule sur une autre paire ou une crypto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(slots=True)
class Instrument:
    """Definition d'un instrument tradable."""

    symbol: str
    asset_class: str          # "metal" | "forex" | "crypto" | "index" | "energy"
    digits: int               # decimales de cotation
    contract_size: float      # unites par lot (valeur d'1.0 de variation de prix par lot)
    min_lot: float
    lot_step: float
    max_lot: float
    round_step: float         # pas des chiffres ronds psychologiques
    typical_spread: float     # spread normal, en prix
    max_spread: float         # au-dela : on ne trade pas
    sessions: tuple[tuple[int, int], ...] = ()   # fenetres UTC (heure debut, heure fin), vide = 24/7
    weekend: bool = False     # tradable le week-end (crypto)
    priority: float = 1.0     # multiplicateur de conviction (l'or est privilegie)
    quote_currency: str = "USD"
    enabled: bool = True
    # Correlations connues, pour ne pas empiler des risques identiques
    correlation_group: str = ""

    def normalize_lot(self, lot: float, round_down: bool = False) -> float:
        """Aligne un volume sur le pas du broker.

        `round_down=True` arrondit vers le bas : c'est ce qu'il faut pour
        dimensionner une position. Arrondir au plus proche peut faire
        depasser le risque vise (0.065 -> 0.07 lot, soit 8 % de risque en
        plus que prevu). Sur le risque, on arrondit toujours en sa faveur.
        """
        if lot <= 0:
            return 0.0
        ratio = lot / self.lot_step
        steps = math.floor(ratio + 1e-9) if round_down else round(ratio)
        lot = max(self.min_lot, min(self.max_lot, steps * self.lot_step))
        return round(lot, 8)

    def value_per_price_unit(self, lots: float) -> float:
        """Combien vaut 1.0 de variation de prix pour ce volume (en devise du compte)."""
        return lots * self.contract_size

    def is_open(self, ts: Optional[float] = None) -> bool:
        """Le marche est-il ouvert a cet instant (UTC) ?"""
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
        weekday = dt.weekday()   # 0 = lundi, 5 = samedi, 6 = dimanche

        if not self.weekend:
            # Le forex/metaux ouvrent dimanche 22h UTC et ferment vendredi 21h UTC.
            if weekday == 5:
                return False
            if weekday == 6 and dt.hour < 22:
                return False
            if weekday == 4 and dt.hour >= 21:
                return False

        if not self.sessions:
            return True
        hour = dt.hour + dt.minute / 60.0
        for start, end in self.sessions:
            if start <= end:
                if start <= hour < end:
                    return True
            else:  # session qui passe minuit
                if hour >= start or hour < end:
                    return True
        return False


# Sessions UTC : Londres 07h-16h, New York 12h-21h.
# Le chevauchement 12h-16h concentre l'essentiel du volume sur l'or et le forex.
LONDON_NY = ((7, 21),)
LONDON_NY_OVERLAP = ((12, 17),)


# ---------------------------------------------------------------------------
# Catalogue crypto : actif Binance -> groupe de correlation.
#
# Les groupes evitent d'empiler trois fois le meme pari : dix jetons de layer 1
# montent et descendent ensemble, les tenir simultanement revient a tripler une
# position unique sans le savoir.
#
# Toutes ces paires n'existent pas dans toutes les devises de cotation. Celles
# qui manquent en USDC sont ecartees au demarrage par
# `BinanceSpotBroker.supports()` : il n'y a rien a maintenir a la main ici, une
# entree inconnue de Binance est simplement ignoree.
# ---------------------------------------------------------------------------
CATALOGUE_CRYPTO: dict[str, str] = {
    # --- References ---
    "BTC": "crypto_major", "ETH": "crypto_major",

    # --- Layer 1 ---
    "SOL": "crypto_l1", "ADA": "crypto_l1", "AVAX": "crypto_l1",
    "DOT": "crypto_l1", "NEAR": "crypto_l1", "ATOM": "crypto_l1",
    "APT": "crypto_l1", "SUI": "crypto_l1", "SEI": "crypto_l1",
    "INJ": "crypto_l1", "TIA": "crypto_l1", "ALGO": "crypto_l1",
    "EGLD": "crypto_l1", "HBAR": "crypto_l1", "ICP": "crypto_l1",
    "FTM": "crypto_l1", "FLOW": "crypto_l1", "XTZ": "crypto_l1",
    "EOS": "crypto_l1", "NEO": "crypto_l1", "IOTA": "crypto_l1",
    "VET": "crypto_l1", "KAVA": "crypto_l1", "MINA": "crypto_l1",
    "ROSE": "crypto_l1", "CELO": "crypto_l1", "QTUM": "crypto_l1",
    "TRX": "crypto_l1", "TON": "crypto_l1", "ZIL": "crypto_l1",

    # --- Layer 2 et mise a l'echelle ---
    "ARB": "crypto_l2", "OP": "crypto_l2", "POL": "crypto_l2",
    "MATIC": "crypto_l2", "IMX": "crypto_l2", "STRK": "crypto_l2",
    "METIS": "crypto_l2", "LRC": "crypto_l2",

    # --- Finance decentralisee ---
    "UNI": "crypto_defi", "AAVE": "crypto_defi", "LINK": "crypto_defi",
    "MKR": "crypto_defi", "CRV": "crypto_defi", "COMP": "crypto_defi",
    "SNX": "crypto_defi", "SUSHI": "crypto_defi", "1INCH": "crypto_defi",
    "LDO": "crypto_defi", "RUNE": "crypto_defi", "DYDX": "crypto_defi",
    "GMX": "crypto_defi", "PENDLE": "crypto_defi",

    # --- Jetons memes : tres volatils, donc utiles, mais fortement correles ---
    "DOGE": "crypto_meme", "SHIB": "crypto_meme", "PEPE": "crypto_meme",
    "FLOKI": "crypto_meme", "BONK": "crypto_meme", "WIF": "crypto_meme",

    # --- Intelligence artificielle, donnees et stockage ---
    "FET": "crypto_ai", "RENDER": "crypto_ai", "GRT": "crypto_ai",
    "AR": "crypto_ai", "FIL": "crypto_ai", "THETA": "crypto_ai",
    "OCEAN": "crypto_ai",

    # --- Jeu video et univers virtuels ---
    "SAND": "crypto_gaming", "MANA": "crypto_gaming", "AXS": "crypto_gaming",
    "GALA": "crypto_gaming", "ENJ": "crypto_gaming", "APE": "crypto_gaming",
    "CHZ": "crypto_gaming",

    # --- Paiement et reserve de valeur ---
    "XRP": "crypto_paiement", "LTC": "crypto_paiement", "BCH": "crypto_paiement",
    "ETC": "crypto_paiement", "XLM": "crypto_paiement", "ZEC": "crypto_paiement",
    "DASH": "crypto_paiement",

    # --- Plateformes d'echange ---
    "BNB": "crypto_echange", "CAKE": "crypto_echange", "CRO": "crypto_echange",

    # --- Or tokenise : suit le metal, pas le marche crypto ---
    "PAXG": "metaux",
}


# Spread typique d'une crypto liquide sur une plateforme correcte, en
# fraction du prix. Un spread ABSOLU n'a aucun sens sur un catalogue
# allant du BTC a 60 000 EUR au PEPE a 0,00001 : la meme valeur y serait
# negligeable d'un cote et interdirait tout trade de l'autre.
SPREAD_CRYPTO_RATIO = 0.0005      # 5 points de base


def spread_estime(instrument: "Instrument", prix: float) -> float:
    """Spread a supposer pour cet instrument a ce prix.

    Les cryptos suivent un modele RELATIF au prix. Les metaux et devises
    gardent leur spread absolu, qui a un sens a leur echelle de cotation
    (l'or se cote en dollars, son spread aussi).

    Sans cela, le backtest melangeait deux mondes : les quatre cryptos
    reglees a la main portaient des spreads absolus herites d'une autre
    epoque — XRP a 0,0008 pour un prix de 0,5 EUR, soit 16 points de base
    la ou le reel en vaut 1 ou 2 — pendant que les quatre-vingt-une autres,
    generees, avaient un spread de zero. Les premieres etaient penalisees,
    les secondes flattees, et aucune n'etait mesuree.
    """
    if instrument.asset_class != "crypto":
        return instrument.typical_spread
    return max(0.0, prix) * SPREAD_CRYPTO_RATIO


def instrument_crypto(actif: str, groupe: str, priorite: float = 0.75) -> Instrument:
    """Construit un instrument crypto generique pour Binance Spot.

    Les valeurs de lot sont volontairement permissives : le broker les
    remplace au demarrage par les vraies contraintes de Binance
    (`apply_market_rules`). Il ne sert a rien de les deviner ici.

    `max_spread` est laisse a l'infini car un plafond absolu n'a aucun sens
    sur un catalogue allant du BTC a 77 000 au PEPE a 0,00001 : le controle
    qui compte est relatif, `max_spread_atr_ratio` compare l'ecart a l'ATR de
    l'instrument, et reste donc valable a toutes les echelles de prix.

    `round_step = 0` desactive les niveaux psychologiques (chiffres ronds),
    qui n'ont de sens que sur des marches ou une echelle de prix fait
    reference, comme les paliers de 10 $ sur l'or.
    """
    return Instrument(
        symbol=f"{actif}USD",
        asset_class="crypto",
        digits=8,
        contract_size=1.0,
        min_lot=1e-8,
        lot_step=1e-8,
        max_lot=1e9,
        round_step=0.0,
        typical_spread=0.0,
        max_spread=math.inf,
        weekend=True,
        priority=priorite,
        correlation_group=groupe,
    )


DEFAULT_UNIVERSE: list[Instrument] = [
    # --- Metaux : coeur du systeme ---
    Instrument("XAUUSD", "metal", 2, 100.0, 0.01, 0.01, 50.0, 10.0, 0.30, 0.60,
               sessions=LONDON_NY, priority=1.25, correlation_group="metals"),
    Instrument("XAGUSD", "metal", 3, 5000.0, 0.01, 0.01, 30.0, 0.50, 0.020, 0.045,
               sessions=LONDON_NY, priority=1.0, correlation_group="metals"),

    # --- Forex majeur : liquide, spreads serres ---
    Instrument("EURUSD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00008, 0.00025,
               sessions=LONDON_NY, priority=1.0, correlation_group="usd_major"),
    Instrument("GBPUSD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00012, 0.00035,
               sessions=LONDON_NY, priority=0.95, correlation_group="usd_major"),
    Instrument("USDJPY", "forex", 3, 100000.0, 0.01, 0.01, 50.0, 1.0, 0.010, 0.030,
               sessions=LONDON_NY, priority=0.95, correlation_group="usd_yen", quote_currency="JPY"),
    Instrument("AUDUSD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00012, 0.00035,
               sessions=LONDON_NY, priority=0.85, correlation_group="commodity_fx"),
    Instrument("USDCAD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00015, 0.00040,
               sessions=LONDON_NY, priority=0.8, correlation_group="commodity_fx", quote_currency="CAD"),

    # --- Crypto : prend le relais la nuit et le week-end (24/7) ---
    Instrument("BTCUSD", "crypto", 2, 1.0, 0.001, 0.001, 20.0, 1000.0, 8.0, 30.0,
               weekend=True, priority=1.05, correlation_group="crypto_major"),
    Instrument("ETHUSD", "crypto", 2, 1.0, 0.01, 0.01, 200.0, 50.0, 0.60, 2.50,
               weekend=True, priority=1.0, correlation_group="crypto_major"),
    Instrument("SOLUSD", "crypto", 3, 1.0, 0.1, 0.1, 2000.0, 5.0, 0.05, 0.25,
               weekend=True, priority=0.9, correlation_group="crypto_l1"),
    Instrument("XRPUSD", "crypto", 4, 1.0, 1.0, 1.0, 100000.0, 0.10, 0.0008, 0.0035,
               weekend=True, priority=0.8, correlation_group="crypto_paiement"),
]

# Le reste du catalogue crypto, genere automatiquement. Les quatre paires
# ci-dessus gardent leurs valeurs reglees a la main ; toutes les autres
# recoivent des valeurs generiques que Binance corrigera au demarrage.
_deja_definis = {i.symbol for i in DEFAULT_UNIVERSE}
DEFAULT_UNIVERSE.extend(
    instrument_crypto(actif, groupe)
    for actif, groupe in CATALOGUE_CRYPTO.items()
    if f"{actif}USD" not in _deja_definis
)


class Universe:
    """Registre des instruments, avec filtrage par disponibilite."""

    def __init__(self, instruments: Optional[list[Instrument]] = None) -> None:
        self._items: dict[str, Instrument] = {}
        for inst in (instruments if instruments is not None else DEFAULT_UNIVERSE):
            self._items[inst.symbol] = inst

    def __iter__(self):
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def get(self, symbol: str) -> Optional[Instrument]:
        return self._items.get(symbol)

    def add(self, inst: Instrument) -> None:
        self._items[inst.symbol] = inst

    def enable_only(self, symbols: list[str]) -> None:
        for sym, inst in self._items.items():
            inst.enabled = sym in symbols

    def tradable(self, ts: Optional[float] = None) -> list[Instrument]:
        """Instruments actifs et dont le marche est ouvert maintenant.

        C'est ce qui permet au robot de tourner 24h/24 : quand le forex et
        l'or ferment, seules les cryptos restent dans la liste.
        """
        return [i for i in self._items.values() if i.enabled and i.is_open(ts)]

    def symbols(self) -> list[str]:
        return list(self._items.keys())

    def classe_dominante(self) -> str:
        """La classe d'actif majoritaire de cet univers.

        Le calibrage en a besoin : un stop typique de crypto vaut deux a
        trois fois un stop typique de forex, et les confondre fait declarer
        « tenables » des unites de temps que le capital ne tient pas.

        L'univers est la seule source qui le sache — la configuration, elle,
        ne nomme que des symboles. Chaine vide si l'univers est vide.
        """
        comptes: dict[str, int] = {}
        for inst in self._items.values():
            classe = (inst.asset_class or "").lower()
            if classe:
                comptes[classe] = comptes.get(classe, 0) + 1
        if not comptes:
            return ""
        return max(comptes.items(), key=lambda kv: kv[1])[0]
