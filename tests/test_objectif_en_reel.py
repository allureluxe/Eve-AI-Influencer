"""Une position REELLE doit pouvoir se fermer sur son objectif.

LA PANNE QUE CES TESTS VERROUILLENT

Bitvavo n'a pas d'ordre lie « l'un annule l'autre ». Poser a la fois un
stop et un objectif laisserait le second vivant apres que le premier a
vendu, et il revendrait plus tard des actifs qui ne sont plus la. Le robot
ne pose donc QUE le stop sur la plateforme et garde l'objectif pour lui.

Sauf que personne ne comparait le prix a cet objectif. Le simulateur le
fait dans `check_tick` — mais le moteur n'appelait `check_tick` que
`if isinstance(self.broker, PaperBroker)`. En reel, `take_profit` n'etait
qu'un nombre en memoire que rien ne lisait.

Consequence exacte, et c'est ce que l'operateur observait :
UNE POSITION REELLE NE POUVAIT PAS SE FERMER EN BENEFICE SUR SON
OBJECTIF. Elle montait vers la cible, ne se fermait pas, redescendait, et
sortait sur le stop. Les seuls gains encaisses l'ont ete a la main.

POURQUOI AUCUN TEST NE L'A VU

Ils passaient tous par le simulateur — le seul endroit ou la
verification existait. Ces tests-ci s'adressent au gestionnaire de trade,
qui est commun a TOUS les lieux d'execution.
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
    atr = _ATR()

    def __getattr__(self, nom):
        return None


def _position(cote: Side = Side.BUY, tp_r: float = 2.0):
    risque = 180.0
    signe = cote.sign
    pos = Position(id="1", symbol="BTC-EUR", side=cote, volume=0.001,
                   entry_price=ENTREE,
                   stop_loss=ENTREE - signe * risque,
                   take_profit=ENTREE + signe * tp_r * risque,
                   opened_at=0.0)
    pos.initial_risk = risque
    return pos, risque


SPREAD = 1.0


def _actions(pos, prix_de_sortie, cfg=None):
    """`prix_de_sortie` est le prix auquel on sortirait REELLEMENT.

    Un achat se solde au bid, une vente a l'ask. Construire le tick autour
    du prix moyen ferait manquer l'objectif de la moitie du spread — et
    c'est justement le detail que ces tests doivent respecter, parce que
    le robot, lui, le respecte.
    """
    if pos.side is Side.BUY:
        tick = Tick(60.0, prix_de_sortie, prix_de_sortie + SPREAD)
    else:
        tick = Tick(60.0, prix_de_sortie - SPREAD, prix_de_sortie)
    mgr = TradeManager(cfg or BotConfig.load("robot.bitvavo.json").trade)
    return mgr.manage(pos, tick, _Indicateurs(), digits=2, now=60.0)


def _fermetures(actions):
    return [a for a in actions if a.type is ActionType.CLOSE]


# --------------------------------------------------------------------------
# Le coeur de la panne
# --------------------------------------------------------------------------
def test_l_objectif_atteint_ferme_la_position_a_l_achat():
    pos, _ = _position(Side.BUY)
    fermetures = _fermetures(_actions(pos, pos.take_profit))
    assert fermetures, (
        "objectif atteint et aucune fermeture demandee : en reel la position "
        "resterait ouverte et redescendrait toucher le stop")
    assert "objectif" in fermetures[0].reason.lower()


def test_l_objectif_atteint_ferme_la_position_a_la_vente():
    pos, _ = _position(Side.SELL)
    assert _fermetures(_actions(pos, pos.take_profit)), (
        "le sens vendeur doit etre traite comme l'acheteur")


def test_depasser_l_objectif_ferme_aussi():
    # Entre deux cycles de 20 s le prix peut sauter au-dela de la cible.
    # Exiger l'egalite exacte laisserait passer ces cas-la.
    pos, risque = _position(Side.BUY)
    assert _fermetures(_actions(pos, pos.take_profit + 3 * risque))


def test_sous_l_objectif_on_ne_ferme_pas():
    pos, risque = _position(Side.BUY)
    prix = ENTREE + 1.5 * risque          # 1,5 R, objectif a 2 R
    assert not _fermetures(_actions(pos, prix)), (
        "fermer avant l'objectif priverait le trade de sa fin de course")


def test_un_objectif_absent_ne_ferme_rien():
    # Une position sans objectif ne doit pas etre fermee des le premier
    # cycle parce que `0` serait « atteint ».
    pos, risque = _position(Side.BUY)
    pos.take_profit = 0.0
    assert not _fermetures(_actions(pos, ENTREE + risque))


# --------------------------------------------------------------------------
# La verification ne doit pas dependre du lieu d'execution
# --------------------------------------------------------------------------
def test_le_moteur_ne_verifie_l_objectif_que_pour_le_simulateur():
    """Constat du defaut d'origine, garde comme temoin.

    `engine.py` n'appelle `check_tick` que pour PaperBroker. C'est
    legitime — un vrai broker n'a pas besoin qu'on simule ses ordres — mais
    ca voulait dire qu'aucune verification d'objectif ne tournait en reel.
    C'est pour ca que la verification vit desormais dans le gestionnaire de
    trade, commun a tous les lieux d'execution.
    """
    import inspect

    from gold_bot.engine import TradingEngine
    source = inspect.getsource(TradingEngine)
    assert "isinstance(self.broker, PaperBroker)" in source, (
        "si cette ligne disparait, ce test n'a plus de raison d'etre")


def test_aucun_broker_reel_n_implemente_la_verification_de_l_objectif():
    """Le simulateur est le seul a savoir fermer sur objectif tout seul.

    Si un broker reel se met a le faire un jour, il faudra verifier qu'il
    ne double pas la fermeture du gestionnaire de trade.
    """
    from gold_bot.brokers.bitvavo import BitvavoBroker
    assert not hasattr(BitvavoBroker, "check_tick"), (
        "BitvavoBroker verifie maintenant l'objectif : risque de double "
        "fermeture avec le gestionnaire de trade")


def test_l_objectif_passe_avant_les_autres_sorties():
    """A l'objectif, on encaisse — on ne sort pas sur un autre motif."""
    pos, _ = _position(Side.BUY)
    fermetures = _fermetures(_actions(pos, pos.take_profit))
    assert len(fermetures) == 1
    assert "objectif" in fermetures[0].reason.lower()


# --------------------------------------------------------------------------
# Le spread compte
# --------------------------------------------------------------------------
def test_l_objectif_se_juge_au_prix_de_sortie_pas_au_prix_moyen():
    """Un achat se solde au bid, pas au milieu de la fourchette.

    Juger l'objectif sur le prix moyen ferait fermer une demi-fourchette
    trop tot : le trade encaisserait chaque fois un peu moins que
    l'objectif annonce, et l'ecart passerait pour du glissement.
    """
    pos, _ = _position(Side.BUY)
    # Le milieu de la fourchette atteint l'objectif, mais le bid — le prix
    # auquel on vendrait vraiment — reste dessous.
    tick = Tick(60.0, pos.take_profit - 1.0, pos.take_profit + 1.0)
    mgr = TradeManager(BotConfig.load("robot.bitvavo.json").trade)
    actions = mgr.manage(pos, tick, _Indicateurs(), digits=2, now=60.0)
    assert not _fermetures(actions), (
        "ferme alors que le bid n'a pas atteint l'objectif")
