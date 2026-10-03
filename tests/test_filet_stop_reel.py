"""Une position reelle sous son stop doit etre vendue (3 oct. 2026).

NOM est restee ouverte sous son stop : l'ordre stopLossLimit deposé chez
Bitvavo s'etait declenche sans trouver preneur a sa limite, et le moteur
reel ne verifiait jamais le stop lui-meme. Deux corrections, verrouillees
ici : le stop deposé est AU MARCHE, et un filet logiciel vend si le prix
passe au stop.
"""
import inspect

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.core import Position, Side, Tick
from gold_bot.engine import TradingEngine, prix_sous_le_stop


def _pos(stop=0.0021311):
    return Position(id="NOMUSD", symbol="NOMUSD", side=Side.BUY, volume=14709.0,
                    entry_price=0.0025129, stop_loss=stop, take_profit=0.0,
                    opened_at=0.0)


def test_sous_le_stop_on_vend():
    assert prix_sous_le_stop(_pos(), Tick(0.0, 0.0020372, 0.0020452))


def test_au_dessus_on_garde():
    assert not prix_sous_le_stop(_pos(), Tick(0.0, 0.0022, 0.00221))


def test_sans_stop_rien():
    assert not prix_sous_le_stop(_pos(stop=0.0), Tick(0.0, 0.001, 0.0011))


def test_le_filet_est_dans_le_moteur_reel():
    src = inspect.getsource(TradingEngine)
    assert "prix_sous_le_stop(pos, tick)" in src
    assert "filet : prix sous le stop" in src


def test_le_stop_depose_est_au_marche():
    from gold_bot.brokers import bitvavo
    src = inspect.getsource(bitvavo.BitvavoBroker._poser_stop)
    assert '"orderType": "stopLoss"' in src
    assert '"price":' not in src, "un stopLoss au marche ne porte pas de prix"
