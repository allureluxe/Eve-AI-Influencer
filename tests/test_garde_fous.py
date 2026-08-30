"""Les decisions de l'operateur, verrouillees.

Plusieurs sessions travaillent sur cette branche et sur la meme
configuration, qui engage de l'argent reel. Un fichier de consignes se
contourne sans bruit ; un test rouge, non.

Ces valeurs ont ete choisies apres audit chiffre, le 27 aout. Elles ne
sont pas des valeurs par defaut a optimiser. Si l'un de ces tests echoue,
ce n'est pas le test qu'il faut changer — c'est qu'un reglage a bouge sans
que la decision correspondante ait ete prise.

Le raisonnement complet est dans CLAUDE.md, a la racine du depot.
"""
from __future__ import annotations

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.calibrage import COUT_INCOMPRESSIBLE, calibrer
from gold_bot.promotion import Promotion
from gold_bot.settings import BotConfig

FRAIS_BITVAVO = 0.0025          # taker, par cote, palier de base (< 100 k EUR/mois)
FRAIS_MAKER = 0.0015            # maker, par cote, meme palier

# ATR mesures dans les journaux du 28 aout, en fraction du prix. Le H1 se
# deduit par racine du temps depuis le M15 (0,56 % x 2), valeur coherente
# avec le H4 et le D1 effectivement observes.
ATR_PAR_UNITE = {"M5": 0.0030, "M15": 0.0056, "M30": 0.0080, "H1": 0.0112,
                 "H4": 0.0224, "D1": 0.0546}


def config() -> BotConfig:
    return BotConfig.load("robot.bitvavo.json")


PLAFOND_COUT = 50.0             # % du risque, decision du 30 aout (rejeu)

# Ce que le rejeu du 30 aout a MESURE sur la variante retenue :
# 8 cryptos, 4000 bougies, frais pleins et SPREAD DOUBLE.
REJEU_TRADES = 159
REJEU_REUSSITE_PCT = 56.6
REJEU_ESPERANCE_R = 0.273


class TestPlafondDeCout:
    """Les frais ne peuvent pas manger plus de 50 % du risque.

    ATTENTION : ce plafond n'est plus une deduction, c'est un CONSTAT.

    Les versions precedentes (15 % en H4, 35 % en H1) etaient calculees
    d'avance : on posait un ratio frais/risque acceptable et on en deduisait
    l'unite de temps. Le rejeu du 30 aout a contredit ce raisonnement.
    Mesure sur 8 cryptos, 4000 bougies, frais pleins et SPREAD DOUBLE :

        M30, plafond 50 %   159 trades   56,6 %   +0,273 R   +42,83 EUR
        H4 tendance 3R      134 trades   49,3 %   +0,130 R   +18,94 EUR
        H1 en service        81 trades   43,2 %   +0,073 R    +4,80 EUR
        D1 tendance 2R      172 trades   45,3 %   -0,067 R   -11,04 EUR

    L'unite la plus lente est la PIRE, exactement l'inverse de ce que
    l'arithmetique des frais laissait attendre. Le M30 paie 47 % de son
    risque en frais et gagne quand meme, parce que sa reussite de 56,6 %
    couvre largement le seuil de 49 %.

    CE QUI DISTINGUE CE PLAFOND DE CELUI DU 29 AOUT AU MATIN (70 %, M5) :
    la, la reussite NECESSAIRE valait 122,5 % — une impossibilite
    arithmetique, aucune mesure ne pouvait la sauver. Ici la reussite
    necessaire vaut 49 % et la mesure en donne 56,6. On n'a pas desserre
    une mesure pour laisser passer un trade perdant : on a constate qu'un
    ratio de frais eleve reste payant quand le taux de reussite le porte.

    La contrepartie est une MARGE MINCE : 7,6 points de reussite, contre
    19,8 pour le H4. C'est pourquoi TestMargeDeSecurite existe plus bas.
    """

    @pytest.mark.parametrize("section", ["risk", "strategy", "trade"])
    def test_le_plafond_est_le_meme_partout(self, section):
        valeur = getattr(getattr(config(), section), "max_cost_ratio_pct")
        assert valeur == pytest.approx(PLAFOND_COUT), (
            f"{section}.max_cost_ratio_pct vaut {valeur} au lieu de "
            f"{PLAFOND_COUT} — voir CLAUDE.md avant de modifier")

    def test_le_plafond_correspond_au_stop_reellement_configure(self):
        """Le plafond n'est pas un chiffre libre : il decoule du stop.

        C'est ce lien qui manquait quand le plafond est passe a 70 % : on
        avait desserre la mesure sans toucher au stop, donc sans rien
        changer au probleme qu'elle mesurait.
        """
        cfg = config()
        atr = ATR_PAR_UNITE[cfg.strategy.entry_tf]
        stop = atr * cfg.trade.atr_stop_mult
        cout_reel = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop * 100
        assert cout_reel <= cfg.risk.max_cost_ratio_pct + 1e-9, (
            f"au tarif normal l'unite {cfg.strategy.entry_tf} coute "
            f"{cout_reel:.0f} % du risque, au-dela du plafond "
            f"{cfg.risk.max_cost_ratio_pct:.0f} % : le robot refusera tout")

    def test_l_esperance_reste_atteignable(self):
        """La reussite necessaire doit rester sous ce que le rejeu a montre.

        Au-dela de 100 % on demande l'impossible — c'est arrive le 29 aout
        au matin. Mais le vrai seuil n'est pas 100 % : c'est ce que le
        systeme sait faire, mesure et non suppose.
        """
        cfg = config()
        atr = ATR_PAR_UNITE[cfg.strategy.entry_tf]
        stop = atr * cfg.trade.atr_stop_mult
        frais_en_r = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop
        necessaire = (1 + frais_en_r) / (1 + cfg.trade.tp_r_multiple) * 100
        assert necessaire < REJEU_REUSSITE_PCT, (
            f"il faudrait gagner {necessaire:.1f} % des trades pour une "
            f"esperance nulle, alors que le rejeu n'en a mesure que "
            f"{REJEU_REUSSITE_PCT:.1f} % — la configuration est perdante "
            "d'avance sur sa propre mesure")


class TestMargeDeSecurite:
    """La marge est mince : ce qui la protege ne peut pas etre retire.

    Le M30 gagne 7,6 points de reussite au-dessus de son seuil de
    rentabilite, la ou le H4 en gagne 19,8. Un systeme perd toujours en
    reel une partie de ce qu'il montrait en rejeu — glissement, ordres
    refuses, elargissements de spread sur annonce, qu'aucun rejeu ne
    reproduit. Sur une marge de 7,6 points, cette perte se voit.

    D'ou : les coupe-circuits et le palier de croissance ne sont pas du
    confort ici, ils sont la condition de la decision.
    """

    def test_la_marge_reste_positive(self):
        cfg = config()
        atr = ATR_PAR_UNITE[cfg.strategy.entry_tf]
        stop = atr * cfg.trade.atr_stop_mult
        frais_en_r = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop
        seuil = (1 + frais_en_r) / (1 + cfg.trade.tp_r_multiple) * 100
        marge = REJEU_REUSSITE_PCT - seuil
        assert marge > 5.0, (
            f"marge de seulement {marge:.1f} points entre la reussite mesuree "
            f"({REJEU_REUSSITE_PCT:.1f} %) et le seuil ({seuil:.1f} %) : "
            "une degradation ordinaire en reel suffirait a passer perdant")

    def test_les_coupe_circuits_tiennent(self):
        """Ce qui limite la casse si la marge s'evapore."""
        cfg = config()
        assert 0 < cfg.risk.daily_loss_limit_pct <= 5.0
        assert 0 < cfg.risk.max_drawdown_pct <= 30.0
        assert cfg.risk.max_consecutive_losses <= 5
        assert cfg.risk.pause_after_losses_minutes > 0
        assert cfg.trade.time_stop_minutes > 0

    def test_le_stop_temporel_suit_l_unite_retenue(self):
        """Une valeur pensee pour une autre unite ne protege plus rien."""
        from gold_bot.calibrage import MINUTES_PAR_UNITE
        cfg = config()
        bougies = cfg.trade.time_stop_minutes / MINUTES_PAR_UNITE[cfg.strategy.entry_tf]
        assert 5 <= bougies <= 40, (
            f"le stop temporel laisse {bougies:.0f} bougie(s) de "
            f"{cfg.strategy.entry_tf} : trop peu pour qu'un mouvement se "
            "forme, ou trop pour qu'il protege")

    def test_l_echantillon_du_rejeu_est_interpretable(self):
        """Sous 100 trades, une esperance ne distingue pas un avantage du hasard."""
        incertitude = 2.0 / (REJEU_TRADES ** 0.5)
        assert REJEU_ESPERANCE_R > incertitude, (
            f"esperance {REJEU_ESPERANCE_R:+.3f} R pour une incertitude de "
            f"{incertitude:.3f} sur {REJEU_TRADES} trades : le rejeu ne "
            "prouve pas d'avantage")

    def test_ce_plafond_laisse_passer_l_unite_retenue(self):
        """La consequence voulue, verifiee et non supposee."""
        cfg = config()
        cal = calibrer(equity=51.0, ticket_minimum=5.0,
                       frais_par_cote=FRAIS_BITVAVO,
                       risk_pct_demande=cfg.risk.base_risk_pct,
                       risk_pct_max=cfg.risk.max_risk_pct,
                       plafond_cout_pct=cfg.risk.max_cost_ratio_pct,
                       plafond_positions=cfg.risk.max_positions,
                       part_engageable_pct=cfg.risk.max_capital_engaged_pct)
        assert cal.unites, "aucune unite tenable au tarif normal"

    def test_le_m15_reste_hors_de_portee_du_plafond(self):
        """Le M15 coute 60 % du risque au tarif normal : le plafond l'exclut.

        Correction d'une erreur : le premier calcul annoncait 78 %, tire
        d'un tableau de stops types qui ne correspondait pas a la crypto.
        Avec les ATR reellement mesures — 0,56 % en M15, 2,24 % en H4 —
        les chiffres sont 60 % et 15 %. La conclusion tient pour le M15,
        mais elle ecartait le H4 a tort.
        """
        cfg = config()
        stop_m15 = 0.0056 * cfg.trade.atr_stop_mult
        cout = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop_m15 * 100
        assert cout > cfg.risk.max_cost_ratio_pct, (
            f"le M15 couterait {cout:.0f} % du risque")

    def test_aucun_capital_ne_debloque_le_m15(self):
        """Ce n'est pas un probleme d'argent, c'est une division.

        Le stop minimum ne depend que des frais et du plafond de cout : le
        capital n'entre pas dans ce calcul. Relancer le calibrage de 51 EUR
        a 20 000 EUR le montre.
        """
        cfg = config()
        for equity in (51.0, 500.0, 5_000.0, 20_000.0):
            cal = calibrer(equity=equity, ticket_minimum=5.0,
                           frais_par_cote=FRAIS_BITVAVO,
                           risk_pct_demande=cfg.risk.base_risk_pct,
                           risk_pct_max=cfg.risk.max_risk_pct,
                           plafond_cout_pct=cfg.risk.max_cost_ratio_pct,
                           plafond_positions=cfg.risk.max_positions,
                           part_engageable_pct=cfg.risk.max_capital_engaged_pct)
            assert "M15" not in cal.unites, f"a {equity:.0f} EUR : {cal.unites}"


class TestUniteDeTemps:
    """D1, et le stop temporel qui va avec.

    Le 28 aout, 7 589 evaluations en M15 : 91,7 % ecartees au spread,
    zero trade. Le spread est a peu pres constant en prix tandis que l'ATR
    grandit avec l'unite de temps — un spread ordinaire de 0,22 % vaut
    51 % de l'ATR en M15 et 7 % en D1. Ce n'etait pas un filtre trop
    strict, c'etait le M15 qui ne tient pas sur cette plateforme.
    """

    def test_l_unite_d_entree_est_celle_qui_a_gagne_au_rejeu(self):
        """M30, choisie sur mesure et contre l'intuition.

        Toutes les versions precedentes deduisaient l'unite d'un ratio
        frais/risque juge acceptable : D1 le 27 aout, H4 le 28, H1 le 29.
        Le rejeu du 30 aout — 8 cryptos, 4000 bougies, spread DOUBLE — les
        a toutes departagees, et le classement contredit le raisonnement :

            M30  159 trades  56,6 %  +0,273 R
            H4   134 trades  49,3 %  +0,130 R
            H1    81 trades  43,2 %  +0,073 R
            D1   172 trades  45,3 %  -0,067 R

        L'unite la plus LENTE est la pire, alors que c'est elle qui paie le
        moins de frais (7 % du risque contre 47 % au M30). Payer cher n'est
        pas le probleme ; ne pas avoir d'avantage l'est.
        """
        assert config().strategy.entry_tf == "M30", "voir CLAUDE.md"

    def test_les_unites_plus_rapides_restent_hors_de_portee(self):
        """En dessous du M30, la division redevient impossible.

        Le M30 est le plancher : le M15 couterait 67 % du risque et le M5
        125 %, au-dela de tout taux de reussite atteignable.
        """
        cfg = config()
        for unite in ("M5", "M15"):
            stop = ATR_PAR_UNITE[unite] * cfg.trade.atr_stop_mult
            cout = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop * 100
            assert cout > cfg.risk.max_cost_ratio_pct, (
                f"{unite} couterait {cout:.0f} % du risque, sous le plafond "
                f"{cfg.risk.max_cost_ratio_pct:.0f} % : il redeviendrait "
                "selectionnable")

    def test_le_m5_reste_hors_de_portee_du_systeme(self):
        """Le M5 exige bien plus que ce que ce robot sait faire.

        Le 29 aout au matin il tournait en argent reel avec une reussite
        NECESSAIRE de 122,5 % — arithmetiquement impossible. Le stop plus
        large (1,6 ATR au lieu de 1,10) et l'objectif a 2R ramenent ce
        chiffre a 75 %, donc plus « impossible » au sens strict.

        Mais le meilleur rejeu jamais obtenu donne 56,6 %. Exiger 75 %,
        c'est demander au systeme d'etre d'un tiers meilleur que tout ce
        qu'il a montre : la barriere reste, elle a seulement change de
        nature — de l'arithmetique a la mesure.
        """
        cfg = config()
        stop = ATR_PAR_UNITE["M5"] * cfg.trade.atr_stop_mult
        frais_en_r = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop
        necessaire = (1 + frais_en_r) / (1 + cfg.trade.tp_r_multiple) * 100
        assert necessaire > REJEU_REUSSITE_PCT + 10.0, (
            f"le M5 ne demanderait plus que {necessaire:.0f} % de reussite "
            f"pour {REJEU_REUSSITE_PCT:.1f} % mesures : il redevient "
            "tentant, et c'est exactement le piege du 29 aout")

    def test_le_stop_temporel_est_a_l_echelle_du_d1(self):
        """Le piege : 180 minutes ont du sens en M15, aucun en D1.

        La transposition automatique prend sa reference dans la
        configuration. Changer l'unite sans changer le delai remettrait
        trois heures sur des bougies journalieres — le defaut meme qu'on a
        corrige.
        """
        from gold_bot.calibrage import MINUTES_PAR_UNITE
        cfg = config()
        bougies = cfg.trade.time_stop_minutes / MINUTES_PAR_UNITE[cfg.strategy.entry_tf]
        assert bougies >= 5, (
            f"le stop temporel ne laisse que {bougies:.1f} bougie(s) de "
            f"{cfg.strategy.entry_tf} : un mouvement n'a pas le temps de se former")

    def test_le_spread_ordinaire_passe_sur_l_unite_retenue(self):
        """Ce qui bloquait 91,7 % de l'univers en M15 doit passer."""
        cfg = config()
        atr = ATR_PAR_UNITE[cfg.strategy.entry_tf]
        spread_ordinaire = 0.0022                      # ~0,22 %, ordre de grandeur observe
        assert spread_ordinaire / atr <= cfg.strategy.max_spread_atr_ratio, (
            f"un spread ordinaire vaut {spread_ordinaire/atr:.2f} ATR en "
            f"{cfg.strategy.entry_tf}, au-dela du filtre "
            f"{cfg.strategy.max_spread_atr_ratio} : l'univers serait vide")

    def test_l_unite_n_est_plus_choisie_a_la_volee(self):
        """Une echelle adaptative ramenerait le robot vers le M15."""
        cfg = config()
        assert cfg.strategy.adaptive_timeframe is False
        assert cfg.strategy.timeframe_ladder == [cfg.strategy.entry_tf]


class TestLevierMaitrise:
    """Le levier sert a ouvrir des positions, pas a grossir le risque.

    Decision du 29 aout : l'operateur autorise le levier. La raison est
    mesurable et n'a rien a voir avec l'esperance — celle-ci est
    INVARIANTE au levier, qui multiplie la taille et les frais dans la
    meme proportion. A 70 EUR :

        1x  ->  2 positions   (c'est le CASH qui bloque)
        2x  ->  5 positions   (c'est le budget de risque qui bloque)
        3x  ->  5 positions
        10x ->  5 positions

    Le levier debloque donc les positions que le budget de risque autorise
    deja et que le cash rendait inatteignables. Au-dela du point ou le
    budget de risque redevient la contrainte, augmenter n'ouvre AUCUNE
    position de plus : seul le risque de liquidation monte.
    """

    def test_le_levier_reste_dans_ce_que_bitvavo_autorise(self):
        levier = config().risk.max_leverage
        assert 1.0 <= levier <= 10.0, (
            f"max_leverage vaut {levier} : Bitvavo plafonne a 10x sur ses "
            "actifs eligibles — voir CLAUDE.md")

    @staticmethod
    def _remplir(capital: float):
        """Ouvre des positions jusqu'a epuisement du budget. Renvoie la liste."""
        from gold_bot.core import Position, Side
        from gold_bot.risk import RiskManager
        from gold_bot.universe import Universe, spread_estime

        cfg = config()
        u = Universe()
        inst = u.get("BTCUSD")
        prix = 68_000.0
        stop = prix * ATR_PAR_UNITE[cfg.strategy.entry_tf] * cfg.trade.atr_stop_mult

        rm = RiskManager(cfg.risk)
        rm.sync_account(equity=capital, balance=capital)

        ouvertes, engage, tailles = [], 0.0, []
        for n in range(cfg.risk.max_positions):
            cash = capital * cfg.risk.max_leverage * 0.9 - engage
            d = rm.size_position(
                inst, Side.BUY, prix, prix - stop,
                prix + stop * cfg.trade.tp_r_multiple,
                open_positions=ouvertes, universe_lookup=u.get,
                spread=spread_estime(inst, prix), available_cash=max(0.0, cash))
            if not d.allowed:
                break
            notionnel = d.lots * prix
            engage += notionnel
            tailles.append((notionnel, d.risk_pct))
            ouvertes.append(Position(str(n), "BTCUSD", Side.BUY, d.lots,
                                     prix, prix - stop, 0.0, 0.0))
        return cfg, capital, tailles

    def test_le_cash_se_partage_entre_les_places(self):
        """Au comptant, chaque euro engage sort du solde.

        Servir la premiere position a la taille voulue par le risque lui
        ferait consommer la moitie du budget, et le compte tiendrait deux
        lignes la ou il peut en tenir six. Or six positions de 14,40 EUR
        risquent EXACTEMENT autant que deux de 43 EUR : le risque total
        vaut le notionnel total fois la distance au stop, et le notionnel
        total est le budget dans les deux cas.

        Meme risque, meme esperance — celle-ci est normalisee par le
        risque — mais plus d'instruments, donc moins de variance et plus de
        trades. C'est ce que veut l'operateur, et c'est arithmetiquement
        equivalent en risque.
        """
        cfg, capital, tailles = self._remplir(96.0)
        assert len(tailles) >= 4, (
            f"seulement {len(tailles)} position(s) ouverte(s) sur "
            f"{cfg.risk.max_positions} places : le budget n'est pas partage")

    def test_le_risque_total_ne_depasse_pas_le_budget(self):
        """Partager le cash ne doit pas multiplier le risque."""
        cfg, capital, tailles = self._remplir(96.0)
        risque_total = sum(pct for _, pct in tailles)
        assert risque_total <= cfg.risk.max_total_risk_pct + 1e-6, (
            f"risque total de {risque_total:.2f} % pour un plafond de "
            f"{cfg.risk.max_total_risk_pct:.2f} %")

    def test_aucune_part_sous_le_ticket_minimum(self):
        """Une part trop petite ne produit aucun ordre : la plateforme refuse.

        C'est la seule vraie borne au partage. Mieux vaut alors moins de
        places, plus grandes.
        """
        from gold_bot.universe import Universe
        cfg, capital, tailles = self._remplir(96.0)
        inst = Universe().get("BTCUSD")
        plancher = inst.min_lot * 68_000.0
        for notionnel, _ in tailles:
            assert notionnel >= plancher - 1e-9, (
                f"position de {notionnel:.2f} EUR sous le ticket minimum "
                f"de {plancher:.2f} EUR")

    def test_le_comptant_ne_peut_pas_emprunter(self):
        """Sans marge, engager plus que le capital est impossible."""
        cfg = config()
        if cfg.engine.broker == "bitvavo":
            assert cfg.risk.max_leverage == pytest.approx(1.0), (
                f"broker au comptant avec max_leverage a {cfg.risk.max_leverage} : "
                "le robot dimensionnerait des positions que la plateforme "
                "refusera faute de liquidites")

    def test_le_risque_par_trade_ne_suit_pas_le_levier(self):
        """Le levier ne doit pas se glisser dans le risque par trade.

        C'est la confusion qui coute cher : croire qu'un levier de 3
        autorise un risque de 3 x 0,6 %. Le dimensionnement part du risque
        et remonte vers la taille, jamais l'inverse.
        """
        cfg = config()
        assert cfg.risk.base_risk_pct <= 1.0, (
            f"risque de base a {cfg.risk.base_risk_pct} % : trop eleve pour "
            "un compte a levier")
        assert cfg.risk.max_total_risk_pct <= 4.0, (
            f"risque total a {cfg.risk.max_total_risk_pct} % : le levier a "
            "servi a grossir le risque, pas a ouvrir des places")

    def test_les_coupe_circuits_restent_serres_sous_levier(self):
        """Sous levier, une serie de pertes va plus vite. Les freins doivent tenir."""
        cfg = config()
        assert 0 < cfg.risk.daily_loss_limit_pct <= 5.0
        assert 0 < cfg.risk.max_drawdown_pct <= 30.0
        assert cfg.risk.max_consecutive_losses <= 5
        assert cfg.trade.time_stop_minutes > 0, (
            "sans stop temporel, une position a levier paie des interets "
            "d'emprunt indefiniment")

    def test_le_moteur_impose_le_levier_de_la_configuration_au_broker(self):
        """Le defaut d'environnement du broker de marge est 10x.

        Si le moteur ne le contredisait pas, il suffirait d'une variable
        oubliee pour que le compte parte a dix fois le capital.
        """
        import inspect
        from gold_bot.dual_scalping_engine import DualScalpingEngine
        source = inspect.getsource(DualScalpingEngine._broker_bitvavo_margin)
        assert "BITVAVO_MARGIN_LEVERAGE" in source
        assert "max_leverage" in source, (
            "le plafond de levier du broker ne suit plus la configuration")

    def test_le_moteur_impose_le_levier_de_la_configuration_au_broker(self):
        """Le defaut d'environnement du broker de marge est 10x.

        Si le moteur ne le contredisait pas, il suffirait d'une variable
        oubliee pour que le compte parte a dix fois le capital.
        """
        import inspect
        from gold_bot.dual_scalping_engine import DualScalpingEngine
        source = inspect.getsource(DualScalpingEngine._broker_bitvavo_margin)
        assert "BITVAVO_MARGIN_LEVERAGE" in source
        assert "max_leverage" in source, (
            "le plafond de levier du broker ne suit plus la configuration")


class TestFenetreSansCommission:
    """Le bloc « promotion » ramene AUTOMATIQUEMENT le robot au D1.

    Sans lui, plus rien ne le fait quand la fenetre se ferme.
    """

    def test_le_bloc_est_present(self):
        """Present, meme quand aucune fenetre n'est en cours.

        L'ancienne assertion exigeait `active` : elle confondait « le
        mecanisme d'expiration existe » avec « une promotion tourne en ce
        moment ». Aucune promotion n'est declaree, donc `active` est faux —
        et c'est correct. Ce qui doit rester vrai, c'est que le bloc soit
        la, pret a expirer tout seul le jour ou on en declare une.
        """
        assert isinstance(config().promotion, dict), (
            "bloc promotion absent — voir CLAUDE.md")
        assert "sans_frais_jusqu_au" in config().promotion, (
            "le bloc ne porte plus de date de fin : une fenetre declaree "
            "n'expirerait jamais")

    def test_une_fenetre_active_porte_toujours_sa_fin(self):
        """La vraie invariante : active => bornee."""
        p = Promotion.depuis_config(config().promotion)
        if p.active:
            assert p.fin, "une fenetre sans date de fin n'expire jamais"

    def test_elle_porte_sa_propre_fin(self):
        """Verifie le mecanisme lui-meme, sans dependre du fichier livre."""
        import datetime as dt
        p = Promotion.depuis_config({"active": True,
                                     "sans_frais_jusqu_au": "2026-09-15"})
        fin = dt.date.fromisoformat(p.fin)
        assert p.en_cours(fin) is True
        assert p.en_cours(fin + dt.timedelta(days=1)) is False

    def test_apres_expiration_le_tarif_reel_revient(self):
        """Le lendemain, le robot repaie ses frais — sans intervention."""
        import datetime as dt
        p = Promotion.depuis_config({"active": True,
                                     "sans_frais_jusqu_au": "2026-09-15"})
        fin = dt.date.fromisoformat(p.fin)
        assert p.frais_effectifs(FRAIS_BITVAVO, fin) == pytest.approx(0.0)
        lendemain = fin + dt.timedelta(days=1)
        assert p.frais_effectifs(FRAIS_BITVAVO, lendemain) == pytest.approx(FRAIS_BITVAVO)


class TestLeSimulateurResteDisponible:
    """Un lieu d'execution qui n'engage rien doit toujours etre la.

    « paper » avait ete retire des brokers valides : plus de dry-run, plus
    de rejeu historique, et aucun moteur constructible en test.
    """

    def test_le_simulateur_passe_la_validation(self):
        cfg = BotConfig()
        cfg.engine.broker = "paper"
        assert not [p for p in cfg.validate() if "broker" in p]

    def test_le_mode_hors_ligne_marche_avec_le_simulateur(self):
        cfg = BotConfig()
        cfg.engine.broker = "paper"
        cfg.engine.offline = True
        assert not [p for p in cfg.validate() if "hors ligne" in p]

    def test_le_mode_hors_ligne_reste_refuse_en_reel(self):
        """La garantie d'origine ne doit pas disparaitre avec la correction."""
        cfg = BotConfig()
        cfg.engine.broker = "bitvavo"
        cfg.engine.offline = True
        assert [p for p in cfg.validate() if "hors ligne" in p]


class TestFiltresDEntree:
    """Ce qui decide si un trade merite d'etre pris.

    Desserres, ces deux reglages ont produit 72 trades a 2,8 % de reussite,
    une esperance de -0,406 R et une progression mediane de 0,25 R la ou
    l'objectif etait a 2,20 R : les trades n'allaient nulle part. Quand un
    trade monte a 1,20 R avant de retomber, c'est la protection qui manque ;
    quand il ne depasse jamais 0,25 R, c'est l'entree qui ne vaut rien.
    """

    def test_le_spread_accepte_reste_sous_le_plafond_de_cout(self):
        """La borne n'est pas un chiffre choisi, c'est le plafond de cout.

        Le stop vaut atr_stop_mult ATR, soit 1 R : un spread de X ATR pese
        donc X / atr_stop_mult en R, et ce poids doit tenir sous le plafond.
        A 0,6 le robot acceptait 0,33 R de spread pour 0,15 R permis — c'est
        ce depassement qui a produit 72 trades a 2,8 % de reussite, pas la
        valeur elle-meme.
        """
        cfg = config()
        limite = cfg.risk.max_cost_ratio_pct / 100.0 * cfg.trade.atr_stop_mult
        valeur = cfg.strategy.max_spread_atr_ratio
        assert valeur <= limite + 1e-9, (
            f"max_spread_atr_ratio vaut {valeur}, au-dela de {limite:.2f} "
            "que le plafond de cout autorise — voir CLAUDE.md")

    def test_la_valeur_du_desastre_reste_exclue(self):
        """0,6 ATR de spread doit rester impossible — mais plus par deduction.

        Avec le plafond a 15 % la borne derivee (plafond x atr_stop_mult)
        valait 0,24 et excluait 0,6 toute seule. A 50 % elle vaut 0,80 et
        n'exclut plus rien : c'est le prix de la marge plus mince du M30.

        La protection est donc devenue le reglage EXPLICITE, et c'est lui
        qu'il faut verrouiller. 0,6 ATR de spread avait produit 72 trades a
        2,8 % de reussite le 28 aout ; on reste tres en dessous.
        """
        cfg = config()
        assert cfg.strategy.max_spread_atr_ratio <= 0.35, (
            f"max_spread_atr_ratio vaut {cfg.strategy.max_spread_atr_ratio} : "
            "la borne derivee du plafond de cout ne l'exclut plus, ce reglage "
            "est desormais la seule protection — voir CLAUDE.md")
        assert 0.6 > cfg.strategy.max_spread_atr_ratio

    def test_la_volatilite_minimale_reste_un_plancher(self):
        """Le seuil suit l'unite de temps, il n'est pas absolu.

        A 0,0035 il avait du sens en M15, ou l'ATR vaut 0,56 % du prix : il
        ecartait les instruments six fois moins mobiles que la normale. En
        H4 l'ATR vaut 2,24 %, et ce meme chiffre ne filtrerait plus rien.

        La valeur retenue est celle du rejeu gagnant, pas une preference :
        devier de ce qui a ete mesure reviendrait a remettre en service une
        configuration que personne n'a testee. La vraie protection contre
        les instruments immobiles reste le rapport spread/ATR et le plafond
        de cout, tous deux verifies plus haut.
        """
        cfg = config()
        atr_typique = {"M15": 0.0056, "H1": 0.0112, "H4": 0.0224, "D1": 0.0546}
        atr = atr_typique.get(cfg.strategy.entry_tf, 0.0224)
        # Le plancher doit rester un plancher : au moins dix fois sous
        # l'ATR normal, sinon il n'ecarte plus rien du tout.
        assert 0 < cfg.strategy.min_atr_price_ratio <= atr / 5, (
            f"min_atr_price_ratio vaut {cfg.strategy.min_atr_price_ratio} pour "
            f"un ATR {cfg.strategy.entry_tf} de {atr:.4f}")

    def test_le_spread_autorise_tient_sous_le_plafond_de_cout(self):
        """LA coherence qui manquait : les deux reglages parlent du meme R.

        Le stop vaut atr_stop_mult ATR, soit 1 R. Un spread de M ATR pese
        donc M / atr_stop_mult en R, et ce poids doit rester sous le
        plafond de cout — sinon le filtre laisse passer ce que le plafond
        interdit, et personne ne s'en apercoit.
        """
        cfg = config()
        spread_en_r = cfg.strategy.max_spread_atr_ratio / cfg.trade.atr_stop_mult
        plafond_en_r = cfg.risk.max_cost_ratio_pct / 100.0
        assert spread_en_r <= plafond_en_r, (
            f"{spread_en_r:.2f} R de spread autorise pour {plafond_en_r:.2f} R "
            "de cout permis")

    def test_le_score_minimal_est_une_vraie_barriere(self):
        """Un reglage qui a l'air de proteger et ne fait rien est pire que rien.

        min_score avait ete rendu purement indicatif en mode quorum : le
        seuil etait force a zero, et un achat XRP reel s'est ouvert sur un
        score de 0,24 alors que la configuration exigeait 0,55.
        """
        cfg = config()
        assert cfg.strategy.min_score >= 0.35 - 1e-9, (
            f"min_score vaut {cfg.strategy.min_score} — voir CLAUDE.md")

    def test_le_seuil_de_score_est_applique_en_quorum(self):
        """La valeur ne sert a rien si le mode l'ignore : on verifie l'effet."""
        from gold_bot.strategy import Strategy, StrategyConfig
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig
        cfg = config()
        strat = Strategy(StrategyConfig(mode=cfg.strategy.mode,
                                        min_score=cfg.strategy.min_score),
                         TradeManager(TradeManagerConfig()), macro=None)
        assert strat.config.min_score == pytest.approx(cfg.strategy.min_score)
        # Le seuil doit remonter dans l'evaluation, quel que soit le mode.
        import inspect
        source = inspect.getsource(Strategy._finish_quorum)
        assert "ev.threshold = 0.0" not in source, (
            "le seuil de score est force a zero en quorum : le reglage "
            "min_score redeviendrait decoratif")

    def test_il_reste_plusieurs_barrieres_independantes(self):
        """Une barriere retiree, les autres doivent tenir.

        La confirmation par les bougies a ete rendue facultative le
        28 aout : elle faisait doublon avec le quorum, qui la compte deja
        parmi ses confirmations, et elle mesurait une figure sur une
        bougie journaliere inachevee — un marteau a midi n'en est plus un
        le soir. Ce retrait ne vaut que si les autres barrieres restent.
        """
        cfg = config()
        barrieres = {
            "quorum": cfg.strategy.min_confirmations >= 3,
            "score": cfg.strategy.min_score >= 0.30,
            "ratio_rr": cfg.strategy.min_rr >= 1.5,
            "volatilite": cfg.strategy.min_atr_price_ratio > 0,
            "cout": 0 < cfg.risk.max_cost_ratio_pct <= PLAFOND_COUT,
            "spread": 0 < cfg.strategy.max_spread_atr_ratio < 0.6,
            "perte_journaliere": 0 < cfg.risk.daily_loss_limit_pct <= 5.0,
            "drawdown": 0 < cfg.risk.max_drawdown_pct <= 30.0,
        }
        tombees = [nom for nom, ok in barrieres.items() if not ok]
        assert not tombees, f"barriere(s) desarmee(s) : {tombees} — voir CLAUDE.md"

    def test_la_contradiction_est_refusee_au_demarrage(self):
        """Un reglage incoherent doit etre annonce, pas subi en silence.

        Le controle reste actif — il refuse tout spread au-dela de
        `max_cost_ratio_pct/100 x atr_stop_mult`, soit 0,80 ATR ici. Il est
        simplement devenu permissif avec le plafond a 50 %, d'ou le test
        explicite ci-dessus qui verrouille la vraie valeur.
        """
        cfg = config()
        borne = cfg.risk.max_cost_ratio_pct / 100.0 * cfg.trade.atr_stop_mult
        cfg.strategy.max_spread_atr_ratio = borne + 0.1
        assert [p for p in cfg.validate() if "spread" in p], (
            "la coherence spread / plafond de cout n'est plus verifiee au "
            "demarrage")


class TestLeCoutEstBienCeQuOnCroit:
    """L'arithmetique qui fonde tout le reste, verifiee ici meme."""

    def test_le_cout_incompressible_survit_a_toute_promotion(self):
        """Spread et glissement se paient au marche, pas a la plateforme."""
        assert COUT_INCOMPRESSIBLE > 0

    @pytest.mark.parametrize("unite,stop,attendu", [
        ("M15", 0.0077, 0.78), ("H1", 0.0154, 0.39),
        ("H4", 0.0308, 0.19), ("D1", 0.0600, 0.10)])
    def test_cout_par_unite_de_temps(self, unite, stop, attendu):
        cout = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop
        assert cout == pytest.approx(attendu, abs=0.01)
