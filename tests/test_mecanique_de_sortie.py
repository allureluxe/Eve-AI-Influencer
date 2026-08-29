"""La machine a encaisser fonctionne-t-elle ? Mesure, sans donnees de marche.

« On n'a cloture aucune position en positif » et « toutes mes positions se
ferment en stop » designaient la sortie comme coupable. Ces tests font
tourner le VRAI gestionnaire de trade sur une montee reguliere du prix et
regardent ce qui se declenche.

Le resultat est un NON : la sortie protege correctement. L'objectif est
atteint, et avant lui le stop suit a distance raisonnable. Le probleme
etait ailleurs — a l'entree (72 trades a 2,8 % de reussite, progression
mediane 0,25 R : ces trades n'atteignaient meme pas le break-even a
0,8 R) et dans le stop qui ne bougeait pas sur la plateforme, corrige
depuis.

Ces tests existent pour empecher qu'on « repare » ce qui marche.

CE QU'ILS NE COUVRENT PAS : l'extension d'objectif ne se declenche qu'avec
une dynamique >= extend_min_momentum. Le jeu d'indicateurs utilise ici
n'en produit pas, donc ce chemin-la n'est pas exerce. Seul le rejeu sur
donnees reelles peut le mesurer.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.core import Position, Side, Tick
from gold_bot.settings import BotConfig
from gold_bot.trade_manager import ActionType, TradeManager

ATR = 100.0
ENTREE = 10000.0


class _ATR:
    value = ATR


class _Indicateurs:
    """Le minimum dont `manage` a besoin : un ATR. Aucune dynamique."""
    atr = _ATR()

    def __getattr__(self, nom):
        return None


def _monter(cfg, jusqu_a_r: float):
    """Fait monter le prix par paliers de 0,01 R et rend l'etat final."""
    t = cfg.trade
    risque = t.atr_stop_mult * ATR
    mgr = TradeManager(t)
    pos = Position(id="1", symbol="X", side=Side.BUY, volume=1.0,
                   entry_price=ENTREE, stop_loss=ENTREE - risque,
                   take_profit=ENTREE + t.tp_r_multiple * risque, opened_at=0.0)
    pos.initial_risk = risque
    ind = _Indicateurs()

    atteint = None
    for pas in range(1, int(jusqu_a_r * 100) + 1):
        r = pas * 0.01
        prix = ENTREE + r * risque
        for a in mgr.manage(pos, Tick(pas * 60.0, prix - 0.5, prix + 0.5), ind,
                            digits=2, now=pas * 60.0):
            if a.type is ActionType.MODIFY_STOP:
                pos.stop_loss = a.price
            elif a.type is ActionType.MODIFY_TARGET:
                pos.take_profit = a.price
        if atteint is None and r >= (pos.take_profit - ENTREE) / risque:
            atteint = r
            break
    return pos, risque, atteint


def _cfg():
    return BotConfig.load("robot.bitvavo.json")


# --------------------------------------------------------------------------
def test_l_objectif_est_bien_atteignable():
    """S'il ne l'etait pas, le robot ne pourrait gagner que par accident."""
    cfg = _cfg()
    _, _, atteint = _monter(cfg, 4.0)
    assert atteint is not None, "l'objectif n'est jamais atteint : la sortie est cassee"
    assert atteint <= cfg.trade.tp_r_multiple + 0.01


def test_le_stop_passe_en_positif_avant_l_objectif():
    """Le break-even doit avoir eu lieu : le trade ne peut plus perdre."""
    cfg = _cfg()
    pos, risque, _ = _monter(cfg, 4.0)
    stop_r = (pos.stop_loss - ENTREE) / risque
    assert stop_r > 0, f"stop encore a {stop_r:+.2f} R en arrivant a l'objectif"


def test_le_recul_tolere_reste_raisonnable():
    """Combien le trade rend-il avant de sortir, une fois lance ?

    Trop serre, il sort sur le moindre soubresaut. Trop lache, il rend
    tout le gain acquis. Entre 0,3 et 0,9 R, la protection fait son
    travail sans etouffer le trade.
    """
    cfg = _cfg()
    pos, risque, atteint = _monter(cfg, 4.0)
    stop_r = (pos.stop_loss - ENTREE) / risque
    recul = atteint - stop_r
    assert 0.3 <= recul <= 0.9, f"recul tolere de {recul:.2f} R"


def test_le_trailing_ne_lache_jamais_plus_que_le_risque_initial():
    """Sinon un trade gagnant pourrait revenir en perte."""
    t = _cfg().trade
    lache_en_r = t.trail_atr_mult / t.atr_stop_mult
    assert lache_en_r < 1.0, (
        f"le trailing lache {lache_en_r:.2f} R : un trade a +0,9 R pourrait "
        f"ressortir perdant")


def test_le_trailing_demarre_apres_le_break_even():
    """Dans l'autre ordre, le trailing poserait un stop encore negatif et
    le break-even ne servirait a rien."""
    t = _cfg().trade
    assert t.trail_start_r >= t.breakeven_at_r
