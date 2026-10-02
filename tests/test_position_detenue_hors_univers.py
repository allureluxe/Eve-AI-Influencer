"""Une crypto detenue doit etre reprise, meme sortie de l'univers du jour.

2 oct. 2026 : DIA, detenue avec son stop chez Bitvavo, n'a pas ete reprise
au redemarrage parce que son volume du jour l'avait sortie de l'univers.
Plus de stop suiveur ni de point mort sur une position ouverte.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.core import Position, Side
from gold_bot.engine import TradingEngine
from gold_bot.universe import ACTIFS_PAR_SYMBOLE, Universe


def _moteur():
    m = object.__new__(TradingEngine)
    m.universe = Universe()
    return m


def _position(sym, volume=445.0):
    return Position(id=sym, symbol=sym, side=Side.BUY, volume=volume,
                    entry_price=0.1482, stop_loss=0.13565, take_profit=12.5,
                    opened_at=1_790_000_000.0)


def test_la_crypto_detenue_est_rajoutee_pour_la_gestion_seulement():
    m = _moteur()
    sym = "ZZDETENUEUSD"
    assert m.universe.get(sym) is None
    m._garder_dans_l_univers(_position(sym))
    inst = m.universe.get(sym)
    assert inst is not None, "la position detenue n'est plus geree"
    assert inst.enabled is False, "une crypto sortie de l'univers ne doit pas etre rachetee"
    assert ACTIFS_PAR_SYMBOLE.get(sym) == "ZZDETENUE", "le courtier ne saurait pas la nommer"


def test_une_position_soldee_n_est_pas_rajoutee():
    m = _moteur()
    m._garder_dans_l_univers(_position("ZZSOLDEEUSD", volume=0.0))
    assert m.universe.get("ZZSOLDEEUSD") is None
