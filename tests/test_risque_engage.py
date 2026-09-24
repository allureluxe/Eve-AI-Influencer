"""Le risque engage ne se recalcule jamais — sinon l'esperance ment.

CE QUE CE FICHIER PROTEGE, ET POURQUOI IL EXISTE
================================================

`Position.initial_risk` est RECALCULE a chaque etage de pyramide, et
c'est volontaire : le point mort (0,7 R), le stop suiveur (1,1 R) et le
stop temporel (sous 0,4 R) doivent parler de la position telle qu'elle
est maintenant. Les deux courtiers le font, avec le meme commentaire.

Mais un etage ne s'ajoute QUE si le stop est deja au-dessus du prix
moyen (`pyramide_locked_r_min`). La distance entree <-> stop s'effondre
donc a mesure que la pyramide monte — et le R, qui DIVISE par elle,
explose.

Mesure du 25 septembre 2026 sur la demo 1, quatre etages :

    RUNE   r_multiple = 46,05   pour   +94,99 EUR

Un R de 46 vaudrait ~911 EUR a 19,80 EUR de risque. L'esperance du
compte affichait **+1,641 R** quand le controle par les euros donnait
**+0,317 R** : cinq fois trop.

CE QUE CA AURAIT COUTE. C'est ce chiffre qui decide, a 40 trades, de
faire passer le risque de 0,6 % a 1,0 % (`gold_bot/croissance.py`).
Doubler la mise sur un avantage surestime cinq fois, c'est exactement
ce que CLAUDE.md interdit en toutes lettres.

LA CORRECTION : un champ SEPARE. `risque_eur_engage` accumule ce que
chaque etage met en jeu, au moment ou il le met en jeu, et n'est jamais
recalcule. Le pilotage garde `initial_risk`, la mesure prend celui-ci.
Un seul chiffre ne pouvait pas servir les deux.
"""
from __future__ import annotations

from gold_bot.brokers.paper import PaperBroker, PaperConfig
from gold_bot.core import ClosedTrade, Position, Side, Tick
from gold_bot.universe import instrument_crypto


def _courtier() -> tuple[PaperBroker, object]:
    b = PaperBroker(PaperConfig(start_balance=3300.0, slippage_atr=0.0,
                                commission_pct=0.0))
    b.connect()
    inst = instrument_crypto("RUNE", "crypto_alt")
    b.set_price("RUNEUSD", Tick(0.0, 1.0, 1.0), atr=0.1)
    return b, inst


class TestLeRisqueEngageSAccumule:
    def test_a_l_ouverture_il_vaut_volume_fois_distance_au_stop(self):
        b, inst = _courtier()
        pos = b.open_position(inst, Side.BUY, 100.0, 0.9, 5.0)
        # 100 unites, stop 0,10 sous l'entree -> 10 EUR en jeu.
        assert round(pos.risque_eur_engage, 6) == 10.0

    def test_un_etage_AJOUTE_son_risque_au_lieu_de_le_remplacer(self):
        b, inst = _courtier()
        b.open_position(inst, Side.BUY, 100.0, 0.9, 5.0)      # 10 EUR
        b.set_price("RUNEUSD", Tick(0.0, 1.5, 1.5), atr=0.1)
        # Le stop du 2e etage est POSE AU-DESSUS du prix d'achat du 1er :
        # c'est la regle « a l'abri », et c'est elle qui faisait exploser
        # le R en ecrasant le denominateur.
        pos = b.open_position(inst, Side.BUY, 100.0, 1.4, 6.0)  # +10 EUR
        assert pos.etages == 2
        assert round(pos.risque_eur_engage, 6) == 20.0

    def test_le_denominateur_du_PILOTAGE_s_effondre_bien_lui(self):
        """La preuve que les deux chiffres devaient etre separes.

        Ce test ne denonce pas un defaut : il constate que `initial_risk`
        DOIT s'effondrer pour que le pilotage reste juste, et que c'est
        precisement pour ca qu'il ne peut pas mesurer la performance.
        """
        b, inst = _courtier()
        b.open_position(inst, Side.BUY, 100.0, 0.9, 5.0)
        b.set_price("RUNEUSD", Tick(0.0, 1.5, 1.5), atr=0.1)
        pos = b.open_position(inst, Side.BUY, 100.0, 1.4, 6.0)
        # Entree moyenne 1,25 ; stop remonte a 1,40 -> distance NEGATIVE,
        # donc |0,15|. Le risque engage, lui, vaut toujours 20 EUR.
        assert pos.initial_risk < pos.risque_eur_engage / 100.0
        assert round(pos.risque_eur_engage, 6) == 20.0


class TestLEsperanceHonnete:
    def test_le_R_net_se_calcule_sur_les_euros_reellement_engages(self):
        t = ClosedTrade(
            position_id="x", symbol="RUNEUSD", side=Side.BUY, volume=100.0,
            entry_price=1.0, exit_price=2.0, opened_at=0.0, closed_at=1.0,
            profit=94.99, r_multiple=46.05, reason="stop", risque_eur=19.80)
        # Le journal disait 46,05 R. La verite : 94,99 / 19,80 = 4,80 R.
        assert round(t.r_net, 2) == 4.80

    def test_un_trade_sans_risque_enregistre_ne_compte_PAS_pour_zero(self):
        """Les trades d'avant le 25 septembre n'ont pas ce champ.

        Les compter comme « zero R » tirerait l'esperance vers le bas
        aussi surement que le defaut la tirait vers le haut. On rend
        None, et l'appelant les ecarte.
        """
        t = ClosedTrade(
            position_id="x", symbol="RUNEUSD", side=Side.BUY, volume=1.0,
            entry_price=1.0, exit_price=2.0, opened_at=0.0, closed_at=1.0,
            profit=10.0, r_multiple=1.0, reason="stop")
        assert t.r_net is None

    def test_une_sortie_partielle_n_emporte_qu_une_part_du_risque(self):
        """Sinon la somme des parts depasserait le risque reellement pris."""
        b, inst = _courtier()
        pos = b.open_position(inst, Side.BUY, 100.0, 0.9, 5.0)   # 10 EUR
        b.set_price("RUNEUSD", Tick(0.0, 1.2, 1.2), atr=0.1)
        b.close_position(pos.id, volume=40.0)
        partiel = [t for t in b.closed_trades() if t.partial][-1]
        assert round(partiel.risque_eur, 6) == 4.0
