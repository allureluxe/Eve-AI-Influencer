"""Renforcer une montee : ouvrir un 2e, puis un 3e etage sur le meme actif.

Demande de l'operateur, mot pour mot : « grosse montee, plus
d'investissement — si le bot voit que ca continue de monter il ouvre une
2e, si ca continue encore une 3e, et elles se fermeront toutes au stop
suiveur en benefice ».

Trois verrous l'interdisaient, et il fallait les lever tous les trois :

  1. `check_exposure` refusait toute seconde position sur un symbole ;
  2. le scan retirait les symboles detenus AVANT evaluation (`exclude`) ;
  3. le rejeu ne tenait qu'une position a la fois — donc meme arme, le
     banc d'essai aurait rendu un resultat identique au temoin et on en
     aurait conclu que le renforcement ne sert a rien.

Le troisieme est le plus vicieux : il ne casse rien, il ment.
"""
from __future__ import annotations

import time

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.core import Position, Side
from gold_bot.risk import RiskConfig, RiskManager
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe


def _position(symbole="SOLUSD", entree=100.0, stop=98.0, pid="p1") -> Position:
    return Position(id=pid, symbol=symbole, side=Side.BUY, volume=1.0,
                    entry_price=entree, stop_loss=stop, take_profit=104.0,
                    opened_at=time.time(), initial_risk=2.0)


def _gestionnaire(**reglages) -> RiskManager:
    cfg = RiskConfig(**reglages)
    rm = RiskManager(cfg)
    rm.sync_account(1000.0, 1000.0, "EUR")
    return rm


class TestLaPyramideResteFermeeParDefaut:
    """Le renforcement ne s'arme pas tout seul : le rejeu tranche avant.

    Il a tranche le 6 septembre 2026, et POUR une fois en faveur du
    renforcement — c'est le seul reglage teste cette session-la qui passe
    le walk-forward. Le defaut du CODE reste desarme ; c'est la
    configuration livree qui l'arme, sur mesure et pas sur principe.
    """

    def _desarmement_d_urgence_du_6_septembre(self):
        """DESARME EN URGENCE le 6 septembre 2026, 21h50 UTC.

        Arme a 21h47, il a ouvert DEUX etages sur LINKUSD en 39 secondes,
        a **0,013 ATR d'ecart** alors que l'espacement exige 0,5 ATR. Un
        troisieme a suivi, refuse seulement par manque de cash.

        Cause : `peut_renforcer(sur_le_meme, side, prix=0.0, atr=0.0)` est
        appele SANS prix ni ATR aux deux endroits (risk.py:461 et
        dual_scalping_engine.py:123), et le controle s'ecrit

            if cfg.pyramide_espacement_atr > 0 and prix > 0 and atr > 0:

        donc il ne s'execute jamais. Le reglage existait, s'affichait dans
        la config, et ne servait a rien — la faute exacte que le CLAUDE.md
        documente deja trois fois. Combine a `pyramide_locked_r_min` a
        -1,0, plus RIEN ne gardait la porte.

        A corriger avant de rearmer : passer prix et ATR jusqu'a
        `peut_renforcer`, et faire echouer FERME quand ils manquent
        (refuser le renforcement) plutot que de laisser passer.

        Reste aussi a trancher : au comptant Bitvavo ne connait qu'un
        AVOIR par actif, pas deux lignes. Le robot tient deux Position en
        memoire sur un seul solde LINK — il faut verifier ce que devient
        le stop de chaque etage avant de rejouer avec.

        La mesure qui justifiait l'armement reste valable, elle :
        3 unites font +35,8 % hors echantillon (Sharpe +0,53) contre
        -10,9 % sans pyramidage. C'est le CHEMIN qui est casse, pas la
        destination.
        """
        assert BotConfig.load("robot.bitvavo.json").risk.pyramide_max == 0

    def test_le_reglage_livre_est_illimite(self):
        """ILLIMITE, arme le 9 septembre 2026 sur decision de l'operateur.

        Sa lecture du mecanisme etait meilleure que ma conclusion, et les
        donnees lui donnent raison. Quand une pyramide se ferme, hors
        echantillon, frais doubles :

            unites    trades  gagnants   resultat    moyen
            1            122      15 %    -635 E    -5,21
            2-3          117      10 %    -719 E    -6,15
            4-5           57      19 %     -63 E    -1,10
            6-9           36      47 %   +1270 E   +35,27
            10 et +        7     100 %    +754 E  +107,75

        Les pyramides de dix unites et plus sont gagnantes SEPT FOIS SUR
        SEPT — exactement ce qu'il decrivait : plus ca monte, plus il
        investit, et tout sort ensemble en profit sur le stop commun.

        Le budget de risque ne les bride pas : une position gagnante
        libere son budget quand son stop passe au-dessus de l'entree.
        Les pyramides atteignent 11-12 unites a 3,5 %, et RELEVER le
        budget degrade (+58,6 % a 3,5 % contre +37,8 % a 6 %).

        CE QUE CA COUTE, et l'operateur l'a accepte : hors echantillon
        +58,6 % contre +27,9 % a trois unites, mais un recul de 47,6 %
        contre 33,6 %. Et en apprentissage l'illimite fait -66,3 % avec
        83,9 % de recul. Les deux periodes se contredisent : une partie
        du resultat est du regime, pas de la strategie.
        """
        assert BotConfig.load("robot.bitvavo.json").risk.pyramide_max >= 99

    def _ancienne_valeur_trois_unites(self):
        """3 unites, pas 4 ni l'illimite : c'est ce que la mesure designe.

        Hors echantillon, frais doubles, 70 paires, 2,2 ans :

            sans pyramidage   -10,9 %   Sharpe -0,17   recul 26,9 %
            2 unites           -0,3 %   Sharpe +0,14   recul 30,8 %
            3 unites          +35,8 %   Sharpe +0,53   recul 35,4 %   <- arme
            4 unites          +23,9 %   Sharpe +0,42   recul 41,3 %
            6 unites          -40,8 %   Sharpe +0,05   recul 76,6 %
            ILLIMITE          -84,4 %   Sharpe -0,57   recul 95,3 %

        Le manuel Turtle dit 4 unites. Sur CES marches et CES frais, la
        mesure dit 3. On suit la mesure. Et l'illimite — demande a un
        moment — est la pire des six : le monter n'est pas « debrider »,
        c'est reproduire un resultat mesure a -84 %.
        """
        assert BotConfig.load("robot.bitvavo.json").risk.pyramide_max >= 99

    def test_le_relevement_turtle_accompagne_le_desserrage(self):
        """`pyramide_locked_r_min` desserre : son remplacant doit etre arme.

        Les deux protegent la meme chose par deux chemins opposes. Le
        notre attend que l'etage precedent ne puisse plus perdre AVANT
        d'ajouter ; la Turtle ajoute tous les 0,5 N mais remonte le stop
        de TOUTE la pyramide sous la derniere unite. Desserrer le premier
        sans armer le second laisse trois fois le risque sur une crypto
        sans filet.
        """
        cfg = BotConfig.load("robot.bitvavo.json")
        if cfg.risk.pyramide_locked_r_min < 0.05:
            assert cfg.trade.pyramide_relevement_turtle, (
                "pyramide_locked_r_min est desserre sans que le relevement "
                "Turtle soit arme : le pyramidage n'a plus aucun filet")

    def test_le_defaut_du_code_est_desarme(self):
        assert RiskConfig().pyramide_max == 0

    def test_desarme_une_seconde_position_est_refusee(self):
        rm = _gestionnaire()
        inst = Universe().get("SOLUSD")
        ok, why = rm.check_exposure(inst, Side.BUY, [_position()], Universe().get)
        assert not ok
        assert "deja ouverte" in why


class TestLaPyramideNeSOuvreQueSurUnGainAcquis:
    """La regle qui rend l'empilement tenable, et la seule qui compte.

    Un etage ne s'ajoute que si les precedents ne peuvent PLUS perdre —
    stop au-dessus de l'entree. Sans elle, trois entrees sur la meme
    crypto triplent le risque, et un retournement brutal — ce qui arrive
    precisement apres une grosse montee — les prend toutes les trois.
    """

    def test_un_etage_dont_le_stop_est_sous_l_entree_bloque_tout(self):
        rm = _gestionnaire(pyramide_max=2)
        inst = Universe().get("SOLUSD")
        # Stop a 98 pour une entree a 100 : la position peut encore perdre.
        ok, why = rm.check_exposure(inst, Side.BUY, [_position(stop=98.0)],
                                    Universe().get)
        assert not ok, "renforcement accepte sur une position qui peut encore perdre"
        assert "verrouille" in why

    def test_un_etage_au_dela_du_seuil_ouvre_la_porte(self):
        rm = _gestionnaire(pyramide_max=2)
        inst = Universe().get("SOLUSD")
        # Stop a 100.5 pour une entree a 100 : +0.25R deja verrouille.
        ok, why = rm.check_exposure(inst, Side.BUY, [_position(stop=100.5)],
                                    Universe().get)
        assert ok, why

    def test_le_nombre_d_etages_est_borne(self):
        rm = _gestionnaire(pyramide_max=1)
        inst = Universe().get("SOLUSD")
        etages = [_position(stop=100.5, pid="p1"), _position(stop=100.5, pid="p2")]
        ok, why = rm.check_exposure(inst, Side.BUY, etages, Universe().get)
        assert not ok
        assert "maximum 1" in why

    def test_un_etage_a_contre_sens_est_refuse(self):
        """Ce serait une couverture : deux positions qui s'annulent en
        payant deux fois les frais."""
        rm = _gestionnaire(pyramide_max=2)
        inst = Universe().get("SOLUSD")
        ok, why = rm.check_exposure(inst, Side.SELL, [_position(stop=100.5)],
                                    Universe().get)
        assert not ok
        assert "sens oppose" in why


class TestChaqueEtageRisqueMoinsQueLePrecedent:
    """La concentration, elle, n'est pas bornee par la regle du stop.

    A 96 EUR de capital, deux etages pleins mettent tout le compte sur une
    seule crypto. La decroissance geometrique garde le sommet raisonnable.
    """

    def test_le_second_etage_risque_moins(self):
        rm = _gestionnaire(pyramide_max=2, pyramide_fraction_risque=0.6,
                           max_cost_ratio_pct=100.0)
        inst = Universe().get("SOLUSD")
        seul = rm.size_position(inst, Side.BUY, 100.0, 98.0, 104.0,
                                [], Universe().get)
        renfort = rm.size_position(inst, Side.BUY, 100.0, 98.0, 104.0,
                                   [_position(stop=100.5)], Universe().get)
        assert seul.allowed and renfort.allowed, (seul.reason, renfort.reason)
        assert renfort.risk_pct < seul.risk_pct, (
            f"etage 2 risque {renfort.risk_pct:.3f}% contre {seul.risk_pct:.3f}% "
            "pour le premier : la pyramide concentre le compte")
        assert abs(renfort.risk_pct / seul.risk_pct - 0.6) < 0.05


class TestLeRejeuSaitEmpiler:
    """Le verrou qui ne casse rien mais qui ment.

    `if broker.positions(): continue` tenait UNE position a la fois. Armer
    la pyramide sans lever cette ligne aurait rendu un resultat identique
    au temoin — et on en aurait conclu que le renforcement ne sert a rien
    alors qu'il n'avait jamais eu lieu.
    """

    def test_hors_pyramide_le_rejeu_ne_tient_qu_une_position(self):
        """Les mesures du 30 aout doivent rester comparables."""
        import inspect
        from gold_bot.backtest import Backtester
        src = inspect.getsource(Backtester.run)
        assert "pyramide_max <= 0" in src, (
            "le rejeu ne distingue plus le mode simple du mode pyramide")

    def test_le_rejeu_ouvre_vraiment_plusieurs_etages(self):
        """Le test qui aurait attrape le mensonge.

        Sur une tendance franche, seuils desarmes, pyramide armee : le
        rejeu doit produire des trades qui se CHEVAUCHENT dans le temps.
        Sans chevauchement, aucun etage ne s'est jamais ajoute.
        """
        from gold_bot.backtest import Backtester
        from test_backtest_pipeline import _RegistreConstant, _serie_en_tendance

        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.strategy.min_score = 0.0
        cfg.strategy.min_confirmations = 1
        cfg.strategy.min_adx = 0.0
        cfg.strategy.min_headroom_atr = 0.0
        cfg.strategy.min_atr_percentile = 0.0
        cfg.strategy.max_atr_percentile = 1.0
        cfg.strategy.min_atr_price_ratio = 0.0
        cfg.risk.pyramide_max = 2
        cfg.risk.min_seconds_between_trades = 0.0
        cfg.risk.max_positions = 6

        res = Backtester(cfg, registry=_RegistreConstant(_serie_en_tendance())).run(
            "BTCUSD", bars=700, start_balance=1000.0)
        assert res.trades, (
            "aucun trade : le test ne mesure rien. Motifs : "
            f"{sorted(res.rejections.items(), key=lambda kv: -kv[1])[:5]}")

        chevauchements = sum(
            1 for i, a in enumerate(res.trades) for b in res.trades[i + 1:]
            if b.opened_at < a.closed_at and a.opened_at < b.closed_at)
        assert chevauchements > 0, (
            f"{len(res.trades)} trades, aucun ne chevauche un autre : le "
            "rejeu tient toujours une seule position, la pyramide n'a "
            "jamais ete mesuree")


class TestLeStopCommunDeLaPyramide:
    """Les etages sortent ENSEMBLE, pas un par un par le haut.

    Le defaut corrige ici : chaque etage suivait son propre plus-haut avec
    la meme distance ATR. L'etage 2, entre plus haut, se retrouvait avec un
    stop AU-DESSUS de celui de l'etage 1 — au moindre repli c'est le
    renfort qui sautait, en payant l'aller-retour complet, pendant que la
    base survivait. On perdait exactement l'etage qu'on venait d'ajouter
    parce que ca montait.
    """

    @staticmethod
    def _gestionnaire(commun: bool):
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig
        return TradeManager(TradeManagerConfig(pyramide_stop_commun=commun))

    @staticmethod
    def _pyramide():
        """Base a 100 (stop deja monte a 106), renfort a 110 (stop 108).

        Le renfort a le stop le plus haut : c'est lui qui saute en premier
        au moindre repli. Le point mort collectif vaut 105, il ne contraint
        donc pas ici — on mesure bien l'effet du niveau partage seul.
        """
        base = _position(entree=100.0, stop=106.0, pid="base")
        haut = _position(entree=110.0, stop=108.0, pid="haut")
        return base, haut

    def test_l_etage_haut_ne_se_resserre_pas_devant_les_autres(self):
        base, haut = self._pyramide()
        partage = self._gestionnaire(True).stop_partage(haut, [base, haut])
        assert partage == 106.0, (
            "le niveau partage doit valoir le stop le plus lache de la "
            f"pyramide (106.0), pas {partage}")
        assert partage < haut.stop_loss, (
            "l'etage haut garde un stop plus serre que les autres : il "
            "sortira encore seul au premier repli")

    def test_le_niveau_partage_ne_passe_pas_sous_le_point_mort_collectif(self):
        """Une pyramide ne doit jamais sortir collectivement perdante."""
        tm = self._gestionnaire(True)
        # Base a 100 avec un stop tres bas : le point mort collectif (105)
        # devient contraignant.
        base = _position(entree=100.0, stop=90.0, pid="base")
        haut = _position(entree=110.0, stop=108.0, pid="haut")
        partage = tm.stop_partage(haut, [base, haut])
        mort = tm.point_mort_collectif([base, haut])
        assert mort == 105.0
        assert partage == 105.0, (
            f"niveau partage {partage} sous le point mort collectif {mort} : "
            "la pyramide sortirait dans le rouge")

    def test_une_position_seule_n_est_pas_une_pyramide(self):
        base = _position(pid="base")
        assert self._gestionnaire(True).stop_partage(base, [base]) is None

    def test_desarme_rien_ne_change(self):
        """Sans le reglage, le comportement d'origine est intact."""
        from gold_bot.trade_manager import TradeManagerConfig
        assert TradeManagerConfig().pyramide_stop_commun is False


class TestLeRelevementTurtleRemonteToutePyramide:
    """Le filet qui remplace « n'ajouter que sur un etage a l'abri ».

    La Turtle renforce tot — tous les 0,5 N, bien avant que l'etage
    precedent ne soit a l'abri. Ce qui rend ca tenable n'est pas une
    condition d'entree mais une consequence : chaque unite ajoutee
    remonte le stop de TOUTE la pyramide sous elle. Sans ce relevement,
    desserrer `pyramide_locked_r_min` empile trois risques pleins sur une
    seule crypto — exactement le scenario que le reglage d'origine
    interdisait.
    """

    @staticmethod
    def _tm(arme: bool = True, stop_mult: float = 1.6):
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig
        return TradeManager(TradeManagerConfig(
            pyramide_relevement_turtle=arme, atr_stop_mult=stop_mult))

    def test_le_plancher_suit_la_derniere_unite(self):
        """Base a 100, renfort a 110, ATR 4 : plancher a 110 - 1,6 x 4."""
        base = _position(entree=100.0, stop=96.8, pid="base")
        time.sleep(0.001)                      # l'ordre d'ouverture compte
        haut = _position(entree=110.0, stop=96.8, pid="haut")
        plancher = self._tm().plancher_turtle(haut, [base, haut], atr=4.0)
        assert plancher == 103.6, (
            f"plancher {plancher} au lieu de 110 - 1,6 x 4 = 103.6 : le "
            "relevement ne suit pas la derniere unite posee")
        assert plancher > base.entry_price, (
            "le plancher doit passer AU-DESSUS de l'entree de la base : "
            "c'est ce qui borne le risque de la pyramide entiere")

    def test_une_position_seule_n_est_pas_relevee(self):
        base = _position(pid="base")
        assert self._tm().plancher_turtle(base, [base], atr=4.0) is None

    def test_sans_atr_aucun_relevement(self):
        """Un ATR nul ne doit pas produire un plancher egal a l'entree."""
        base = _position(entree=100.0, pid="base")
        haut = _position(entree=110.0, pid="haut")
        assert self._tm().plancher_turtle(haut, [base, haut], atr=0.0) is None

    def test_un_autre_symbole_n_entre_pas_dans_la_famille(self):
        """Deux cryptos ne forment pas une pyramide, meme ouvertes ensemble."""
        sol = _position(symbole="SOLUSD", entree=100.0, pid="sol")
        ada = _position(symbole="ADAUSD", entree=110.0, pid="ada")
        assert self._tm().plancher_turtle(sol, [sol, ada], atr=4.0) is None

    def test_desarme_le_defaut_du_code_ne_releve_rien(self):
        from gold_bot.trade_manager import TradeManagerConfig
        assert TradeManagerConfig().pyramide_relevement_turtle is False


class TestLEspacementSExecuteVRAIMENT:
    """Le bug du 6 septembre 2026 : un garde-fou qui ne s'executait jamais.

    `peut_renforcer` recevait `prix=0.0, atr=0.0` de ses deux appelants du
    moteur reel, et son controle s'ecrivait

        if cfg.pyramide_espacement_atr > 0 and prix > 0 and atr > 0:

    donc il ne s'executait JAMAIS. Deux etages sur LINKUSD en 39 secondes,
    a 0,013 ATR d'ecart pour 0,5 exige. Le rejeu, lui, passait prix et ATR
    — il mesurait une regle que le robot n'appliquait pas.
    """

    def test_sans_prix_ni_atr_le_renforcement_est_REFUSE(self):
        """Fail-closed. C'est toute la correction.

        Un garde-fou incapable de verifier doit refuser. L'ancien code
        laissait passer, ce qui transformait une regle en decoration.
        """
        rm = _gestionnaire(pyramide_max=2, pyramide_espacement_atr=0.5,
                           pyramide_locked_r_min=-1.0)
        ok, why = rm.peut_renforcer([_position(entree=100.0)], Side.BUY)
        assert not ok, (
            "renforcement accepte sans prix ni ATR : le controle d'espacement "
            "ne s'execute pas, exactement comme le 6 septembre")
        assert "invérifiable" in why or "inverifiable" in why

    def test_trop_proche_refuse(self):
        """Le cas LINKUSD : 0,013 ATR d'ecart pour 0,5 exige."""
        rm = _gestionnaire(pyramide_max=2, pyramide_espacement_atr=0.5,
                           pyramide_locked_r_min=-1.0)
        ok, why = rm.peut_renforcer([_position(entree=11.1951)], Side.BUY,
                                    prix=11.2014, atr=0.4703)
        assert not ok, "un etage a 0,013 ATR du precedent a ete accepte"
        assert "trop proche" in why

    def test_assez_loin_accepte(self):
        rm = _gestionnaire(pyramide_max=2, pyramide_espacement_atr=0.5,
                           pyramide_locked_r_min=-1.0)
        ok, why = rm.peut_renforcer([_position(entree=11.1951)], Side.BUY,
                                    prix=11.1951 + 0.6 * 0.4703, atr=0.4703)
        assert ok, why

    def test_le_prefiltre_ne_verifie_pas_l_espacement(self):
        """La phase de selection tourne AVANT le chargement des donnees.

        Elle n'a ni prix ni ATR, et doit le dire explicitement — sinon
        le fail-closed la bloquerait et le symbole ne serait plus jamais
        regarde.
        """
        rm = _gestionnaire(pyramide_max=2, pyramide_espacement_atr=0.5,
                           pyramide_locked_r_min=-1.0)
        ok, why = rm.peut_renforcer([_position(entree=100.0)], Side.BUY,
                                    verifier_espacement=False)
        assert ok, why

    def test_l_espacement_se_mesure_depuis_la_DERNIERE_unite(self):
        """Pas depuis la moyenne ponderee, qui recule a chaque ajout.

        Position fusionnee : entree moyenne 100, derniere unite a 110.
        Un prix de 110,5 n'est qu'a 0,1 ATR de la derniere unite : refuse.
        Le mesurer depuis la moyenne donnerait 1,05 ATR et laisserait
        empiler deux etages sur le meme mouvement.
        """
        pos = _position(entree=100.0)
        pos.derniere_entree = 110.0
        pos.etages = 2
        rm = _gestionnaire(pyramide_max=3, pyramide_espacement_atr=0.5,
                           pyramide_locked_r_min=-1.0)
        ok, why = rm.peut_renforcer([pos], Side.BUY, prix=110.5, atr=5.0)
        assert not ok, (
            "espacement mesure depuis la moyenne ponderee (100) au lieu de "
            "la derniere unite (110) : deux etages sur le meme mouvement")

    def test_le_plafond_compte_les_ETAGES_pas_les_lignes(self):
        """Au comptant, trois unites vivent dans UNE position.

        Compter les positions rendrait toujours 1 et le plafond ne serait
        jamais atteint.
        """
        pos = _position(entree=100.0)
        pos.etages = 3
        pos.derniere_entree = 100.0
        rm = _gestionnaire(pyramide_max=2, pyramide_espacement_atr=0.0,
                           pyramide_locked_r_min=-1.0)
        ok, why = rm.peut_renforcer([pos], Side.BUY, prix=200.0, atr=1.0)
        assert not ok, "4e etage accepte alors que le maximum est 3 unites"
        assert "maximum 2" in why


class TestUnePositionQuiAvanceNeSortJamaisSurLeTemps:
    """Decision de l'operateur du 6 septembre 2026.

    « Aucune limite de temps tant que la position evolue, meme si elle
    monte pendant 20 jours. Si elle fait pratiquement peu de mouvement en
    5 jours, la elle se ferme. »

    Ce qui change n'est pas le nombre de jours, c'est LE R QU'ON REGARDE.
    L'ancienne regle lisait le R COURANT : une position montee a +3 R puis
    redescendue a +0,2 R etait fermee comme si elle avait stagne, alors
    que c'est au stop suiveur de decider. On lit le MEILLEUR parcours.

    Mesure hors echantillon, frais doubles, 70 paires, 2,2 ans :
        ancienne regle 12 j     +35,8 %   Sharpe 0,53   recul 35,4 %
        aucune limite du tout   +31,8 %   Sharpe 0,50   recul 35,6 %
        stagnation 5 j / 0,5 R  +73,1 %   Sharpe 0,79   recul 34,0 %
    """

    @staticmethod
    def _tm():
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig
        return TradeManager(TradeManagerConfig(stagnation_jours=5.0,
                                               stagnation_max_r=0.5))

    @staticmethod
    def _pos(meilleur: float, jours: float):
        """Position ouverte il y a `jours`, dont le sommet vaut `meilleur` R."""
        p = _position(entree=100.0, stop=98.0)          # 1R = 2.0
        p.initial_risk = 2.0
        p.opened_at = time.time() - jours * 86400
        p.max_favorable = 100.0 + meilleur * 2.0
        return p

    def _sortie(self, pos):
        from gold_bot.trade_manager import Momentum
        return self._tm()._safety_exits(
            pos, price=pos.entry_price, r_now=0.0,
            momentum=Momentum(score=0.0), now=time.time())

    def test_vingt_jours_de_hausse_ne_se_ferment_PAS(self):
        """Le coeur de la demande : on laisse courir."""
        action = self._sortie(self._pos(meilleur=3.0, jours=20))
        assert action is None, (
            f"position fermee apres 20 jours alors qu'elle a fait +3 R : "
            f"{action.reason if action else ''} — seul le stop suiveur "
            "doit la sortir")

    def test_cinq_jours_sans_bouger_se_ferment(self):
        action = self._sortie(self._pos(meilleur=0.1, jours=5.5))
        assert action is not None, "position immobile depuis 5 jours non fermee"
        assert "stagnation" in action.reason

    def test_avant_cinq_jours_on_laisse_le_temps(self):
        action = self._sortie(self._pos(meilleur=0.1, jours=3))
        assert action is None, "ferme avant les 5 jours accordes"

    def test_le_sommet_compte_PAS_le_prix_du_moment(self):
        """La regression que l'ancienne regle produisait.

        Position montee a +3 R, retombee a l'entree, ouverte depuis
        10 jours. L'ancienne regle la fermait (R courant nul). La nouvelle
        la garde : elle a bouge, donc c'est au stop suiveur de trancher.
        """
        pos = self._pos(meilleur=3.0, jours=10)
        assert self._sortie(pos) is None, (
            "fermee alors que son meilleur parcours vaut +3 R : la regle "
            "lit encore le prix du moment au lieu du sommet")

    def test_desarme_le_defaut_du_code_garde_l_ancienne_regle(self):
        from gold_bot.trade_manager import TradeManagerConfig
        assert TradeManagerConfig().stagnation_jours == 0.0

    def test_les_deux_regles_ne_tournent_jamais_ensemble(self):
        """Deux regles pour une meme sortie : le piege du CLAUDE.md."""
        import inspect
        from gold_bot.trade_manager import TradeManager
        src = inspect.getsource(TradeManager._safety_exits)
        assert "elif age_min >= cfg.time_stop_minutes" in src, (
            "le stop temporel n'est plus dans un `elif` : il peut fermer "
            "une position que la regle de stagnation venait d'epargner")

    def test_le_reglage_livre_coupe_a_CINQ_JOURS(self):
        """5 jours, et sur le R COURANT — pas sur le pic.

        L'operateur a demande « pas de limite tant que ca evolue, sortie
        a 5 jours si ca stagne ». J'ai d'abord arme la version « pic »,
        puis il a demande : « si la position monte a +3 R avec un bon
        stop suiveur, elle sera coupee avant de toucher 0,2 R, non ? »

        Oui. 1 R = 1,6 ATR, le suiveur lache 2,2 ATR sous le plus-haut
        (1,375 R) : un pic a +3 R sort a +1,62 R. Le cas que le critere
        « pic » protege n'existe pas — il ne fait qu'epargner les
        positions dont le pic est reste entre 0,5 et 1,1 R, trop faible
        pour armer le suiveur, et qui meurent ensuite.

        Mesure 2x2, hors echantillon, frais doubles :

            A  12 j / R courant   +46,0 %   Sharpe 0,61   <- ancien
            B   5 j / R courant   +94,5 %   Sharpe 0,91   <- arme
            C  12 j / pic         +34,7 %   Sharpe 0,52
            D   5 j / pic         +73,1 %   Sharpe 0,79

        Tout le gain vient du DELAI. Le critere « pic » degrade des deux
        cotes. La demande de fond est respectee : a +3 R au 20e jour,
        r_now vaut 3 — bien au-dessus de 0,4 — donc rien ne la ferme.
        """
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.trade.time_stop_minutes == 7200.0, "5 jours = 7200 minutes"
        assert cfg.trade.time_stop_min_r == 0.4
        assert cfg.trade.stagnation_jours == 0.0, (
            "le critere « pic » est mesure PIRE que le R courant : "
            "+73,1 % contre +94,5 % hors echantillon")

    def test_une_hausse_longue_n_est_pas_coupee_par_le_stop_temporel(self):
        """La demande de fond, verifiee sur la regle REELLEMENT armee."""
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig, Momentum
        tm = TradeManager(TradeManagerConfig(time_stop_minutes=7200.0,
                                             time_stop_min_r=0.4))
        p = _position(entree=100.0, stop=98.0)
        p.initial_risk = 2.0
        p.opened_at = time.time() - 20 * 86400        # 20 jours
        action = tm._safety_exits(p, price=106.0, r_now=3.0,
                                  momentum=Momentum(score=0.0), now=time.time())
        assert action is None, (
            f"position a +3 R fermee apres 20 jours : "
            f"{action.reason if action else ''}")


class TestLeStopSuiveurEstUnCliquet:
    """Le pyramidage desarmait le stop suiveur. Trouve le 9 septembre 2026.

    `initial_risk` est le denominateur du R, et il GROSSIT a chaque etage
    ajoute. Le R courant retombait donc sous `trail_start_r`, et le stop
    suiveur se desarmait : la position gardait le stop fige du dernier
    etage, sans plus rien pour le remonter.

    Mesure sur 65 actions US, 10 ans, meme configuration :

        pyramidage desarme  ->  position la plus longue    75 jours
        pyramidage arme     ->  position la plus longue 3 510 jours

    Dix ans avec le capital bloque a 98 %. En crypto le defaut se voyait
    moins — la volatilite ramene vite le prix sur le stop fige — mais il
    etait le meme. Ajouter du volume a un gagnant ne doit pas lui retirer
    sa protection.
    """

    @staticmethod
    def _tm():
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig
        return TradeManager(TradeManagerConfig(trail_start_r=1.1))

    def test_le_defaut_est_desarme(self):
        assert _position().trail_arme is False

    def test_le_cliquet_est_bien_dans_manage(self):
        """Le cliquet vit dans `manage`, la ou le stop suiveur se calcule.

        On verifie la source plutot que le comportement : `manage` exige
        un tick, un jeu d'indicateurs et un carnet complets, et un test
        qui reconstruit tout ca casserait a la premiere refonte sans rien
        prouver de plus.
        """
        import inspect
        from gold_bot.trade_manager import TradeManager
        src = inspect.getsource(TradeManager.manage)
        assert "position.trail_arme = True" in src, (
            "le cliquet ne s arme plus dans manage()")
        assert "if position.trail_arme:" in src, (
            "le stop suiveur est redevenu conditionne au R courant : il se "
            "desarmera a chaque etage de pyramide")

    def test_le_R_qui_retombe_ne_desarme_plus(self):
        """Le scenario exact : un etage ajoute fait retomber le R."""
        p = _position(entree=100.0, stop=98.0)
        p.initial_risk = 2.0
        p.trail_arme = True
        # Un etage s'ajoute : initial_risk triple, le R courant s'effondre.
        p.initial_risk = 6.0
        assert p.trail_arme is True, (
            "le cliquet doit survivre au recalcul de initial_risk — c'est "
            "tout l'interet")


class TestLeCliquetSArmeSansDependreDuR:
    """Le premier cliquet ne pouvait jamais s'armer. Corrige le 9 sept. 2026.

    Il s'armait sur `r_now >= trail_start_r`. Or `initial_risk` grossit a
    chaque etage, donc le R d'une position renforcee ne repasse JAMAIS
    au-dessus du seuil — et au redemarrage le drapeau repart a false pour
    toutes les positions. Constat de l'operateur : plus aucun stop ne
    bougeait sur les 10 positions ouvertes.

    On mesure donc la progression en ATR, qui ne depend d'aucun
    denominateur mobile, plus deux preuves qui survivent a un
    redemarrage : un stop deja au-dessus de l'entree, et une pyramide de
    plusieurs etages.
    """

    @staticmethod
    def _src():
        import inspect
        from gold_bot.trade_manager import TradeManager
        return inspect.getsource(TradeManager.manage)

    def test_la_progression_se_mesure_en_ATR(self):
        src = self._src()
        assert "progres_atr" in src, (
            "le cliquet mesure encore la progression en R : il ne pourra "
            "pas s'armer sur une position pyramidee")
        assert "cfg.trail_start_r * cfg.atr_stop_mult" in src, (
            "le seuil en ATR doit rester derive de trail_start_r, sinon "
            "changer le reglage ne changerait plus rien")

    def test_un_stop_deja_au_dessus_de_l_entree_arme_le_cliquet(self):
        """Preuve de progression qui survit a un redemarrage."""
        assert "position.locked_r() > 0" in self._src(), (
            "une position deja protegee doit retrouver son stop suiveur "
            "apres un redemarrage, meme si max_favorable a ete perdu")

    def test_une_pyramide_arme_le_cliquet(self):
        """Un etage ne s'ajoute qu'apres 0,5 N de progression."""
        assert "position.etages > 1" in self._src(), (
            "une pyramide a forcement progresse : elle doit avoir son "
            "stop suiveur, c'est justement elle que le bug privait")


class TestLaPyramideSurvitAuRedemarrage:
    """Sans persistance, un redemarrage effacait la pyramide.

    Trouve le 9 septembre 2026 sur une question de l'operateur : « il a
    quel etage du pyramide ? ». Le robot ne savait pas repondre — le
    compteur repartait a 1 a chaque demarrage.

    Consequence mesurable et deja survenue : KAVA s'est retrouvee avec
    QUATRE unites alors que le maximum arme en autorise trois. Le robot,
    croyant repartir de zero, avait rajoute un etage sur une pyramide
    deja pleine. Six unites font -40,8 % hors echantillon : le plafond
    n'est pas decoratif.
    """

    CHAMPS = ("etages", "derniere_entree", "trail_arme")

    def test_les_trois_champs_sont_memorises(self):
        import inspect
        from gold_bot.state import TradeJournal, StateStore
        src = inspect.getsource(StateStore)
        for champ in self.CHAMPS:
            assert f'"{champ}": pos.{champ}' in src, (
                f"{champ} n'est pas ecrit dans state.json : un redemarrage "
                "l'effacera")

    def test_les_trois_champs_sont_restaures(self):
        import inspect
        from gold_bot.state import StateStore
        src = inspect.getsource(StateStore.restore_position)
        for champ in self.CHAMPS:
            assert f'pos.{champ} = meta.get("{champ}"' in src, (
                f"{champ} n'est pas relu au demarrage")

    def test_le_defaut_de_etages_est_UN_pas_zero(self):
        """Une position sans historique compte pour une unite, pas zero.

        A zero, `peut_renforcer` autoriserait un etage de plus que le
        plafond sur toute position dont l'etat a ete perdu.
        """
        import inspect
        from gold_bot.state import StateStore
        src = inspect.getsource(StateStore.restore_position)
        assert 'meta.get("etages", 1)' in src


class TestLaLargeurDuStopSuiveur:
    """2,0 ATR, arme le 9 septembre 2026 — et pourquoi PAS plus serre.

    L'operateur avait vu juste : les positions rendaient leurs gains.
    KAVA valait +5,57 EUR de gain latent et serait sortie a +0,71 ;
    NEAR +2,58 pour une sortie a +0,10. Un suiveur a 2,2 ATR lache 8 a
    14 % du prix selon la crypto — il ne peut pas proteger un gain de 6 %.

    LA PREMIERE MESURE DISAIT DE SERRER A 0,6 ATR (+403 % hors
    echantillon, Sharpe 2,16). C'ETAIT FAUX, et le defaut etait dans le
    modele d'execution : le rejeu sortait TOUJOURS au prix du stop.
    Acceptable pour un stop large ; fiction pour un stop serre pose sous
    le plus-haut de la veille, que l'OUVERTURE franchit une fois sur
    deux. Le rejeu offrait donc chaque jour le plus-haut de la veille.

    Le signe qui aurait du alerter plus tot : le resultat s'ameliorait
    SANS LIMITE en serrant (0,2 ATR rendait +1253 %), et la duree
    medianne tombait a 1 jour. Une mesure qui s'ameliore indefiniment
    dans une direction decrit un defaut de modele, pas un optimum.

    Une fois le gap modelise (`sortie = min(stop, ouverture)`), le
    classement s'inverse, hors echantillon, frais doubles :

        0,6 ATR   -26,5 %   Sharpe -0,38   recul 46,7 %
        1,6 ATR   -10,5 %   Sharpe  0,00   recul 34,4 %
        2,0 ATR   +27,9 %   Sharpe  0,48   recul 33,6 %   <- arme
        2,2 ATR   +16,8 %   Sharpe  0,37   recul 34,5 %
        2,6 ATR    +5,5 %   Sharpe  0,25   recul 35,0 %

    2,0 bat 2,2 sur les trois criteres, en apprentissage comme hors
    echantillon. Le gain est modeste et c'est normal : il n'y avait pas
    de miracle a trouver.
    """

    def test_le_reglage_livre_est_a_deux_ATR(self):
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.trade.trail_atr_mult == 2.0

    def test_ne_pas_serrer_le_suiveur(self):
        """Le piege a ne pas retomber dedans.

        Serrer parait toujours meilleur tant que le rejeu ne modelise pas
        le gap d'ouverture. Sous 1,6 ATR, la mesure honnete est negative
        hors echantillon.
        """
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.trade.trail_atr_mult >= 1.6, (
            "suiveur serre sous 1,6 ATR : mesure PERDANT hors echantillon "
            "des que le gap d'ouverture est modelise (-26,5 % a 0,6 ATR)")


class TestLePlafondDeCorrelationEstRetire:
    """Retire le 9 septembre 2026, pour ALIGNER le robot sur la mesure.

    LA RAISON N'EST PAS « plus d'opportunites », c'est la coherence :
    `turtle-variants/backtests/moteur.py` NE MODELISE PAS les groupes
    correles. Tous les rejeux — y compris celui qui a valide le
    pyramidage « a l'abri » — ont donc ete faits SANS aucune limite de
    correlation. Le moteur reel etait plus bride que la configuration
    mesuree.

    C'est la meme classe d'ecart que le stop temporel du harnais (seuil
    0 R contre 0,4 R en reel) ou le gap d'ouverture : le rejeu mesurait
    une chose, le robot en faisait une autre.

    Historique du reglage, aucune valeur jamais mesuree :
        22 aout   Claude      2   valeur par defaut, sans mesure
        25 aout   operateur   1   « reduce correlated exposure »
        28 aout   operateur   2   « liberer les opportunites »
        9 sept    operateur  99   alignement sur le rejeu

    CE QU'ON PERD, et c'est assume : la protection contre le scenario du
    31 aout — six stops pleins en une nuit sur des cryptos correlees.
    Le garde-fou qui reste est `max_total_risk_pct` (3,5 %), qui borne
    la perte totale quel que soit le nombre de familles touchees.
    """

    def test_le_plafond_est_retire(self):
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.risk.max_per_correlation_group >= 99

    def test_le_budget_de_risque_reste_la_vraie_borne(self):
        """Sans plafond par famille, c'est lui qui limite l'exposition."""
        cfg = BotConfig.load("robot.bitvavo.json")
        assert 0 < cfg.risk.max_total_risk_pct <= 5.0, (
            "le budget de risque total est desormais le SEUL garde-fou "
            "contre une exposition sectorielle concentree")
