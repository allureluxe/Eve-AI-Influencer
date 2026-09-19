"""Une part du budget de risque est reservee aux renforcements.

Decision de l'operateur le 19 septembre : « tu bloques desormais un
tiers du capital aux pyramides ». Elle repose sur une mesure faite le
soir meme (55 paires, 900 bougies, frais reels) : une nouvelle ligne
perd 5,74 EUR en moyenne, un 3e etage en gagne 33,32. Le robot
depensait tout son budget sur la categorie perdante.
"""
import pytest

from gold_bot.core import Position, Side
from gold_bot.risk import RiskConfig, RiskManager
from gold_bot.universe import Instrument, Universe


def _manager(reserve: float) -> RiskManager:
    cfg = RiskConfig(
        base_risk_pct=0.6, max_risk_pct=1.5, max_total_risk_pct=5.0,
        reserve_pyramide_pct=reserve, pyramide_max=99,
        pyramide_locked_r_min=0.01, pyramide_fraction_risque=1.0,
        max_positions=99, min_seconds_between_trades=0.0,
        ticket_min_eur=0.0,
        # Les prix de ce test sont fictifs : le controle de cout, calcule
        # sur un spread type herite du vrai catalogue, refuserait chaque
        # trade AVANT le plafond de risque et le test ne mesurerait plus
        # la regle qu'il est cense verrouiller.
        max_cost_ratio_pct=1000.0, commission_pct=0.0,
    )
    r = RiskManager(cfg)
    r.sync_account(10_000.0, 10_000.0, "EUR")
    return r


def _position(symbole: str, entree: float, stop: float, volume: float) -> Position:
    p = Position(id=symbole + "-1", symbol=symbole, side=Side.BUY,
                 volume=volume, entry_price=entree, stop_loss=stop,
                 take_profit=entree * 2, opened_at=0.0)
    p.initial_risk = abs(entree - stop)
    return p


@pytest.fixture
def univers():
    return Universe()


# Le symbole garde HORS du portefeuille, pour qu'une entree dessus soit
# vraiment une ligne NOUVELLE. Sans cette precaution le test ouvrait en
# fait un etage de pyramide -- donc il verifiait la regle inverse de
# celle qu'il annonce, et il passait au vert pour la mauvaise raison.
NEUF = "BTCUSD"


def _remplir(univers, lignes: int, manager: RiskManager) -> list[Position]:
    """Ouvre `lignes` positions risquant chacune exactement 0,6 %.

    Un NOMBRE, pas un pourcentage vise : une boucle qui s'arrete « quand
    on depasse » depasse justement, et les seuils du test se retrouvent
    du mauvais cote sans qu'on le voie. Ici `n` lignes engagent n x 0,6 %,
    verifie juste apres.
    """
    positions: list[Position] = []
    symboles = [i.symbol for i in univers
                if i.symbol.endswith("USD") and i.symbol != NEUF]
    capital = manager.account.equity
    for sym in symboles:
        if len(positions) >= lignes:
            break
        inst = univers.get(sym)
        if inst is None:
            continue
        entree, stop = 100.0, 90.0
        volume = (capital * 0.6 / 100.0) / (entree - stop) / inst.contract_size
        positions.append(_position(sym, entree, stop, volume))
    engage = manager.open_risk_pct(positions, univers.get)
    assert abs(engage - lignes * 0.6) < 0.05, (
        f"{lignes} lignes devaient engager {lignes * 0.6:.2f} %, "
        f"elles en engagent {engage:.2f} % : le test ne mesure pas ce "
        "qu'il croit")
    return positions


class TestSansReserveRienNeChange:
    def test_le_plafond_reste_le_budget_total(self, univers):
        m = _manager(reserve=0.0)
        # 7 lignes = 4,2 % engage, plafond 5,0 % : il reste de la place.
        positions = _remplir(univers, 7, m)
        d = m.size_position(univers.get(NEUF), Side.BUY, 100.0, 90.0,
                            120.0, positions, univers.get)
        assert d.allowed, d.reason


class TestAvecReserveLaNouvelleLigneSArreteAvant:
    def test_une_nouvelle_ligne_est_refusee_des_le_plafond_reduit(self, univers):
        """Plafond des nouvelles lignes : 5,0 - 1,67 = 3,33 %.

        6 lignes engagent 3,6 %, donc au-dela. Sans la reserve elles
        passeraient sans probleme (3,6 % sur 5,0 autorises).
        """
        m = _manager(reserve=5.0 / 3.0)
        positions = _remplir(univers, 6, m)
        d = m.size_position(univers.get(NEUF), Side.BUY, 100.0, 90.0,
                            120.0, positions, univers.get)
        assert not d.allowed, (
            "une nouvelle ligne est passee a 3,60 % engage alors que la "
            "reserve devait l'arreter a 3,33 %")
        assert "reserve" in d.reason, d.reason

    def test_un_renforcement_passe_au_meme_moment(self, univers):
        """C'est tout l'interet : la place gardee sert aux etages."""
        m = _manager(reserve=5.0 / 3.0)
        positions = _remplir(univers, 6, m)
        # Le symbole doit DEJA etre en portefeuille : c'est ce qui fait
        # de cette entree un etage et non une ligne nouvelle.
        deja = positions[0].symbol
        d = m.size_position(univers.get(deja), Side.BUY, 100.0, 90.0,
                            120.0, positions, univers.get)
        assert d.allowed, (
            f"le renforcement de {deja} a ete refuse : la reserve ne sert "
            f"a rien ({d.reason})")


class TestLaReserveNePeutPasSeMordreLaQueue:
    def test_une_reserve_enorme_laisse_toujours_passer_la_premiere_ligne(self, univers):
        """Sans pyramide possible, une reserve totale bloquerait tout.

        Si la reserve devorait le budget entier, aucune premiere entree
        ne pourrait s'ouvrir -- donc aucune pyramide ne naitrait, donc la
        reserve ne servirait jamais.
        """
        m = _manager(reserve=99.0)
        d = m.size_position(univers.get(NEUF), Side.BUY, 100.0, 90.0,
                            120.0, [], univers.get)
        assert d.allowed, d.reason
