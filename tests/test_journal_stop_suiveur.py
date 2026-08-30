"""Le journal du stop suiveur doit dire la verite.

Observe le 30 aout en production : UNIUSD a repete trente fois

    stop -> 4.32703 (stop suiveur a +1.15R -> +1.15R verrouille)

en quatre minutes. Le stop suiveur, lui, fonctionnait — il est monte de
+0,05R a +1,64R sur la journee. Mais chaque cycle recalcule un chandelier
`max_favorable - k x ATR` dont les deux termes bougent, donc un niveau
superieur d'un milliardieme : arrondi a instrument.digits (1e-8 sur les
cryptos), invisible a l'affichage en 1e-5.

Aucune de ces lignes ne correspondait a un ordre repose chez Bitvavo — le
broker ne deplace le sien qu'au-dela de stop_move_threshold_r. Le journal
annoncait donc trente fois un deplacement qui n'avait pas eu lieu, en
noyant les vrais paliers. C'est le seul defaut de cette affaire, et il
n'est pas dans la mecanique : il est dans ce qu'elle raconte.
"""
from __future__ import annotations

import logging

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.trade_manager import ActionType, TradeAction


def _moteur(tmp_path, monkeypatch):
    for cle in ("BITVAVO_API_KEY", "BITVAVO_API_SECRET",
                "OKX_API_KEY", "GB_STATE_FILE", "GB_TRADES_FILE"):
        monkeypatch.delenv(cle, raising=False)
    monkeypatch.chdir(tmp_path)
    from gold_bot.engine import TradingEngine
    from gold_bot.settings import BotConfig
    cfg = BotConfig.load()
    cfg.engine.broker = "bitvavo"
    cfg.engine.dry_run = True
    return TradingEngine(cfg)


class _BrokerFictif:
    """Accepte tout ; ne repose son ordre que si on l'y autorise.

    C'est le comportement reel de BitvavoBroker : il ne deplace l'ordre en
    carnet qu'au-dela de stop_move_threshold_r, et renvoie True dans les
    deux cas. Un journal qui se fie a ce True annonce donc des
    deplacements qui n'ont pas eu lieu.
    """

    def __init__(self, pose=None, repose=False):
        self.pose = pose
        self.repose = repose

    def stop_depose(self, symbol):
        return self.pose

    def modify_position(self, position_id, stop_loss=None, take_profit=None):
        if self.repose and stop_loss is not None:
            self.pose = stop_loss
        return True


class _SansStopDepose:
    """Un lieu d'execution qui ne depose aucun ordre (le simulateur)."""

    def modify_position(self, position_id, stop_loss=None, take_profit=None):
        return True


class _Position:
    def __init__(self, symbol="UNIUSD", pid="p1"):
        self.symbol = symbol
        self.id = pid


def _action(prix):
    return TradeAction(ActionType.MODIFY_STOP, "p1", prix,
                       reason="stop suiveur a +1.15R -> +1.15R verrouille")


def _lignes_info(moteur, position, prix_successifs):
    from gold_bot import engine as mod
    recu: list[str] = []

    class _Piege(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.INFO:
                recu.append(record.getMessage())

    piege = _Piege()
    niveau = mod.logger.level
    desactive = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    mod.logger.addHandler(piege)
    mod.logger.setLevel(logging.DEBUG)
    try:
        for prix in prix_successifs:
            moteur._apply_action(position, _action(prix), None)
    finally:
        mod.logger.removeHandler(piege)
        mod.logger.setLevel(niveau)
        logging.disable(desactive)
    return recu


class TestLeJournalNAnnoncePasCeQuiNAPasBouge:

    def test_les_increments_invisibles_ne_produisent_qu_une_ligne(self, tmp_path, monkeypatch):
        """La regression du 30 aout, verrouillee.

        Trente cycles, trente hausses reelles de 1e-8, un seul et meme
        niveau a l'affichage : une seule ligne doit sortir.
        """
        moteur = _moteur(tmp_path, monkeypatch)
        moteur.broker = _BrokerFictif(pose=4.30000)
        prix = [4.32703 + i * 1e-8 for i in range(30)]
        lignes = _lignes_info(moteur, _Position(), prix)
        assert len(lignes) == 1, (
            f"{len(lignes)} lignes pour un stop qui ne bouge pas a "
            f"l'affichage : le journal reproduit le bruit du chandelier")

    def test_un_vrai_palier_est_annonce(self, tmp_path, monkeypatch):
        """Filtrer le bruit ne doit pas faire taire les paliers.

        C'est l'envers du test precedent et il compte autant : un journal
        muet ne vaut pas mieux qu'un journal noye.
        """
        moteur = _moteur(tmp_path, monkeypatch)
        moteur.broker = _BrokerFictif(pose=4.30000)
        lignes = _lignes_info(moteur, _Position(), [4.32703, 4.32703, 4.43406])
        assert len(lignes) == 2, f"paliers manques : {lignes}"
        assert "4.43406" in lignes[-1]

    def test_un_ordre_repose_est_toujours_annonce(self, tmp_path, monkeypatch):
        """Ce qui atteint la plateforme se voit, meme au meme niveau affiche.

        Le stop interne et le stop en carnet divergent en permanence — le
        broker ne repose qu'au-dela de stop_move_threshold_r. Le moment ou
        la protection REELLE rattrape son retard est precisement celui
        qu'il ne faut pas manquer, et il peut tomber sur un niveau deja
        annonce.
        """
        moteur = _moteur(tmp_path, monkeypatch)
        broker = _BrokerFictif(pose=4.30000)
        moteur.broker = broker

        lignes = _lignes_info(moteur, _Position(), [4.32703, 4.32703])
        assert len(lignes) == 1

        broker.repose = True             # la plateforme accepte enfin le niveau
        lignes += _lignes_info(moteur, _Position(), [4.32703])
        assert len(lignes) == 2, "un ordre reellement repose n'a pas ete annonce"
        assert "ordre repose" in lignes[-1]

    def test_la_ligne_distingue_l_interne_de_la_plateforme(self, tmp_path, monkeypatch):
        """Sans cette mention, « stop -> X » laisse croire que X est en carnet."""
        moteur = _moteur(tmp_path, monkeypatch)
        moteur.broker = _BrokerFictif(pose=4.30000)
        lignes = _lignes_info(moteur, _Position(), [4.32703])
        assert "interne, ordre inchange" in lignes[0], lignes

    def test_le_simulateur_reste_lisible(self, tmp_path, monkeypatch):
        """Un broker sans ordre depose n'a rien a mentionner, et ne ment pas."""
        moteur = _moteur(tmp_path, monkeypatch)
        moteur.broker = _SansStopDepose()
        lignes = _lignes_info(moteur, _Position(),
                              [4.32703 + i * 1e-8 for i in range(10)] + [4.43406])
        assert len(lignes) == 2, lignes
        assert "ordre" not in lignes[0]


class TestLeStopDeposeEstLisible:
    def test_le_broker_bitvavo_expose_son_niveau_en_carnet(self):
        """Position.stop_loss ne repond pas a cette question.

        Le gestionnaire y ecrit son niveau AVANT que le broker soit appele.
        Distinguer les deux est ce qui permet au journal de dire laquelle
        des deux valeurs il annonce.
        """
        from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig
        broker = BitvavoBroker(BitvavoConfig(dry_run=True))
        assert broker.stop_depose("UNIUSD") is None
        broker._stop_pose["UNIUSD"] = 4.32
        assert broker.stop_depose("UNIUSD") == 4.32
