"""Robot de trading autonome multi-actifs (or, forex, crypto).

Modules principaux :
    core          types de base (bougie, position, sens)
    indicators    indicateurs techniques incrementaux
    candles       lecture des bougies japonaises
    chart         analyse graphique (niveaux, figures, divergences, zones)
    news          calendrier economique et filtre d'annonces
    macro         drivers fondamentaux (taux reels, dollar, VIX, COT)
    strategy      moteur de decision : filtres eliminatoires + confluence
    scanner       balayage multi-actifs et classement des opportunites
    risk          money management et echelle de taille adaptative
    objectives    defi hebdomadaire par paliers
    trade_manager gestion dynamique : trailing et extension d'objectif
    brokers       execution (simulateur, MoonX)
    engine        boucle autonome 24h/24
    backtest      rejeu historique
"""

__version__ = "1.0.0"

from .core import Candle, ClosedTrade, Position, Side, Tick

__all__ = ["Candle", "ClosedTrade", "Position", "Side", "Tick", "__version__"]
