"""Moteur autonome.

Boucle unique, qui tourne 24h/24 sans intervention :

    synchroniser le compte
      -> gerer les positions ouvertes (stop, objectif, extension)
      -> encaisser les cloturees
      -> si le risque le permet : scanner l'univers
      -> si une opportunite passe TOUS les filtres : envoyer l'ordre
      -> dormir le temps utile, recommencer

Le robot ne demande jamais de validation : il analyse, decide et execute.
Les seules choses qui l'arretent sont ses propres coupe-circuits (limite de
perte, drawdown maximal) ou un arret explicite.

Robustesse : toute exception d'un cycle est capturee, comptee et suivie
d'une temporisation croissante. Un cycle en echec n'arrete pas le robot ;
seule une serie continue d'echecs declenche une alerte critique et une
mise en pause.
"""
from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .apprentissage import PoidsAdaptatifs, alimenter_depuis_journal
from .calibrage import calibrer, duree_stop_temporel
from .promotion import Promotion
from .brokers import (BinanceBroker, BinanceConfig, BinanceSpotBroker,
                      BitvavoBroker, BitvavoConfig, Broker,
                      BrokerError, MoonXBroker, MoonXConfig, OkxBroker,
                      OkxConfig, PaperBroker,
                      PaperConfig, SpotConfig)
from .core import ClosedTrade, Position, Side, Tick
from .datasources import DataRegistry, build_registry
from .macro import MacroEngine
from .news import NewsFilter
from .notifiers import Notifier
from .objectives import ObjectiveTracker
from .risk import RiskManager
from .scanner import Scanner, ScanResult
from .settings import BotConfig
from .state import StateStore, TradeJournal
from .strategy import Evaluation, Strategy
from .trade_manager import ActionType, TradeAction, TradeManager
from .universe import Instrument, Universe

logger = logging.getLogger(__name__)


def _devise_du_lieu_d_execution(broker: str) -> str:
    """Devise de cotation imposee aux sources de prix, selon le broker.

    Les plateformes europeennes cotent en euros, les autres en dollars.
    Melanger les deux pour un meme instrument ferait calculer les niveaux
    sur une echelle de prix differente de celle ou les ordres partent :
    l'ecart euro/dollar depasse largement la taille d'un stop.

    Une chaine vide signifie « aucune contrainte » : les lieux d'execution
    en dollars gardent le jeu complet des sources de secours.
    """
    if broker in ("bitvavo", "bitvavo_margin"):
        return BitvavoConfig.from_env().quote_asset
    if broker == "okx":
        return OkxConfig.from_env().quote_asset
    return ""


def registre_pour(config) -> DataRegistry:
    """Construit le registre de donnees pour une configuration.

    Point d'entree UNIQUE. Le verrou de devise avait deja ete oublie deux
    fois — dans le backtest, puis dans les commandes du terminal — parce
    que chaque appelant reconstruisait le registre a sa facon. Un
    quatrieme oubli couterait des prix en dollars pour des ordres en
    euros, sans message d'erreur.
    """
    return build_registry(
        offline=config.engine.offline,
        devise_crypto=_devise_du_lieu_d_execution(config.engine.broker))


def positions_tenables(equity: float, notionnel_minimum: float,
                       part_engageable_pct: float, plafond: int) -> tuple[int, str]:
    """Combien de positions simultanees le capital permet reellement.

    La contrainte n'est pas un palier arbitraire mais le ticket d'entree de la
    plateforme : un compte de 60 avec un minimum de 5 par ordre peut tenir
    plusieurs lignes. L'ancienne table fixe (« sous 100 = une seule position »)
    ramenait un tel compte a une position unique, ce qui bridait le nombre de
    trades bien plus surement que n'importe quel filtre de strategie.

    Retourne le nombre de positions et le nom du palier correspondant.
    """
    if equity <= 0 or notionnel_minimum <= 0 or plafond <= 0:
        return max(0, min(1, plafond)), "insuffisant"

    engageable = equity * max(0.0, part_engageable_pct) / 100.0
    capacite = int(engageable // notionnel_minimum)

    if capacite <= 0:
        palier = "insuffisant"
    elif capacite < 3:
        palier = "micro"
    elif capacite < 8:
        palier = "petit"
    elif capacite < 20:
        palier = "moyen"
    else:
        palier = "confortable"

    return max(1, min(capacite, plafond)), palier


class TradingEngine:
    """Orchestrateur : assemble tous les modules et fait tourner la boucle."""

    def __init__(self, config: Optional[BotConfig] = None,
                 notifier: Optional[Notifier] = None) -> None:
        self.config = config or BotConfig.load()
        cfg = self.config

        problems = cfg.validate()
        if problems:
            for p in problems:
                logger.error("configuration : %s", p)
            raise ValueError("configuration incoherente : " + " | ".join(problems))

        self.notifier = notifier or Notifier()
        self.universe = Universe()
        if cfg.engine.symbols:
            self.universe.enable_only([s.upper() for s in cfg.engine.symbols])

        # Les prix doivent etre lus dans la devise ou les ordres partiront :
        # sur Bitvavo c'est l'euro, et une bascule silencieuse vers une
        # source en dollars fausserait tous les niveaux de 8 %.
        self.registry: DataRegistry = registre_pour(self.config)
        self.macro = MacroEngine(self.registry)
        self.news = NewsFilter()
        self.trade_manager = TradeManager(cfg.trade)
        # Reference du stop temporel, figee ici et jamais recalculee : c'est
        # le couple (unite d'entree, delai) tel que la configuration l'a
        # ecrit, avant que le calibrage ne touche a l'unite. Le relire plus
        # tard reviendrait a transposer depuis une valeur deja transposee,
        # et le delai deriverait a chaque cycle.
        self._stop_temporel_reference: Optional[tuple[str, float]] = (
            cfg.strategy.entry_tf, cfg.trade.time_stop_minutes)
        # Ce que le robot a reellement gagne ou perdu, relu au demarrage.
        # C'est la seule source de verite disponible pour apprendre : les
        # trades fermes. Sans journal, la ponderation reste neutre.
        self.poids = PoidsAdaptatifs()
        self.strategy = Strategy(cfg.strategy, self.trade_manager, self.macro,
                                 poids=self.poids)
        self.scanner = Scanner(self.registry, self.universe, self.strategy,
                               self.news, cfg.strategy.history,
                               max_workers=cfg.engine.scan_workers)
        self.risk = RiskManager(cfg.risk)
        # Le risque VOULU par le fichier, garde avant que le calibrage ou le
        # palier de croissance ne le rabaissent. Sans cette reference, un
        # plafond applique une fois deviendrait definitif : le robot ne
        # saurait plus a quoi revenir une fois l'avantage etabli.
        self._risque_configure = float(cfg.risk.base_risk_pct)
        # Plancher impose par le ticket minimum de la plateforme, rempli par
        # le calibrage. Le palier ne descend jamais en dessous.
        self._risque_plancher = 0.0
        self.objectives = ObjectiveTracker(cfg.objectives)
        # Le lieu d'execution nomme l'instance : deux robots sur deux
        # plateformes tiennent ainsi des comptes separes, sans quoi leurs
        # plafonds de pertes et leurs journaux se melangeraient.
        instance = cfg.engine.broker
        self.store = StateStore(instance=instance)
        self.journal = TradeJournal(instance=instance)
        # Le journal existe enfin : c'est seulement ici qu'on peut nourrir
        # la ponderation avec les trades reellement fermes.
        alimenter_depuis_journal(self.poids, self.journal.path)
        # Date du dernier changement de reglage decisif : tout ce qui juge
        # la performance compte a partir de la, sans quoi une strategie
        # neuve herite des pertes de celle qu'elle remplace.
        from .version_strategie import marqueur
        self._strategie_depuis, strategie_changee = marqueur(cfg, instance)
        if strategie_changee:
            # LE RESULTAT DE LA SEMAINE APPARTIENT A LA STRATEGIE QUI L'A FAIT.
            #
            # Observe sur le premier trade du M30 : « semaine negative
            # (-159 % de l'objectif) : risque reduit », donc position
            # divisee par deux. Ces -5,79 EUR venaient de la configuration
            # precedente. La nouvelle n'avait rien perdu et se voyait
            # penalisee pour les pertes d'une autre.
            ancien = self.objectives.state.realized_this_week
            if abs(ancien) > 1e-9:
                logger.warning(
                    "STRATEGIE MODIFIEE : resultat hebdomadaire remis a zero "
                    "(%.2f %s appartenaient a la configuration precedente)",
                    ancien, cfg.engine.currency)
                self.objectives.state.realized_this_week = 0.0
                self.objectives.state.trades_this_week = 0
                self.objectives.state.achieved_this_week = False
                self.objectives.save()
        self.broker: Broker = self._build_broker()

        self._running = False
        # Dernier niveau de stop ANNONCE dans le journal, par position.
        self._stop_journalise: dict[str, float] = {}
        self._stop_requested = False
        self._consecutive_errors = 0
        self._last_heartbeat = 0.0
        self._last_report_day = ""

    # ---------------------------------------------------------------
    def _build_broker(self) -> Broker:
        cfg = self.config.engine
        if cfg.broker == "moonx":
            mx = MoonXConfig.from_env()
            if cfg.dry_run:
                mx.dry_run = True
            broker = MoonXBroker(mx)
        elif cfg.broker == "binance":
            bn = BinanceConfig.from_env()
            if cfg.dry_run:
                bn.dry_run = True
            broker = BinanceBroker(bn)
        elif cfg.broker == "binance_spot":
            sp = SpotConfig.from_env()
            if cfg.dry_run:
                sp.dry_run = True
            broker = BinanceSpotBroker(sp)
        elif cfg.broker == "bitvavo":
            bv = BitvavoConfig.from_env()
            # DEUX INTERRUPTEURS, ET LE FICHIER L'EMPORTE.
            #
            # `BITVAVO_DRY_RUN=0` dans .env ne suffit pas si la
            # configuration porte `"dry_run": true` — et rien ne le disait.
            # Observe en production : un robot en argent reel cote .env
            # ouvrait ses positions en simulation, avec la mention
            # « (dry-run) » noyee au milieu du journal.
            #
            # Le fichier reste prioritaire, c'est le comportement voulu :
            # une configuration livree ne doit jamais s'armer toute seule.
            # Mais la contradiction est desormais annoncee, et elle nomme
            # les deux reglages.
            if cfg.dry_run and not bv.dry_run:
                logger.warning(
                    "SIMULATION IMPOSEE PAR LA CONFIGURATION. "
                    "BITVAVO_DRY_RUN=0 demande le mode reel, mais %s porte "
                    "\"dry_run\": true — c'est le fichier qui l'emporte. "
                    "Pour engager de l'argent, passez-le a false.",
                    getattr(self.config, "source", "la configuration"))
            if cfg.dry_run:
                bv.dry_run = True
            broker = BitvavoBroker(bv)
        elif cfg.broker == "okx":
            ok = OkxConfig.from_env()
            if cfg.dry_run:
                ok.dry_run = True
            broker = OkxBroker(ok)
        else:
            broker = PaperBroker(PaperConfig(start_balance=cfg.start_balance,
                                             currency=cfg.currency))

        # Un lieu d'execution ne propose pas forcement tout l'univers : scanner
        # un instrument qu'on ne pourra pas trader gaspille des appels reseau
        # et produit des signaux inexploitables.
        if hasattr(broker, "supports"):
            self._filtrer_univers_sur_le_broker(broker)

        for inst in self.universe:
            if hasattr(broker, "register_instrument"):
                broker.register_instrument(inst)
        return broker

    # ---------------------------------------------------------------
    def _filtrer_univers_sur_le_broker(self, broker=None) -> list[str]:
        """N'active que les instruments reellement cotables sur ce lieu.

        Appele deux fois : a la construction, sur la seule liste des actifs
        connus du broker, puis apres le chargement des regles de marche, quand
        on sait quelles paires existent dans la devise de cotation retenue.
        """
        broker = broker or self.broker
        if not hasattr(broker, "supports"):
            return []

        traitables, ecartes = [], []
        for inst in self.universe:
            (traitables if broker.supports(inst.symbol) else ecartes).append(inst.symbol)

        if ecartes:
            apercu = ", ".join(ecartes[:12])
            if len(ecartes) > 12:
                apercu += f", … (+{len(ecartes) - 12})"
            logger.info("%s ne propose pas %d instrument(s) : %s",
                        broker.name, len(ecartes), apercu)
        logger.info("univers retenu : %d instrument(s) cotables", len(traitables))
        self.universe.enable_only(traitables)
        return ecartes

    # ---------------------------------------------------------------
    def _appliquer_palier_de_croissance(self) -> None:
        """Plafonne le risque par trade tant que l'avantage n'est pas prouve.

        Un compte grandit par `risque x esperance`. Monter le risque avant
        de connaitre le signe de l'esperance ne fait pas grandir plus vite :
        ca amplifie ce qui est la. Le 28 aout, 72 trades a -0,406 R — doubler
        le risque aurait divise le temps de survie par deux.

        Le plafond suit donc l'echantillon reel du journal, et il ne peut
        que RESTREINDRE ce que la configuration demande : un fichier qui
        reclame 1,5 % n'obtient 1,5 % qu'une fois l'avantage etabli.
        """
        from .croissance import diagnostiquer

        try:
            # UNIQUEMENT les trades de la strategie EN COURS. Le journal est
            # cumulatif : compter tout l'historique verrouillerait le palier
            # sur les pertes d'une configuration remplacee depuis, et ferait
            # lire « 0 % de reussite » a l'operateur pour une strategie qui
            # n'a pas encore trade.
            stats = self.journal.stats(since=self._strategie_depuis)
        except Exception as exc:  # noqa: BLE001 - jamais bloquant
            logger.debug("palier de croissance : journal illisible (%s)", exc)
            return

        diag = diagnostiquer(self.risk.account.equity, 0.0, stats, 0.0)
        demande = float(self._risque_configure)
        plancher = float(self._risque_plancher)
        retenu = max(min(demande, diag.palier.risque_pct), plancher)
        if abs(self.risk.config.base_risk_pct - retenu) < 1e-9:
            return

        self.risk.config.base_risk_pct = retenu
        if retenu < demande:
            logger.warning(
                "PALIER « %s » : risque ramene a %.2f %% (la configuration "
                "demande %.2f %%) — %d trade(s), esperance %+.3f R. Manque : %s",
                diag.palier.nom, retenu, demande, diag.trades, diag.esperance_r,
                "; ".join(diag.manques) or "conditions du palier suivant non remplies")
        elif plancher > diag.palier.risque_pct:
            logger.warning(
                "PALIER « %s » releve a %.2f %% : le ticket minimum de la "
                "plateforme l'impose. En dessous, aucun trade n'est "
                "dimensionnable.", diag.palier.nom, retenu)
        else:
            logger.info("PALIER « %s » : risque a %.2f %% par trade, "
                        "avantage etabli sur %d trade(s) (%+.3f R)",
                        diag.palier.nom, retenu, diag.trades, diag.esperance_r)

    # ---------------------------------------------------------------
    def _calibrer_sur_le_capital(self) -> None:
        """Aligne la strategie sur ce que le capital permet reellement.

        Le risque par trade peut etre remonte, jamais au-dela du plafond
        ecrit dans la configuration. C'est une deduction arithmetique a
        partir du ticket minimum de la plateforme, pas une reaction aux
        resultats : augmenter la mise parce qu'on vient de gagner est une
        facon connue de se ruiner, et le calibrage ne fait pas cela.
        """
        cfg = self.config
        ticket = 0.0
        if hasattr(self.broker, "notionnel_minimum"):
            try:
                ticket = float(self.broker.notionnel_minimum())
            except Exception as exc:  # noqa: BLE001
                logger.warning("ticket minimum illisible : %s", str(exc)[:120])
        self.frais_reels = float(
            getattr(getattr(self.broker, "config", None), "fee_rate", 0.0)
            or cfg.risk.commission_pct or 0.0)

        # Une fenetre sans commission change ce que la strategie peut viser.
        # Elle porte sa propre fin : voir gold_bot/promotion.py.
        self.promotion = Promotion.depuis_config(self.config.promotion)
        if self.promotion.active:
            logger.warning("tarif : %s", self.promotion.resume())
        frais = self.promotion.frais_effectifs(self.frais_reels)

        # La commission du gestionnaire de RISQUE doit suivre le meme
        # regime que le calibrage. Sans cela, le robot refuse des trades
        # pour des frais que la plateforme ne preleve pas : mesure en
        # production, un cout annonce a 46 % du risque sur ETH et 100 %
        # sur AVAX, alors que la promotion les ramenait a 13 %.
        #
        # Un seuil calcule sur un cout imaginaire est un seuil faux, et
        # il bloque en silence — le robot trouvait ses signaux, les
        # validait, puis les jetait tous au dimensionnement.
        if self.config.risk.commission_pct != frais:
            logger.warning("commission du risque alignee sur le tarif : "
                           "%.4f %% -> %.4f %%",
                           self.config.risk.commission_pct * 100, frais * 100)
            self.config.risk.commission_pct = frais
            if getattr(self, "risk", None) is not None:
                self.risk.config.commission_pct = frais

        cal = calibrer(
            equity=self.broker.account().equity,
            ticket_minimum=ticket,
            frais_par_cote=self.promotion.frais_effectifs(self.frais_reels),
            risk_pct_demande=cfg.risk.base_risk_pct,
            risk_pct_max=cfg.risk.max_risk_pct,
            plafond_cout_pct=cfg.risk.max_cost_ratio_pct,
            plafond_positions=cfg.risk.max_positions,
            part_engageable_pct=cfg.risk.max_capital_engaged_pct,
            # Le stop REELLEMENT configure, et non celui qu'une table
            # supposait. Sans lui, une configuration a 1,60 ATR voyait son
            # M30 evalue a 1,10 % au lieu de 1,28 %, tombait sous le seuil,
            # et le calibrage basculait sur H1 : le robot tournait une
            # strategie differente de celle mesuree au rejeu.
            atr_stop_mult=cfg.trade.atr_stop_mult,
        )
        self.calibrage = cal
        self._ticket_minimum = ticket

        # Le plancher de volatilite doit suivre le plafond de cout, sinon le
        # robot evalue en boucle des instruments que le dimensionnement
        # refusera. Ce n'est pas dangereux — le filtre de cout protege — donc
        # on avertit sans bloquer.
        atr_utile = self.config.atr_minimal_utile()
        if atr_utile > 0 and cfg.strategy.min_atr_price_ratio < atr_utile * 0.95:
            logger.warning(
                "PLANCHER DE VOLATILITE INCOHERENT : %.4f accepte des ATR que "
                "le plafond de cout (%.0f %%) refusera au dimensionnement. Avec "
                "un stop de %.2f ATR il faut au moins %.4f. Le robot va evaluer "
                "puis rejeter les memes instruments a chaque cycle.",
                cfg.strategy.min_atr_price_ratio, cfg.risk.max_cost_ratio_pct,
                cfg.trade.atr_stop_mult, atr_utile)
        # Un palier de croissance que le plafond dur rabote en silence rend
        # le plan de croissance faux au moment ou il compte le plus.
        for probleme in self.config.paliers_inatteignables():
            logger.warning("PALIER DE CROISSANCE INATTEIGNABLE : %s. Le journal "
                           "annoncera le palier, le risque reel restera au "
                           "plafond, et la projection sera fausse d'autant.",
                           probleme)
        self._promo_en_cours = self.promotion.en_cours()
        for ligne in cal.resume():
            logger.info("calibrage : %s", ligne)

        if not cal.viable:
            self.notifier.warning(
                "Capital insuffisant pour cette plateforme", "\n".join(cal.resume()))
        else:
            if cal.risk_pct > cfg.risk.base_risk_pct:
                logger.warning("risque par trade porte a %.3f %% (ticket minimum "
                               "de %.2f a atteindre)", cal.risk_pct, cal.ticket_minimum)
                cfg.risk.base_risk_pct = cal.risk_pct
                # PLANCHER, et non preference : en dessous, le lot minimum de
                # la plateforme est inatteignable et plus aucun trade ne peut
                # etre dimensionne. Le palier de croissance plafonne le risque
                # choisi, jamais celui que l'arithmetique impose — sinon il
                # figerait le robot en croyant le proteger.
                self._risque_plancher = cal.risk_pct

            # L'unite d'entree suit ce que le capital autorise, sauf si la
            # configuration en demande deja une plus lente — on ne descend
            # jamais vers une unite que les frais rendent perdante.
            if cal.unite_conseillee and cfg.strategy.entry_tf not in cal.unites:
                logger.warning("unite d'entree %s hors de portee a ce capital, "
                               "bascule sur %s", cfg.strategy.entry_tf,
                               cal.unite_conseillee)
                cfg.strategy.entry_tf = cal.unite_conseillee
                self.strategy.config.entry_tf = cal.unite_conseillee

        # Hors du « si viable » a dessein : le delai doit suivre l'unite
        # reellement utilisee dans tous les cas. Une sortie anticipee qui
        # sauterait cette ligne laisserait un delai calibre pour une autre
        # unite de temps — precisement le defaut qu'on corrige ici.
        self._transposer_le_stop_temporel()

    def _transposer_le_stop_temporel(self) -> None:
        """Reporte le stop temporel sur l'unite de temps reellement utilisee.

        Le calibrage change l'unite d'entree quand les frais l'imposent. Tout
        le reste de la gestion est exprime en R ou en ATR et suit ce
        changement tout seul ; le stop temporel, lui, est en minutes et ne
        suivait rien.

        Sans cette transposition, la bascule automatique du 30 aout — M15
        vers D1 quand la fenetre sans commission se ferme — laissait un delai
        de quatre heures sur des mouvements qui mettent des jours a se
        former. Presque chaque position aurait ete fermee avant d'avoir eu sa
        chance, et l'aller-retour paye a chaque fois. Silencieusement : le
        robot aurait fait exactement ce qu'on lui avait dit.

        La reference est figee au premier calibrage. Transposer a partir de
        la valeur courante ferait deriver le delai a chaque recalibrage —
        et il y en a un par cycle tant que le regime tarifaire peut changer.
        """
        trade = self.config.trade
        unite_ref, minutes_ref = self._stop_temporel_reference
        unite = self.config.strategy.entry_tf
        minutes = duree_stop_temporel(unite_ref, minutes_ref, unite)
        if abs(minutes - trade.time_stop_minutes) < 0.01:
            return
        logger.warning("stop temporel transpose de %s sur %s : %.0f min -> "
                       "%.0f min (%.1f jour(s))", unite_ref, unite,
                       trade.time_stop_minutes, minutes, minutes / 1440.0)
        trade.time_stop_minutes = minutes
        self.trade_manager.config.time_stop_minutes = minutes

    # ---------------------------------------------------------------
    # Demarrage
    # ---------------------------------------------------------------
    def start(self) -> bool:
        """Prepare le robot. Retourne False si le demarrage est impossible."""
        cfg = self.config.engine

        if cfg.broker == "binance" and not cfg.dry_run:
            bn = getattr(self.broker, "config", None)
            if bn is not None and not bn.testnet:
                self.notifier.warning(
                    "Binance en mode REEL",
                    "Les ordres engagent de l'argent veritable. "
                    "BINANCE_TESTNET=1 bascule sur de l'argent fictif.")

        if cfg.broker == "okx" and not cfg.dry_run and not cfg.offline:
            ok = getattr(self.broker, "config", None)
            if ok is not None and not ok.demo:
                self.notifier.warning(
                    "OKX en mode REEL",
                    "Les ordres engagent de l'argent veritable. "
                    "OKX_DRY_RUN=1 revient a la simulation.")

        if cfg.broker in ("bitvavo", "bitvavo_margin") and not cfg.dry_run:
            detail = ("Les ordres engagent de l'argent veritable. "
                      "BITVAVO_DRY_RUN=1 revient a la simulation.")
            if cfg.broker == "bitvavo_margin":
                detail += (" VENTE A DECOUVERT ACTIVE : une position vendeuse "
                           "emprunte l'actif et paie un interet journalier "
                           "tant qu'elle reste ouverte.")
            self.notifier.warning("Bitvavo en mode REEL", detail)

        if cfg.broker == "moonx" and cfg.offline:
            self.notifier.critical("Demarrage refuse",
                                   "execution reelle demandee avec des donnees synthetiques")
            return False

        # Un broker signale une connexion impossible de DEUX facons : en
        # rendant False, ou en levant une BrokerError qui, elle, porte la
        # cause exacte. Seule la premiere etait traitee : une passerelle IBKR
        # eteinte faisait remonter une trace de pile jusqu'au superviseur,
        # qui relancait le processus sans que personne ne lise jamais la
        # phrase utile. On rattrape donc les deux, et on garde le motif.
        try:
            connecte = self.broker.connect()
            motif = f"broker={cfg.broker} — verifier la configuration"
        except BrokerError as exc:
            connecte, motif = False, str(exc)
        if not connecte:
            logger.error("connexion impossible : %s", motif)
            self.notifier.critical("Connexion au broker impossible", motif)
            if cfg.broker == "ibkr":
                # IBKR ne s'ouvre pas avec une cle : il faut une passerelle
                # authentifiee, second facteur compris. Le journal doit le
                # dire, sinon on cherche du cote de la configuration.
                from .ibkr_readiness import etat_passerelle
                logger.error("%s", etat_passerelle().resume())
            return False

        # Les contraintes de la plateforme font foi sur celles declarees par
        # defaut : tailles de lot, pas de prix, notionnel minimum.
        if hasattr(self.broker, "apply_market_rules"):
            self.broker.apply_market_rules(self.universe)

        # C'est seulement ici qu'on connait a la fois le capital reel et le
        # ticket minimum reel de la plateforme. Le calibrage en deduit ce
        # que ce compte peut viser — aucun capital n'est suppose ailleurs.
        self._calibrer_sur_le_capital()

        # Les regles de marche viennent d'arriver : c'est seulement maintenant
        # qu'on sait quelles paires existent vraiment dans la devise choisie.
        # Sans ce second tri, une paire cotee en USDT mais absente en USDC
        # resterait dans l'univers et consommerait du quota d'API a chaque
        # cycle pour une erreur previsible.
        self._filtrer_univers_sur_le_broker()

        acc = self.broker.account()
        self.risk.sync_account(acc.equity, acc.balance, acc.currency)
        if self.store.state.account_reference:
            self.risk.account.reference_equity = self.store.state.account_reference
        if self.store.state.peak_equity:
            self.risk.account.peak_equity = self.store.state.peak_equity
        if self.store.state.halted:
            self.risk.halt(self.store.state.halt_reason or "arret memorise")

        self.objectives.sync(acc.equity)
        self._restore_positions()

        n_events = self.news.refresh(force=True)
        sources = [s["source"] for s in self.registry.status() if s["configuree"]]

        obj = self.objectives.status()
        body = "\n".join([
            f"Execution      : {cfg.broker}" + (" (DRY-RUN, aucun ordre envoye)" if cfg.dry_run else ""),
            f"Capital        : {acc.equity:.2f} {acc.currency}",
            f"Instruments    : {len(self.universe)} suivis, {len(self.universe.tradable())} ouverts maintenant",
            f"Sources prix   : {', '.join(sources) or 'aucune'}",
            f"Calendrier     : {n_events} evenements charges",
            f"Alertes        : {', '.join(self.notifier.active_channels())}",
            f"Objectif       : palier {obj['palier']}, {obj['objectif']:.2f} {acc.currency} cette semaine"
            + (f" (nominal {obj['objectif_nominal']:.2f}, plafonne par le capital)" if obj["plafonne"] else ""),
            f"Risque/trade   : {self.risk.effective_risk_pct()[0]:.2f} % "
            f"(plafond {self.config.risk.max_risk_pct:.2f} %)",
            f"Positions      : {len(self.broker.positions())} reprises",
            f"Palier capital : {self.capital_tier()['palier']} — "
            f"{self.capital_tier()['positions_simultanees']} position(s) a la fois",
            f"Sens possibles : "
            + ("achat et vente" if getattr(self.broker, "supports_short", True)
               else "ACHAT SEUL (le spot ne permet pas la vente a decouvert)"),
            f"Decision       : mode {self.config.strategy.mode}"
            + (f", {self.config.strategy.min_confirmations} confirmations minimum"
               if self.config.strategy.mode == "quorum" else ""),
        ])
        self.notifier.info("Robot demarre", body)
        self._running = True
        return True

    def _restore_positions(self) -> None:
        """Reprend la gestion des positions deja ouvertes apres un redemarrage."""
        # Au comptant, le lieu d'execution ne voit que des avoirs : il repart
        # sans aucune position. On lui redonne d'abord celles qu'on avait
        # memorisees, sinon la boucle ci-dessous ne trouverait rien a
        # reprendre et les positions ouvertes seraient abandonnees en vol.
        connues = {p.id for p in self.broker.positions()}
        for identifiant in list(self.store.state.position_meta):
            if identifiant in connues:
                continue
            memorisee = self.store.position_memorisee(identifiant)
            if memorisee is None:
                continue
            if not self.broker.reprendre(memorisee):
                logger.info("position memorisee %s non reprise par %s",
                            identifiant, self.broker.name)

        for pos in self.broker.positions():
            if self.store.restore_position(pos):
                logger.info("gestion reprise sur %s %s (%d extension(s), stop a %.5f)",
                            pos.side.value, pos.symbol, pos.tp_extensions, pos.stop_loss)
            else:
                # Position inconnue du robot : on la reprend avec prudence,
                # en deduisant le risque initial des niveaux actuels.
                if not pos.initial_risk:
                    pos.initial_risk = abs(pos.entry_price - pos.stop_loss)
                self.store.remember_position(pos)
                logger.info("position externe adoptee : %s %s", pos.side.value, pos.symbol)
        self.store.save()

    # ---------------------------------------------------------------
    # Boucle principale
    # ---------------------------------------------------------------
    def run(self) -> None:
        """Boucle infinie. Ne rend la main que sur arret demande."""
        if not self._running and not self.start():
            return

        self._install_signal_handlers()
        logger.info("boucle demarree — cadence %.0fs / %.0fs (position ouverte / recherche)",
                    self.config.engine.poll_seconds, self.config.engine.idle_poll_seconds)

        while not self._stop_requested:
            cycle_start = time.time()
            try:
                self.run_cycle()
                self._consecutive_errors = 0
            except KeyboardInterrupt:
                break
            except Exception as exc:  # noqa: BLE001 - le robot ne doit jamais mourir sur un cycle
                self._handle_cycle_error(exc)

            self._sleep_until_next(cycle_start)

        self.shutdown()

    def run_cycle(self) -> None:
        """Un cycle complet de decision."""
        cfg = self.config.engine
        state = self.store.state
        state.cycles += 1
        state.last_cycle = time.time()

        # 1. Etat reel du compte et des positions
        self.broker.sync()
        # Les contraintes de la plateforme font foi sur celles declarees par
        # defaut : tailles de lot, pas de prix, notionnel minimum.
        if hasattr(self.broker, "apply_market_rules"):
            self.broker.apply_market_rules(self.universe)

        acc = self.broker.account()
        self.risk.sync_account(acc.equity, acc.balance, acc.currency)
        self.objectives.sync(acc.equity)
        state.account_reference = self.risk.account.reference_equity
        state.peak_equity = self.risk.account.peak_equity

        positions = self.broker.positions()

        # Le nombre de positions simultanees suit la taille du compte : sur un
        # micro-compte, deux positions ouvertes en meme temps representent une
        # part de risque que le lot minimum rend impossible a maitriser.
        palier = self.capital_tier()
        self.risk.config.max_positions = palier["positions_simultanees"]

        # Le risque par trade ne monte qu'apres PREUVE, jamais par impatience.
        self._appliquer_palier_de_croissance()

        # 2. Gestion des positions ouvertes (priorite absolue)
        self._manage_positions(positions)

        # 3. Detection des cloturees
        self._collect_closed()

        # 4. Recherche d'une nouvelle opportunite
        self._look_for_entry()

        # 5. Suivi periodique
        self._verifier_promotion()
        self._heartbeat()
        self._daily_report()
        self.store.save()

    # ---------------------------------------------------------------
    # Gestion des positions
    # ---------------------------------------------------------------
    def _manage_positions(self, positions: list[Position]) -> None:
        """Applique le trailing, les extensions d'objectif et les sorties."""
        vivantes = {p.id for p in positions}
        for ferme in [i for i in self._stop_journalise if i not in vivantes]:
            self._stop_journalise.pop(ferme, None)
        for pos in positions:
            instrument = self.universe.get(pos.symbol)
            if instrument is None:
                continue
            ctx = self.scanner.context(pos.symbol)
            try:
                self.scanner.refresh_symbol(instrument)
            except Exception as exc:  # noqa: BLE001
                logger.warning("donnees indisponibles pour gerer %s : %s", pos.symbol, str(exc)[:120])
                continue

            ind = ctx.indicators.get(self.config.strategy.entry_tf)
            if ind is None or not ind.ready:
                continue
            tick = self.registry.tick(pos.symbol, instrument.asset_class)
            if tick is None:
                continue

            # Le simulateur a besoin du prix pour evaluer SL/TP lui-meme.
            if isinstance(self.broker, PaperBroker):
                self.broker.set_price(pos.symbol, tick, ind.atr.value or 0.0)
                for trade in self.broker.check_tick(pos.symbol, tick):
                    self._on_trade_closed(trade)
                if pos.id not in {p.id for p in self.broker.positions()}:
                    continue

            chart = ctx.chart(self.config.strategy.entry_tf, instrument.round_step)
            window = self.news.check(instrument.asset_class, pos.symbol)

            actions = self.trade_manager.manage(
                pos, tick, ind, chart=chart, news=window, digits=instrument.digits)
            for action in actions:
                self._apply_action(pos, action, instrument)

            self.store.remember_position(pos)

    def _stop_sur_la_plateforme(self, symbol: str) -> Optional[float]:
        """Stop reellement en carnet, pour les brokers qui en deposent un.

        None quand le broker n'en depose pas (simulateur) : l'appelant se
        rabat alors sur le seul changement de niveau.
        """
        lire = getattr(self.broker, "stop_depose", None)
        return lire(symbol) if callable(lire) else None

    def _apply_action(self, pos: Position, action: TradeAction, instrument: Instrument) -> None:
        """Transmet une action de gestion au broker."""
        try:
            if action.type is ActionType.MODIFY_STOP:
                # POURQUOI CE FILTRE D'AFFICHAGE.
                #
                # Le stop suiveur est un chandelier : max_favorable - k x ATR.
                # Les deux termes bougent a chaque cycle, donc le niveau
                # remonte par increments minuscules — arrondis a
                # instrument.digits, soit 1e-8 sur les cryptos. Chacun est
                # une hausse REELLE, la section 5 du gestionnaire a raison
                # de l'emettre, et le broker a raison de ne pas reposer
                # l'ordre pour si peu (stop_move_threshold_r).
                #
                # Mais la ligne de journal, elle, s'affiche a 1e-5 : le 30
                # aout, UNIUSD a repete « stop -> 4.32703 (+1.15R -> +1.15R
                # verrouille) » toutes les dix secondes pendant quatre
                # minutes. Trente lignes identiques annoncant un
                # deplacement qui n'avait pas eu lieu chez Bitvavo : le
                # journal disait le contraire de la verite, et noyait les
                # vrais paliers.
                #
                # On n'annonce donc que ce qui se voit : un niveau different
                # a l'affichage, ou un ordre reellement repose.
                pose_avant = self._stop_sur_la_plateforme(pos.symbol)
                if self.broker.modify_position(pos.id, stop_loss=action.price):
                    pose_apres = self._stop_sur_la_plateforme(pos.symbol)
                    repose = pose_apres is not None and pose_apres != pose_avant
                    precedent = self._stop_journalise.get(pos.id)
                    visible = precedent is None or round(action.price, 5) != round(precedent, 5)
                    self._stop_journalise[pos.id] = action.price
                    if repose or visible:
                        logger.info("%s : stop -> %.5f (%s)%s", pos.symbol, action.price,
                                    action.reason,
                                    "" if pose_apres is None else
                                    (" [ordre repose]" if repose else " [interne, ordre inchange]"))
                    else:
                        logger.debug("%s : stop interne -> %.8f (%s)",
                                     pos.symbol, action.price, action.reason)

            elif action.type is ActionType.MODIFY_TARGET:
                if self.broker.modify_position(pos.id, take_profit=action.price):
                    self.notifier.trade(
                        f"Objectif repousse — {pos.symbol}",
                        f"{pos.side.value} : TP {pos.initial_tp} -> {action.price}\n"
                        f"Stop a {pos.stop_loss} ({pos.locked_r():+.2f}R verrouille)\n"
                        f"{action.reason}",
                        data={"symbole": pos.symbol, "tp": action.price,
                              "extensions": pos.tp_extensions})

            elif action.type is ActionType.PARTIAL_CLOSE:
                trade = self.broker.close_position(pos.id, action.volume, action.reason)
                if trade:
                    self._on_trade_closed(trade)

            elif action.type is ActionType.CLOSE:
                trade = self.broker.close_position(pos.id, None, action.reason)
                if trade:
                    self._on_trade_closed(trade)

        except BrokerError as exc:
            logger.error("action %s refusee sur %s : %s", action.type.value, pos.symbol, exc)
            self.notifier.warning(f"Action refusee — {pos.symbol}",
                                  f"{action.type.value} : {exc}",
                                  throttle_key=f"action_{pos.symbol}", throttle_seconds=300)

    def _collect_closed(self) -> None:
        """Recupere les trades cloturees par le broker (stop ou objectif touche)."""
        known = {t.position_id for t in self.journal.trades}
        for trade in self.broker.closed_trades():
            key = f"{trade.position_id}_{trade.closed_at}"
            if trade.position_id in known and any(
                    t.position_id == trade.position_id and abs(t.closed_at - trade.closed_at) < 1
                    for t in self.journal.trades):
                continue
            self._on_trade_closed(trade)

    def _on_trade_closed(self, trade: ClosedTrade) -> None:
        """Comptabilise un trade termine."""
        if any(t.position_id == trade.position_id and abs(t.closed_at - trade.closed_at) < 1
               for t in self.journal.trades):
            return

        self.journal.append(trade)
        self.risk.record_close(trade)
        self.objectives.record_trade(trade.profit)
        self.store.state.trades_closed += 1
        self.store.forget_position(trade.position_id)

        obj = self.objectives.status()
        acc = self.risk.account
        level = "trade" if trade.profit >= 0 else "warning"
        self.notifier.notify(
            level,
            f"{'Gain' if trade.profit >= 0 else 'Perte'} {trade.profit:+.2f} {acc.currency} — {trade.symbol}",
            "\n".join([
                f"{trade.side.value} {trade.volume} lots : {trade.entry_price} -> {trade.exit_price}",
                f"Resultat : {trade.r_multiple:+.2f}R ({trade.reason})",
                f"Extensions d'objectif : {trade.tp_extensions}",
                f"Semaine : {obj['realise']:+.2f} / {obj['objectif']:.2f} "
                f"({obj['avancement']:.0%} du palier {obj['palier']})",
                f"Journee : {acc.daily_pnl_pct():+.2f} % | drawdown {acc.drawdown_pct():.2f} %",
            ]),
            data={"symbole": trade.symbol, "profit": trade.profit, "R": trade.r_multiple},
        )

        # Coupe-circuits atteints : on previent immediatement.
        ok, why = self.risk.can_trade(self.broker.positions())
        if not ok and any(k in why for k in ("limite", "drawdown", "pause")):
            self.notifier.warning("Trading suspendu", why,
                                  throttle_key="suspendu", throttle_seconds=1800)

    # ---------------------------------------------------------------
    # Recherche d'entree
    # ---------------------------------------------------------------
    def _look_for_entry(self) -> None:
        """Scanne l'univers et execute la meilleure opportunite validee."""
        positions = self.broker.positions()

        allowed, why = self.risk.can_trade(positions)
        if not allowed:
            logger.debug("pas de recherche : %s", why)
            return

        stop, stop_why = self.objectives.should_stop_trading()
        if stop:
            logger.info("recherche suspendue : %s", stop_why)
            return

        bonus = self.objectives.score_threshold_bonus()
        held = {p.symbol for p in positions}

        def exposure_ok(inst: Instrument) -> tuple[bool, str]:
            return self.risk.check_exposure(inst, Side.BUY, positions, self.universe.get)

        sens = None if getattr(self.broker, "supports_short", True) else {Side.BUY}
        result = self.scanner.scan(score_bonus=bonus, exclude=held,
                                   allow=exposure_ok, allowed_sides=sens)
        logger.info("%s", result.summary())
        if self.config.engine.verbose_scan:
            for line in self.scanner.report(result, verbose=True)[1:]:
                logger.info("%s", line)

        if result.best is None:
            return
        self._execute(result.best)

    def _execute(self, ev: Evaluation, places_visees: Optional[int] = None) -> None:
        """Dimensionne et envoie l'ordre. Aucune validation manuelle.

        `places_visees` : nombre d'occasions reellement disponibles ce
        cycle. Sans lui, le partage du cash reserve une part pour chacune
        des six places libres — y compris celles qu'aucune occasion ne
        viendra remplir.
        """
        instrument = self.universe.get(ev.symbol)
        if instrument is None or ev.side is None:
            return

        positions = self.broker.positions()
        multiplier, why = self.objectives.risk_multiplier()
        sizing = self.risk.size_position(
            instrument, ev.side, ev.entry, ev.stop_loss, ev.take_profit,
            open_positions=positions, universe_lookup=self.universe.get,
            extra_multiplier=multiplier, spread=ev.spread,
            available_cash=self.broker.account().margin_free,
            places_visees=places_visees)

        if not sizing.allowed:
            logger.info("%s ecarte au dimensionnement : %s", ev.symbol, sizing.reason)
            self.notifier.notify("debug", f"Trade non dimensionnable — {ev.symbol}", sizing.reason)
            # Certains refus ne dependent pas des conditions du moment mais du
            # capital : ils se reproduiront a l'identique au prochain cycle.
            # On met l'instrument de cote plutot que de le redemander sans fin.
            structurel = any(m in sizing.reason for m in
                             ("cout d'execution", "lot minimum", "capital insuffisant", "levier autorise"))
            if structurel:
                self.scanner.sleep_symbol(ev.symbol, 3600.0, sizing.reason.split(":")[0].strip())
            return

        try:
            pos = self.broker.open_position(
                instrument, ev.side, sizing.lots, ev.stop_loss, ev.take_profit,
                comment=f"{ev.setup} score={ev.score:.2f}")
        except BrokerError as exc:
            logger.error("ordre refuse sur %s : %s", ev.symbol, exc)
            self.notifier.warning(f"Ordre refuse — {ev.symbol}", str(exc))
            self.store.state.errors += 1
            # Un refus du courtier se reproduit a l'identique au cycle
            # suivant tant que la cause n'a pas bouge (cash pris par une
            # autre position, notionnel sous le minimum). Sans mise en
            # sommeil, l'instrument est repropose toutes les ~10 s et
            # inonde le journal d'ERROR. On le met de cote ; il repassera
            # quand une position se sera fermee.
            self.scanner.sleep_symbol(ev.symbol, 900.0, "ordre refuse par le courtier")
            return

        pos.initial_risk = abs(pos.entry_price - pos.stop_loss) or sizing.stop_distance
        self.store.remember_position(pos)
        self.store.state.trades_opened += 1
        self.risk.account.last_trade_ts = time.time()

        obj = self.objectives.status()
        self.notifier.trade(
            f"Position ouverte — {ev.side.value} {ev.symbol}",
            "\n".join([
                f"Scenario  : {ev.setup} (score {ev.score:.2f} / seuil {ev.threshold:.2f})",
                f"Entree    : {pos.entry_price} | SL {pos.stop_loss} | TP {pos.take_profit} (RR {ev.rr:.2f})",
                f"Volume    : {sizing.lots} lots — risque {sizing.risk_amount:.2f} "
                f"{self.risk.account.currency} ({sizing.risk_pct:.2f} %)",
                f"Taille    : {why}",
                f"Objectif  : palier {obj['palier']}, {obj['realise']:+.2f}/{obj['objectif']:.2f}",
                "Facteurs valides : " + ", ".join(g.name for g in ev.gates if g.passed),
                "Confluence : " + ", ".join(
                    f"{c.name} {c.value:+.2f}" for c in ev.components if abs(c.value) > 0.01),
            ]),
            data={"symbole": ev.symbol, "sens": ev.side.value, "lots": sizing.lots,
                  "entree": pos.entry_price, "sl": pos.stop_loss, "tp": pos.take_profit,
                  "score": ev.score, "setup": ev.setup},
        )

    # ---------------------------------------------------------------
    # Rythme et supervision
    # ---------------------------------------------------------------
    def _sleep_until_next(self, cycle_start: float) -> None:
        """Cadence adaptative : rapide en position, lente marche ferme."""
        cfg = self.config.engine
        if self.broker.positions():
            target = cfg.poll_seconds
        elif self.universe.tradable():
            target = cfg.idle_poll_seconds
        else:
            target = cfg.closed_market_seconds
        if self._consecutive_errors:
            target = max(target, cfg.error_backoff_seconds * min(self._consecutive_errors, 8))

        elapsed = time.time() - cycle_start
        delay = max(1.0, target - elapsed)
        end = time.time() + delay
        while time.time() < end and not self._stop_requested:
            time.sleep(min(1.0, end - time.time()))

    def _handle_cycle_error(self, exc: Exception) -> None:
        self._consecutive_errors += 1
        self.store.state.errors += 1
        logger.exception("erreur de cycle #%d", self._consecutive_errors)
        if self._consecutive_errors >= self.config.engine.max_consecutive_errors:
            reason = f"{self._consecutive_errors} cycles en echec : {str(exc)[:200]}"
            self.risk.halt(reason)
            self.store.state.halted = True
            self.store.state.halt_reason = reason
            self.notifier.critical("Robot en securite", reason)
        else:
            self.notifier.warning("Cycle en echec", str(exc)[:300],
                                  throttle_key="cycle_error", throttle_seconds=600)

    def _verifier_promotion(self) -> None:
        """Recalibre si la fenetre sans commission s'est ouverte ou fermee.

        C'est le point qui rend l'expiration automatique. Sans lui, un
        robot demarre pendant la promotion garderait le M15 apres sa fin —
        et chaque trade coutrait alors 78 % du risque, sans erreur ni
        alerte. Compter sur quelqu'un pour changer un reglage a une date
        donnee n'est pas une strategie.
        """
        if not getattr(self, "promotion", None) or not self.promotion.active:
            return
        maintenant = self.promotion.en_cours()
        if maintenant == getattr(self, "_promo_en_cours", maintenant):
            return
        logger.warning("changement de regime tarifaire : %s", self.promotion.resume())
        self.notifier.warning("Regime tarifaire modifie", self.promotion.resume())
        self._calibrer_sur_le_capital()

    def _heartbeat(self) -> None:
        """Signe de vie periodique : prouve que le robot tourne vraiment."""
        interval = self.config.engine.heartbeat_minutes * 60
        if interval <= 0 or time.time() - self._last_heartbeat < interval:
            return
        self._last_heartbeat = time.time()
        acc = self.risk.account
        obj = self.objectives.status()
        uptime_h = (time.time() - self.store.state.started_at) / 3600.0
        self.notifier.info(
            "Robot actif",
            "\n".join([
                f"Actif depuis {uptime_h:.1f} h, {self.store.state.cycles} cycles",
                f"Capital {acc.equity:.2f} {acc.currency} "
                f"(jour {acc.daily_pnl_pct():+.2f} %, semaine {acc.weekly_pnl_pct():+.2f} %)",
                f"Positions ouvertes : {len(self.broker.positions())}",
                f"Objectif palier {obj['palier']} : {obj['realise']:+.2f}/{obj['objectif']:.2f}",
                f"Marches ouverts : {', '.join(i.symbol for i in self.universe.tradable()) or 'aucun'}",
            ]),
        )

    def _daily_report(self) -> None:
        """Bilan quotidien envoye une fois par jour."""
        now = datetime.now(timezone.utc)
        day = now.strftime("%Y-%m-%d")
        if now.hour < self.config.engine.daily_report_hour or self._last_report_day == day:
            return
        self._last_report_day = day

        since = time.time() - 86400
        stats = self.journal.stats(since)
        acc = self.risk.account
        obj = self.objectives.status()
        lines = [f"Capital : {acc.equity:.2f} {acc.currency} ({acc.daily_pnl_pct():+.2f} % sur la journee)"]
        if stats.get("trades"):
            lines += [
                f"Trades : {stats['trades']} ({stats['gagnants']} gagnants, "
                f"{stats['taux_reussite_pct']:.0f} % de reussite)",
                f"Resultat net : {stats['profit_net']:+.2f} {acc.currency}",
                f"Esperance : {stats['esperance_R']:+.3f}R par trade",
                f"Facteur de profit : {stats['facteur_profit']}",
                f"Objectifs repousses : {stats['trades_avec_extension']} trade(s), "
                f"{stats['extensions_tp_totales']} extension(s)",
            ]
        else:
            lines.append("Aucun trade aujourd'hui : aucune configuration n'a passe les filtres.")
        lines.append(f"Objectif hebdomadaire : {obj['realise']:+.2f} / {obj['objectif']:.2f} "
                     f"(palier {obj['palier']}, {obj['avancement']:.0%})")
        self.notifier.info(f"Bilan du {day}", "\n".join(lines))

    # ---------------------------------------------------------------
    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            logger.info("signal %s recu : arret propre demande", signum)
            self._stop_requested = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):   # pragma: no cover - hors thread principal
                pass

    def stop(self) -> None:
        self._stop_requested = True

    def shutdown(self) -> None:
        """Arret propre : on sauvegarde tout et on previent.

        Les positions ouvertes ne sont PAS fermees : leur stop-loss est
        deja place cote broker, elles restent protegees. Les fermer
        automatiquement transformerait un redemarrage en perte seche.
        """
        self.store.save()
        self.objectives.save()
        positions = self.broker.positions()
        stats = self.journal.stats(self.store.state.started_at)
        self.notifier.info(
            "Robot arrete",
            "\n".join([
                f"{self.store.state.cycles} cycles, {self.store.state.trades_closed} trades cloture(s)",
                f"Resultat de la session : {stats.get('profit_net', 0):+.2f}",
                f"{len(positions)} position(s) laissee(s) ouverte(s), protegees par leur stop",
            ]),
        )
        self._running = False

    # ---------------------------------------------------------------
    def capital_tier(self) -> dict:
        """Ce que le capital courant permet reellement de trader.

        Le robot n'a pas besoin qu'on lui dise quels instruments prendre : le
        lot minimum et le cout d'execution le decident pour lui. Cette methode
        rend cette decision lisible, et ajuste le nombre de positions
        simultanees a la taille du compte.
        """
        equity = self.risk.account.equity
        cfg = self.config.risk

        # Le nombre de positions tenables ne depend pas de paliers arbitraires
        # mais du ticket d'entree impose par la plateforme : un compte de 60
        # avec un minimum de 5 peut reellement tenir plusieurs lignes, la ou
        # un palier fixe « sous 100 = une seule position » l'en empechait.
        minimum = 5.0
        lire_minimum = getattr(self.broker, "notionnel_minimum", None)
        if callable(lire_minimum):
            try:
                valeur = float(lire_minimum())
                if valeur > 0:
                    minimum = valeur
            except Exception:  # pragma: no cover - la valeur de repli suffit
                logger.debug("notionnel minimum illisible, repli sur %.2f", minimum)

        positions, palier = positions_tenables(
            equity, minimum, cfg.max_capital_engaged_pct, cfg.max_positions)

        if positions != cfg.max_positions:
            logger.info(
                "capital %.2f (%s) : %d position(s) simultanee(s) — ticket minimum %.2f, "
                "%.0f%% engageable",
                equity, palier, positions, minimum, cfg.max_capital_engaged_pct)

        endormis = {sym: motif for sym, (fin, motif) in self.scanner.dormant.items()
                    if fin > time.time()}
        return {
            "palier": palier,
            "capital": round(equity, 2),
            "positions_simultanees": positions,
            "instruments_actifs": [i.symbol for i in self.universe.tradable()
                                   if i.symbol not in endormis],
            "instruments_en_sommeil": endormis,
        }

    def status(self) -> dict:
        """Etat complet du robot (diagnostic, supervision)."""
        acc = self.broker.account()
        return {
            "broker": self.broker.name,
            "mode": getattr(self.broker, "mode", "simulation"),
            "actif": self._running,
            "cycles": self.store.state.cycles,
            "capital": round(acc.equity, 2),
            "devise": acc.currency,
            "positions": len(self.broker.positions()),
            "risque": self.risk.snapshot(),
            "objectif": self.objectives.status(),
            "palier_capital": self.capital_tier(),
            "marches_ouverts": [i.symbol for i in self.universe.tradable()],
            "sources": self.registry.status(),
            "alertes": self.notifier.active_channels(),
        }
