"""Money management : dimensionnement, limites et echelle adaptative.

Regles de fond :
  - le risque se mesure AVANT d'entrer : taille = f(risque accepte, distance au stop) ;
  - aucune position sans stop-loss, jamais ;
  - la taille monte quand le capital monte, et descend quand il descend
    (anti-martingale : on augmente la mise avec les gains, jamais pour se
    refaire) ;
  - des coupe-circuits journaliers et hebdomadaires arretent le robot avant
    que la serie ne devienne structurelle.

L'echelle adaptative demandee est implementee dans `EquityLadder` :
chaque palier de gain augmente le multiplicateur de taille, chaque palier
de perte le reduit, par crans, sans effet de levier cumulatif.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .core import ClosedTrade, Position, Side
from .datasources.base import tf_seconds
from .universe import Instrument

logger = logging.getLogger(__name__)


# DEUX REFUS QUI NE SONT PAS DES PANNES.
#
# Ils se resolvent seuls en quelques secondes et font partie du
# fonctionnement normal : le premier suit CHAQUE cloture de trade
# (`last_trade_ts` vaut `trade.closed_at`), le second signale simplement
# que le compte travaille a plein.
#
# Les annoncer au meme niveau qu'un drawdown ou une limite de perte
# journaliere transforme une trace d'activite en fausse alerte. Le
# 30 aout, onze de ces lignes ont fait croire a un robot bloque toute la
# journee — alors qu'elles prouvaient exactement l'inverse : onze trades
# s'etaient fermes.
DELAI_NON_ECOULE = "delai minimal entre deux trades non ecoule"
PLACES_OCCUPEES = "nombre maximal de positions atteint"


def refus_routinier(motif: str) -> bool:
    """Le refus se resout-il seul, sans que personne ait a intervenir ?"""
    return motif.startswith((DELAI_NON_ECOULE, PLACES_OCCUPEES))


@dataclass(slots=True)
class RiskConfig:
    """Parametres de gestion du risque."""

    # --- Risque par trade ---
    base_risk_pct: float = 0.75        # % du capital risque sur un trade normal
    min_risk_pct: float = 0.20
    max_risk_pct: float = 1.50         # plafond dur, jamais franchi

    # --- Coupe-circuits ---
    daily_loss_limit_pct: float = 4.0
    weekly_loss_limit_pct: float = 8.0
    max_drawdown_pct: float = 20.0     # arret complet du robot
    daily_profit_target_pct: float = 6.0   # au-dela : on protege la journee

    # --- Exposition ---
    max_positions: int = 3
    max_per_correlation_group: int = 1
    max_total_risk_pct: float = 3.0    # somme des risques ouverts
    max_daily_trades: int = 12
    min_seconds_between_trades: float = 45.0
    # Part du capital pouvant etre engagee simultanement. Le reste sert de
    # coussin : sans lui, une position minimale supplementaire est refusee
    # par la plateforme au pire moment, faute de liquidites disponibles.
    max_capital_engaged_pct: float = 80.0
    max_leverage: float = 30.0         # plafond de levier effectif

    # --- Renforcement (pyramidage) ---
    #
    # Ajouter une position sur un actif qui MONTE DEJA, pour que la suite
    # du mouvement porte plus de volume. C'est la demande de l'operateur :
    # « grosse montee, plus d'investissement ».
    #
    # La regle qui rend la chose tenable est `pyramide_locked_r_min`. Une
    # position ne peut etre renforcee que si son stop est DEJA au-dessus
    # de son entree — c'est-a-dire que la premiere ne peut plus perdre.
    # Sans cette condition, empiler trois entrees sur la meme crypto
    # revient a tripler le risque sur un seul actif, et une meche a
    # contre-sens les prend toutes les trois ensemble. Avec elle, le pire
    # cas de la pyramide reste le risque du dernier etage.
    #
    # A zero, rien ne change : c'est le reglage par defaut, et le rejeu
    # doit avoir tranche avant qu'il bouge.
    pyramide_max: int = 0              # etages supplementaires autorises (0 = desarme)
    pyramide_locked_r_min: float = 0.05    # stop de l'etage precedent, en R
    pyramide_fraction_risque: float = 0.6  # chaque etage risque moins que le precedent

    # ESPACEMENT ENTRE ETAGES, en ATR (regle Turtle : « +1 unite tous les
    # 0,5 N »). A zero, aucune distance n'est exigee et deux etages peuvent
    # s'ouvrir sur la meme bougie — ce qui n'est pas du renforcement, c'est
    # une position double payee deux fois en frais.
    pyramide_espacement_atr: float = 0.0

    # --- TAILLE MINIMALE D'UNE POSITION, en devise du compte ---
    #
    # Le 10 septembre l'operateur constate des positions de 5, 8 et 9 EUR
    # sur un compte de 361. Verifie dans le journal : sur 23 trades, le
    # risque REELLEMENT porte vaut 0,30 % du capital en median, pour
    # 0,60 % configures — et descend a 0,04 %.
    #
    # Le mecanisme n'est pas un mauvais reglage, c'est une TRONCATURE.
    # Le dimensionnement part du risque et donne la bonne taille ; puis la
    # part de cash restante la rabote. Quand la caisse est presque vide, le
    # robot n'ouvre pas RIEN — il ouvre une miette. Une miette de 5 EUR qui
    # gagne 10 % rapporte 50 centimes, pour le meme travail et les memes
    # frais qu'une position entiere. Le 9 septembre : KAVA 89 EUR -> +5,56,
    # NEAR 31 EUR -> +2,84, IMX 5 EUR -> -0,50, STRK 8 EUR -> -0,01.
    #
    # Mesure sur 7,5 ans, 70 paires, frais doubles, walk-forward :
    #
    #     plancher      hors echantillon     trades
    #      5 EUR            1 284 EUR          392
    #     20 EUR            1 284 EUR          392   <- arme
    #     50 EUR            1 139 EUR          382
    #
    # A 20 EUR le plancher ne coute RIEN : memes trades, meme resultat. Il
    # ne supprime que les miettes. A 50 EUR il commence a refuser de vraies
    # occasions. NE PAS le monter sans remesurer.
    #
    # Ce plancher REFUSE, il ne rabote pas : mieux vaut attendre qu'une
    # position se ferme et ouvrir entier que d'ouvrir petit tout de suite.
    # Le refus est conjoncturel — le cash revient a chaque cloture.
    ticket_min_eur: float = 0.0        # 0 = seul le minimum plateforme s'applique

    # --- Delai de carence apres une SORTIE, par symbole ---
    #
    # Mesure sur 48 h les 1er-2 septembre : 53 trades, dont DIX entrees
    # successives sur UNIUSD (4,54 -> 4,64 -> 4,80 -> 5,00 -> ... -> 5,49)
    # pour un gain total de 0,64 EUR. Sept sur CRVUSD, six sur FILUSD dont
    # la plus haute a pris la perte pleine (-1,06 R).
    #
    # Le robot refermait une position et rouvrait la MEME crypto quelques
    # minutes plus tard, plus haut, en repayant l'aller-retour a chaque
    # fois. Le chiffre qui tranche : esperance BRUTE +0,135 R (les entrees
    # sont gagnantes sur les prix) contre NETTE -0,105 R. Ce ne sont pas
    # les entrees qui sont mauvaises, c'est la ROTATION qui les mange.
    #
    # CE DELAI NE TOUCHE PAS AU PYRAMIDAGE, ET C'EST LA DISTINCTION QUI
    # COMPTE. Il ne s'applique qu'a un RACHAT apres une sortie — quand
    # plus rien n'est ouvert sur le symbole. Ajouter un etage a une
    # position encore ouverte passe par `peut_renforcer` et n'est jamais
    # concerne : renforcer un gagnant en cours et racheter un actif qu'on
    # vient de quitter sont deux gestes opposes.
    #
    # A zero, rien ne change : le rejeu doit trancher avant.
    cooldown_apres_sortie_minutes: float = 0.0

    # UNE SEULE ENTREE PAR BOUGIE DE SIGNAL, par crypto.
    #
    # Corrige une incoherence, pas un reglage : voir le bloc detaille dans
    # `carence_restante`. Le robot reevalue une bougie journaliere toutes
    # les 10 secondes et prend plusieurs fois le meme signal.
    #
    # N'empeche PAS le pyramidage : renforcer une position ouverte est un
    # autre geste, et `check_exposure` le laisse passer explicitement.
    carence_meme_bougie: bool = False
    unite_du_signal: str = "D1"

    # --- Serie ---
    max_consecutive_losses: int = 4    # au-dela : pause forcee
    pause_after_losses_minutes: float = 90.0

    # --- Qualite minimale ---
    min_rr: float = 1.5                # ratio rendement/risque minimum

    # --- Cout d'execution ---
    #
    # Le rapport entre ce que coute un aller-retour (spread + commission) et
    # ce que le trade risque est LE facteur qui decide de la survie d'un
    # petit compte en trading rapide. Simulation a l'appui : avec un systeme
    # a 55 % de reussite et 1,3 de ratio, 20 trades par jour sur 50 EUR
    # donnent 446 EUR en trois mois quand le cout vaut 17 % du risque, et
    # 15 EUR (compte detruit) quand il en vaut 30 %. Meme systeme, meme
    # nombre de trades : seul le cout change.
    #
    # On refuse donc en amont tout trade dont le cout ronge l'esperance,
    # plutot que de le decouvrir sur le releve de compte.
    max_cost_ratio_pct: float = 15.0   # cout / risque, en %
    commission_per_lot: float = 0.0    # commission fixe eventuelle du broker
    commission_pct: float = 0.0        # commission proportionnelle au notionnel

    # Glissement : ecart entre le prix vu et le prix obtenu, en fraction du
    # spread. Un ordre au marche ne s'execute jamais exactement au prix
    # affiche — il consomme le carnet, et d'autant plus que le marche est
    # nerveux ou l'instrument peu liquide.
    #
    # Compte pour DEUX passages : l'entree et la sortie. Le negliger fait
    # paraitre rentables des trades qui ne le sont pas, et c'est le poste
    # de cout qu'on oublie le plus souvent parce qu'il n'apparait sur
    # aucune facture.
    # Une marge de securite supplementaire serait de la prudence comptee
    # deux fois : `max_cost_ratio_pct` joue deja ce role, et lui est
    # reglable par l'utilisateur.
    slippage_spread_ratio: float = 0.5


@dataclass(slots=True)
class LadderStep:
    """Un cran de l'echelle adaptative."""

    threshold_pct: float    # variation du capital depuis la reference, en %
    multiplier: float       # multiplicateur de taille applique


@dataclass(slots=True)
class EquityLadder:
    """Echelle de taille adossee a la courbe de capital (anti-martingale).

    Exemple par defaut : a +10 % de capital le robot passe a 1.2x, a +25 %
    a 1.45x ; a -8 % il redescend a 0.75x, a -15 % a 0.5x. Les crans sont
    bornes des deux cotes, et la reference se recale sur les nouveaux
    sommets pour ne jamais empiler le risque sur un capital deja rendu.
    """

    steps: list[LadderStep] = field(default_factory=lambda: [
        LadderStep(50.0, 1.80),
        LadderStep(25.0, 1.45),
        LadderStep(10.0, 1.20),
        LadderStep(0.0, 1.00),
        LadderStep(-5.0, 0.85),
        LadderStep(-8.0, 0.75),
        LadderStep(-15.0, 0.50),
        LadderStep(-25.0, 0.35),
    ])
    floor: float = 0.30
    ceiling: float = 2.00

    def multiplier(self, equity: float, reference: float) -> tuple[float, str]:
        """Multiplicateur courant + explication."""
        if reference <= 0:
            return 1.0, "reference de capital inconnue"
        change = (equity - reference) / reference * 100.0
        for step in sorted(self.steps, key=lambda s: -s.threshold_pct):
            if change >= step.threshold_pct:
                mult = max(self.floor, min(self.ceiling, step.multiplier))
                sense = "gains" if change >= 0 else "pertes"
                return mult, f"capital {change:+.1f}% ({sense}) -> taille x{mult:.2f}"
        mult = max(self.floor, self.steps[-1].multiplier)
        return mult, f"capital {change:+.1f}% -> taille x{mult:.2f} (plancher)"


@dataclass(slots=True)
class AccountState:
    """Etat du compte suivi par le robot."""

    equity: float = 0.0
    balance: float = 0.0
    currency: str = "EUR"
    reference_equity: float = 0.0      # base de l'echelle adaptative
    peak_equity: float = 0.0
    day_key: str = ""
    week_key: str = ""
    day_start_equity: float = 0.0
    week_start_equity: float = 0.0
    realized_today: float = 0.0
    realized_this_week: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    last_trade_ts: float = 0.0
    paused_until: float = 0.0
    halted: bool = False
    halt_reason: str = ""

    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100.0)

    def daily_pnl_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return (self.equity - self.day_start_equity) / self.day_start_equity * 100.0

    def weekly_pnl_pct(self) -> float:
        if self.week_start_equity <= 0:
            return 0.0
        return (self.equity - self.week_start_equity) / self.week_start_equity * 100.0


@dataclass(slots=True)
class SizingDecision:
    """Resultat du dimensionnement d'une position."""

    allowed: bool
    lots: float = 0.0
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    stop_distance: float = 0.0
    cost: float = 0.0            # cout estime de l'aller-retour
    cost_ratio_pct: float = 0.0  # ce cout rapporte au risque engage
    reason: str = ""
    factors: list[str] = field(default_factory=list)


class RiskManager:
    """Gardien du capital : autorise, dimensionne et arrete."""

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        ladder: Optional[EquityLadder] = None,
    ) -> None:
        self.config = config or RiskConfig()
        self.ladder = ladder or EquityLadder()
        self.account = AccountState()
        # Derniere SORTIE par symbole, pour le delai de carence. Distinct
        # de `last_trade_ts` qui est global : c'est le rachat du MEME actif
        # qui coute, pas la cadence generale.
        self._derniere_sortie: dict[str, float] = {}

    # ---------------------------------------------------------------
    # Suivi du compte
    # ---------------------------------------------------------------
    # Montant du dernier apport detecte, remis a zero a chaque cycle.
    # L'appelant s'en sert pour recaler ce qui depend du capital de
    # depart : l'echelle le fait ici, l'objectif hebdomadaire non.
    dernier_apport: float = 0.0

    def sync_account(self, equity: float, balance: float, currency: str = "EUR",
                     ts: Optional[float] = None) -> None:
        """Met a jour l'etat du compte et gere les changements de periode."""
        acc = self.account
        now = ts or time.time()
        dt = datetime.fromtimestamp(now, tz=timezone.utc)
        day = dt.strftime("%Y-%m-%d")
        year, week, _ = dt.isocalendar()
        wk = f"{year}-W{week:02d}"

        # UN APPORT N'EST PAS UNE PERFORMANCE.
        #
        # Observe le 2 septembre : un depot de ~69 EUR a porte le compte de
        # 90 a 158 EUR. L'echelle de capital (anti-martingale) y a lu +63 %
        # de gain, est montee au cran x1,80, et le risque par trade est
        # passe de 0,41 % a 1,08 % — au-dessus du palier « preuve » (0,6 %)
        # que le plan de croissance impose tant que l'avantage n'est pas
        # etabli. La perte suivante a coute 2,28 EUR la ou les precedentes
        # coutaient 0,30 a 0,71 EUR : meme strategie, position trois fois
        # plus grosse.
        #
        # L'echelle ne peut pas distinguer un virement d'une serie de gains
        # : les deux font monter la courbe. On la lui apprend ici — un saut
        # que les trades fermes n'expliquent pas est un mouvement de
        # tresorerie, et la reference le suit au lieu de le recompenser.
        #
        # UNIQUEMENT LES SAUTS VERS LE HAUT, et l'asymetrie est deliberee.
        #
        # Un bond que les trades n'expliquent pas est presque toujours un
        # depot. Une CHUTE que les trades n'expliquent pas, elle, peut etre
        # un retrait — ou une grosse perte. Traiter une perte comme un
        # retrait recalerait la reference vers le bas et **desarmerait le
        # coupe-circuit de drawdown** au pire moment. Les deux erreurs ne
        # coutent pas la meme chose : se tromper sur un depot donne des
        # positions un peu trop petites, se tromper sur une perte retire le
        # filet. On ne corrige donc que le sens dangereux.
        #
        # `peak_equity` n'est pas touche : il remonte tout seul par le
        # `max()` juste apres, et le baisser aurait le meme effet que
        # ci-dessus.
        #
        # Seuil volontairement large (5 % du capital ET 3x le realise du
        # jour) : on recale sur un apport franc, pas sur un gros gagnant.
        self.dernier_apport = 0.0
        precedent = acc.equity
        if precedent > 0 and acc.reference_equity > 0:
            saut = equity - precedent
            explique = abs(acc.realized_today) * 3.0 + 0.02 * precedent
            if saut > max(explique, 0.05 * precedent):
                acc.reference_equity += saut
                # Memorise pour l'appelant : l'objectif hebdomadaire doit
                # etre recale lui aussi, sinon il reste calcule sur le
                # capital d'AVANT le virement. Le 9 septembre 2026, un
                # objectif de 4,47 EUR (4 % de 111 EUR) a ete « largement
                # depasse » avec 8,40 EUR alors que le compte valait deja
                # 366 EUR — et le robot s'est arrete pour la semaine.
                self.dernier_apport = saut
                logger.warning(
                    "apport detecte : +%.2f %s que les trades n'expliquent "
                    "pas. Reference %.2f -> %.2f : l'echelle de capital ne "
                    "prend PAS ce saut pour un gain.",
                    saut, currency, acc.reference_equity - saut,
                    acc.reference_equity)

        acc.equity, acc.balance, acc.currency = equity, balance, currency
        if acc.reference_equity <= 0:
            acc.reference_equity = equity
        if acc.peak_equity <= 0:
            acc.peak_equity = equity
        acc.peak_equity = max(acc.peak_equity, equity)

        if acc.day_key != day:
            acc.day_key = day
            acc.day_start_equity = equity
            acc.realized_today = 0.0
            acc.trades_today = 0
            logger.info("nouvelle journee %s : capital de depart %.2f %s", day, equity, currency)
        if acc.week_key != wk:
            acc.week_key = wk
            acc.week_start_equity = equity
            acc.realized_this_week = 0.0
            # La reference de l'echelle se recale chaque semaine sur le
            # sommet atteint : on ne re-risque pas un capital deja rendu.
            acc.reference_equity = max(acc.reference_equity, min(equity, acc.peak_equity))

    def absorber_retrait(self, montant: float) -> None:
        """Descend la reference d'un retrait CONFIRME par la plateforme.

        POURQUOI CETTE METHODE EXISTE, ET POURQUOI ELLE EST SEPAREE.

        `sync_account` ne corrige QUE les sauts vers le haut, et son
        commentaire dit pourquoi : une chute inexpliquee peut etre un
        retrait comme une grosse perte, et prendre une perte pour un
        retrait desarmerait le coupe-circuit de drawdown au pire moment.
        Ce raisonnement est juste — il lui manquait une troisieme option :
        DEMANDER A LA PLATEFORME. Un retrait est un fait verifiable, pas
        une deduction sur la forme de la courbe.

        Ce que ca coutait, mesure le 10 septembre 2026 :

            reference du gestionnaire de risque   429,45 EUR
            reference du chien de garde           370,61 EUR  (sommet reel)
            retrait du 7 septembre                 61,00 EUR
            429,45 - 61,00 = 368,45  ~=  370,61

        La reference etait restee au sommet d'AVANT le retrait. Le robot
        lisait donc -16,4 % de capital, appliquait le cran « -15 % » de
        l'echelle anti-martingale, et divisait chaque position par trois :
        risque 0,25 % au lieu de 0,60 %, positions de 9 EUR au lieu de 21.
        Il se protegeait d'une perte qui n'avait jamais eu lieu.

        C'est la TROISIEME fois que ce piege sort dans ce depot — apres
        l'objectif hebdomadaire et le chien de garde. La regle generale :
        tout ce qui se calcule sur un capital de reference doit absorber
        les mouvements de tresorerie, dans LES DEUX SENS.

        `peak_equity` descend aussi, et c'est volontaire ici : l'argent est
        parti, ce n'est pas une perte. Le laisser en haut ferait declencher
        le coupe-circuit de drawdown sur un virement — exactement ce qui
        est arrive au chien de garde le 4 septembre.
        """
        montant = max(0.0, float(montant))
        if montant <= 0:
            return
        acc = self.account
        avant_ref, avant_pic = acc.reference_equity, acc.peak_equity
        acc.reference_equity = max(0.0, acc.reference_equity - montant)
        acc.peak_equity = max(acc.equity, acc.peak_equity - montant)
        logger.warning(
            "retrait CONFIRME de %.2f %s : reference %.2f -> %.2f, "
            "sommet %.2f -> %.2f. Ce n'est pas une perte, l'echelle de "
            "capital ne doit pas reduire les positions.",
            montant, acc.currency, avant_ref, acc.reference_equity,
            avant_pic, acc.peak_equity)

    def record_close(self, trade: ClosedTrade) -> None:
        """Enregistre un trade cloture (statistiques et coupe-circuits)."""
        acc = self.account
        acc.realized_today += trade.profit
        acc.realized_this_week += trade.profit
        acc.trades_today += 1
        acc.last_trade_ts = trade.closed_at
        self._derniere_sortie[trade.symbol] = trade.closed_at
        if trade.profit < 0:
            acc.consecutive_losses += 1
            acc.consecutive_wins = 0
            if acc.consecutive_losses >= self.config.max_consecutive_losses:
                acc.paused_until = time.time() + self.config.pause_after_losses_minutes * 60
                logger.warning("%d pertes consecutives : pause de %.0f min",
                               acc.consecutive_losses, self.config.pause_after_losses_minutes)
        else:
            acc.consecutive_wins += 1
            acc.consecutive_losses = 0

    # ---------------------------------------------------------------
    # Autorisations
    # ---------------------------------------------------------------
    def can_trade(self, open_positions: Optional[list[Position]] = None,
                  ts: Optional[float] = None) -> tuple[bool, str]:
        """Le robot a-t-il le droit d'ouvrir une position maintenant ?"""
        acc, cfg = self.account, self.config
        now = ts or time.time()
        positions = open_positions or []

        if acc.halted:
            return False, f"robot arrete : {acc.halt_reason}"
        if acc.equity <= 0:
            return False, "capital inconnu ou nul"
        if acc.drawdown_pct() >= cfg.max_drawdown_pct:
            acc.halted = True
            acc.halt_reason = f"drawdown maximal atteint ({acc.drawdown_pct():.1f}%)"
            return False, acc.halt_reason
        if now < acc.paused_until:
            return False, f"pause apres pertes ({(acc.paused_until - now) / 60:.0f} min restantes)"
        if acc.paused_until and acc.consecutive_losses >= cfg.max_consecutive_losses:
            # La pause a ete purgee : elle etait la sanction, elle est
            # payee. Sans cette remise a zero, chaque perte suivante
            # redeclenche la pause et le robot ne sort plus jamais du
            # regime punitif — mesure sur ADA, 1044 bougies bloquees sur
            # 1439, soit 73 % de la periode.
            logger.info("pause purgee : compteur de pertes consecutives remis a zero")
            acc.consecutive_losses = 0
            acc.paused_until = 0.0
        if acc.daily_pnl_pct() <= -cfg.daily_loss_limit_pct:
            return False, f"limite de perte journaliere atteinte ({acc.daily_pnl_pct():.2f}%)"
        if acc.weekly_pnl_pct() <= -cfg.weekly_loss_limit_pct:
            return False, f"limite de perte hebdomadaire atteinte ({acc.weekly_pnl_pct():.2f}%)"
        if cfg.daily_profit_target_pct > 0 and acc.daily_pnl_pct() >= cfg.daily_profit_target_pct:
            return False, f"objectif journalier atteint ({acc.daily_pnl_pct():+.2f}%) : journee protegee"
        # 0 ou moins = aucun plafond. Sans ce test, `trades_today >= 0` est vrai
        # des le premier cycle et un plafond mis a zero pour « liberer » le
        # robot le bloquerait au contraire entierement — c'est l'inverse de
        # l'intention. Meme convention que daily_profit_target_pct ci-dessus.
        if cfg.max_daily_trades > 0 and acc.trades_today >= cfg.max_daily_trades:
            return False, f"quota de trades du jour atteint ({acc.trades_today})"
        if len(positions) >= cfg.max_positions:
            return False, f"{PLACES_OCCUPEES} ({len(positions)})"
        if now - acc.last_trade_ts < cfg.min_seconds_between_trades:
            return False, DELAI_NON_ECOULE
        return True, ""

    def carence_restante(self, symbol: str, now: Optional[float] = None) -> float:
        """Minutes restantes avant de pouvoir RACHETER ce symbole.

        `now` est explicite pour que le rejeu, qui avance sur l'horloge des
        bougies et non sur celle du systeme, mesure la meme chose que le
        robot. Sans ce parametre le delai ne s'appliquait jamais en rejeu —
        et le banc d'essai aurait rendu un resultat identique au temoin,
        exactement le piege decrit pour la pyramide.
        """
        cfg = self.config
        sortie = self._derniere_sortie.get(symbol)

        # UN SIGNAL JOURNALIER NE SE PREND QU'UNE FOIS PAR JOUR.
        #
        # LE DEFAUT, trouve le 12 septembre 2026 en regardant MTL. La
        # strategie est journaliere : elle a UN signal par jour et par
        # crypto, la cassure du plus-haut de 20 jours. Mais le robot
        # reevalue la bougie du jour toutes les 10 secondes — et tant
        # qu'elle n'est pas close, le prix repasse au-dessus du canal
        # plusieurs fois. Il prend donc trois fois le meme signal.
        #
        #     MTL    01h30 · 05h26 · 14h49 · 15h56   le meme jour
        #     BLUR   15h06 · 15h16 · 16h12
        #     SAGA   20h26 · 21h10 · 21h38
        #
        # Mesure sur les 51 trades de l'ere D1 : 14 entrees en trop, soit
        # 27 % des trades, pour +1,51 EUR de gain brut et 1,54 EUR de
        # frais — exactement rien, en payant le peage trois fois.
        #
        # POURQUOI AUCUNE MESURE NE L'AVAIT VU. Le banc d'essai avance en
        # bougies journalieres : une bougie, une decision. Il ne PEUT pas
        # reproduire ce defaut. Les delais de carence que j'y ai mesures
        # refusaient donc de vraies entrees du LENDEMAIN — autre chose, et
        # defavorable a juste titre. C'est la cinquieme fois que ce depot
        # rencontre l'ecart entre ce qu'on mesure et ce qui tourne.
        #
        # Ce n'est donc pas un reglage a optimiser : c'est une incoherence
        # a supprimer. On aligne le robot sur son unite de temps.
        if cfg.carence_meme_bougie and sortie:
            secondes = tf_seconds(cfg.unite_du_signal)
            if secondes > 0:
                maintenant = now or time.time()
                if int(sortie // secondes) == int(maintenant // secondes):
                    fin = (int(maintenant // secondes) + 1) * secondes
                    return max(0.0, (fin - maintenant) / 60.0)

        if cfg.cooldown_apres_sortie_minutes <= 0:
            return 0.0
        if not sortie:
            return 0.0
        ecoule = ((now or time.time()) - sortie) / 60.0
        return max(0.0, cfg.cooldown_apres_sortie_minutes - ecoule)

    def check_exposure(self, instrument: Instrument, side: Side,
                       open_positions: list[Position],
                       universe_lookup,
                       now: Optional[float] = None) -> tuple[bool, str]:
        """Verifie les regles d'exposition et de correlation.

        Empiler trois achats correles (or + argent + AUD par exemple)
        revient a tripler la meme position sans le savoir.
        """
        cfg = self.config
        same_group = 0
        sur_le_meme = [p for p in open_positions if p.symbol == instrument.symbol]
        if sur_le_meme:
            # Position encore ouverte : c'est une decision de PYRAMIDE.
            # Le delai de carence ne s'applique pas ici — renforcer un
            # gagnant en cours n'est pas racheter ce qu'on vient de quitter.
            # PRE-FILTRE, PAS PORTE. `check_exposure` tourne dans la phase
            # de selection du scanner, avant tout chargement de donnees :
            # ni prix ni ATR n'existent encore. On verifie donc ce qui ne
            # depend pas d'eux (armement, nombre d'etages, sens) et on
            # laisse l'espacement a `_execute`, seul endroit ou le prix et
            # l'ATR de l'evaluation sont connus.
            #
            # Sans ce partage explicite, l'espacement serait « verifie »
            # ici avec des zeros — c'est-a-dire pas verifie du tout.
            ok, why = self.peut_renforcer(sur_le_meme, side,
                                          verifier_espacement=False)
            if not ok:
                return False, why
        else:
            # Rien d'ouvert sur ce symbole : c'est un RACHAT. C'est celui-la
            # qui a produit dix entrees sur UNIUSD en 48 h.
            reste = self.carence_restante(instrument.symbol, now)
            if reste > 0:
                return False, (
                    f"rachat de {instrument.symbol} trop tot : encore "
                    f"{reste:.0f} min de carence sur "
                    f"{cfg.cooldown_apres_sortie_minutes:.0f}")
        for pos in open_positions:
            if pos.symbol == instrument.symbol:
                continue
            other = universe_lookup(pos.symbol)
            if other and instrument.correlation_group and other.correlation_group == instrument.correlation_group:
                same_group += 1
        if instrument.correlation_group and same_group >= cfg.max_per_correlation_group:
            return False, f"exposition deja prise sur le groupe correle '{instrument.correlation_group}'"
        return True, ""

    def peut_renforcer(self, sur_le_meme: list[Position],
                       side: Side, prix: float = 0.0,
                       atr: float = 0.0,
                       verifier_espacement: bool = True) -> tuple[bool, str]:
        """Un etage de plus est-il permis sur un actif deja detenu ?

        Trois conditions, et chacune ferme une porte differente :

        1. le renforcement est arme (`pyramide_max` > 0) ;
        2. le nombre d'etages n'est pas atteint ;
        3. TOUS les etages ouverts ont deja leur stop au-dessus de leur
           entree.

        La troisieme est la seule qui protege vraiment. Elle transforme
        « trois fois le risque sur une crypto » en « le risque du dernier
        etage, les precedents ne pouvant plus perdre ». Sans elle, un
        retournement brutal — ce qui arrive precisement apres une grosse
        montee — encaisse toutes les pertes d'un coup.

        Elle impose aussi le bon SENS de la pyramide : on ne renforce que
        ce qui gagne. Renforcer une position perdante est une moyenne a la
        baisse, exactement l'inverse de ce qui est demande ici.
        """
        cfg = self.config
        if cfg.pyramide_max <= 0:
            return False, f"position deja ouverte sur {sur_le_meme[0].symbol}"
        # On compte les ETAGES, pas les lignes. Au comptant, Bitvavo ne
        # connait qu'un avoir par actif : les trois unites d'une pyramide
        # vivent dans UNE position dont le volume a grossi. Compter les
        # positions y rendrait toujours 1, et le plafond ne serait jamais
        # atteint.
        deja = sum(getattr(p, "etages", 1) for p in sur_le_meme)
        if deja > cfg.pyramide_max:
            return False, (f"{deja} etage(s) deja sur "
                           f"{sur_le_meme[0].symbol}, maximum {cfg.pyramide_max}")
        # Un renforcement a contre-sens serait une couverture, pas une
        # pyramide : les deux positions s'annuleraient en payant deux fois
        # les frais.
        if any(p.side is not side for p in sur_le_meme):
            return False, f"position de sens oppose ouverte sur {sur_le_meme[0].symbol}"
        # Espacement Turtle : le prix doit avoir avance d'au moins
        # `pyramide_espacement_atr` ATR depuis le DERNIER etage ouvert.
        #
        # CE CONTROLE ECHOUE FERME, ET C'EST TOUTE LA CORRECTION DU
        # 6 SEPTEMBRE 2026. Il s'ecrivait avant :
        #
        #     if cfg.pyramide_espacement_atr > 0 and prix > 0 and atr > 0:
        #
        # Les deux appelants du moteur reel n'ayant jamais passe `prix` ni
        # `atr` (ils tournent AVANT le chargement des donnees), la
        # condition etait toujours fausse et le controle ne s'executait
        # JAMAIS. Le rejeu, lui, les passait — il mesurait donc une regle
        # que le robot n'appliquait pas. Resultat en argent reel : deux
        # etages sur LINKUSD en 39 secondes, a 0,013 ATR d'ecart pour
        # 0,5 exige.
        #
        # Un garde-fou qui ne peut pas verifier doit REFUSER, jamais
        # laisser passer. L'appelant qui n'a pas encore le prix le dit
        # explicitement avec `verifier_espacement=False` — et celui-la
        # n'est plus une porte, seulement un pre-filtre.
        if verifier_espacement and cfg.pyramide_espacement_atr > 0:
            if prix <= 0 or atr <= 0:
                return False, (
                    f"espacement de pyramide invérifiable sur "
                    f"{sur_le_meme[0].symbol} (prix ou ATR absent) : "
                    "renforcement refuse par prudence")
            dernier = max(sur_le_meme, key=lambda p: p.opened_at)
            # `prix_dernier_etage`, pas `entry_price` : apres une fusion
            # l'entree est une MOYENNE PONDEREE, qui recule a chaque ajout.
            # Mesurer l'avance depuis elle laisserait empiler deux etages
            # sur le meme mouvement.
            reference = getattr(dernier, "prix_dernier_etage", dernier.entry_price)
            avance = side.sign * (prix - reference)
            exige = cfg.pyramide_espacement_atr * atr
            if avance < exige:
                return False, (
                    f"renforcement trop proche sur {dernier.symbol} : "
                    f"{avance / atr:+.2f} ATR depuis le dernier etage, "
                    f"{cfg.pyramide_espacement_atr:.2f} exiges")

        retard = [p for p in sur_le_meme if p.locked_r() < cfg.pyramide_locked_r_min]
        if retard:
            return False, (f"renforcement refuse sur {sur_le_meme[0].symbol} : "
                           f"un etage n'a que {min(p.locked_r() for p in retard):+.2f}R "
                           f"verrouille pour {cfg.pyramide_locked_r_min:+.2f}R exiges")
        return True, ""

    def open_risk_pct(self, open_positions: list[Position],
                      universe_lookup) -> float:
        """Risque total encore en jeu sur les positions ouvertes, en % du capital."""
        acc = self.account
        if acc.equity <= 0:
            return 0.0
        total = 0.0
        for pos in open_positions:
            inst = universe_lookup(pos.symbol)
            if not inst:
                continue
            # Si le stop est deja en profit, le risque est nul.
            risk_price = max(0.0, pos.side.sign * (pos.entry_price - pos.stop_loss))
            total += risk_price * inst.value_per_price_unit(pos.volume)
        return total / acc.equity * 100.0

    # ---------------------------------------------------------------
    # Dimensionnement
    # ---------------------------------------------------------------
    def effective_risk_pct(self, extra_multiplier: float = 1.0) -> tuple[float, list[str]]:
        """Risque par trade apres application de tous les multiplicateurs."""
        acc, cfg = self.account, self.config
        factors: list[str] = []

        risk = cfg.base_risk_pct
        factors.append(f"base {risk:.2f}%")

        ladder_mult, ladder_why = self.ladder.multiplier(acc.equity, acc.reference_equity)
        risk *= ladder_mult
        factors.append(ladder_why)

        if extra_multiplier != 1.0:
            risk *= extra_multiplier
            factors.append(f"modulation objectif x{extra_multiplier:.2f}")

        # Serie de pertes : on reduit progressivement avant meme la pause.
        if acc.consecutive_losses >= 2:
            shrink = max(0.5, 1.0 - 0.15 * acc.consecutive_losses)
            risk *= shrink
            factors.append(f"{acc.consecutive_losses} pertes d'affilee x{shrink:.2f}")

        # Drawdown courant : reduction continue supplementaire.
        dd = acc.drawdown_pct()
        if dd > 5.0:
            shrink = max(0.5, 1.0 - (dd - 5.0) / 30.0)
            risk *= shrink
            factors.append(f"drawdown {dd:.1f}% x{shrink:.2f}")

        risk = max(cfg.min_risk_pct, min(cfg.max_risk_pct, risk))
        factors.append(f"retenu {risk:.2f}% (plafond dur {cfg.max_risk_pct:.2f}%)")
        return risk, factors

    def size_position(
        self,
        instrument: Instrument,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        open_positions: Optional[list[Position]] = None,
        universe_lookup=None,
        extra_multiplier: float = 1.0,
        spread: float = 0.0,
        available_cash: Optional[float] = None,
        places_visees: Optional[int] = None,
    ) -> SizingDecision:
        """Calcule le volume a engager. Refuse si une regle est violee."""
        acc, cfg = self.account, self.config
        positions = open_positions or []
        lookup = universe_lookup or (lambda _s: None)

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return SizingDecision(False, reason="stop-loss invalide (distance nulle)")
        # Tolerance sur la comparaison : un objectif place exactement au ratio
        # minimal ne doit pas etre refuse a cause d'un arrondi binaire.
        rr = abs(take_profit - entry_price) / stop_distance if take_profit else 0.0
        if take_profit and rr < cfg.min_rr - 1e-9:
            return SizingDecision(False, reason=f"ratio rendement/risque insuffisant ({rr:.2f} < {cfg.min_rr})")

        risk_pct, factors = self.effective_risk_pct(extra_multiplier)

        # CHAQUE ETAGE DE PYRAMIDE RISQUE MOINS QUE LE PRECEDENT.
        #
        # Sans decroissance, un renforcement double le risque sur le meme
        # actif ; a trois etages il le triple. La condition d'entree exige
        # deja que les etages precedents ne puissent plus perdre, donc le
        # pire cas reste borne — mais la CONCENTRATION, elle, ne l'est pas :
        # a 96 EUR de capital, deux etages pleins mettent tout le compte
        # sur une seule crypto. La decroissance geometrique garde le poids
        # du sommet de la pyramide raisonnable.
        etages = sum(1 for p in positions if p.symbol == instrument.symbol)
        if etages and cfg.pyramide_max > 0:
            attenuation = cfg.pyramide_fraction_risque ** etages
            risk_pct *= attenuation
            factors.append(f"etage {etages + 1} de la pyramide (x{attenuation:.2f})")

        # Le risque deja engage plafonne le risque du nouveau trade.
        already = self.open_risk_pct(positions, lookup)
        room = cfg.max_total_risk_pct - already
        if room <= 0.05:
            return SizingDecision(False, reason=f"risque total deja engage ({already:.2f}%)")
        if risk_pct > room:
            risk_pct = room
            factors.append(f"limite par le risque total restant ({room:.2f}%)")

        risk_amount = acc.equity * risk_pct / 100.0
        value_per_unit = instrument.value_per_price_unit(1.0)   # pour 1 lot
        if value_per_unit <= 0:
            return SizingDecision(False, reason="taille de contrat invalide")

        raw_lots = risk_amount / (stop_distance * value_per_unit)

        # Argent reellement disponible. Au comptant, le capital total inclut
        # ce qui est deja investi : on ne peut pas acheter avec. Sans cette
        # limite, le robot proposerait des ordres que la plateforme refuserait
        # a chaque cycle, faute de liquidites.
        if available_cash is not None and available_cash >= 0:
            valeur_unitaire = entry_price * instrument.contract_size
            if valeur_unitaire > 0:
                # Le cash n'est pas reserve au premier arrive. Le moteur
                # multi-entrees peut ouvrir plusieurs places dans le meme
                # cycle : si le premier ordre consomme tout le solde, les
                # suivants sont refuses faute de liquidites, et le robot se
                # retrouve avec UNE position la ou la configuration en
                # autorise douze. On repartit donc le solde entre les places
                # encore libres.
                #
                # La part est bornee par le plafond d'engagement, et ce qui
                # est deja investi en est deduit : sans cela le coussin de
                # securite disparaitrait des la deuxieme position.
                # Le plafond d'engagement borne ce qu'on peut ENGAGER, donc
                # il se calcule sur le pouvoir d'achat, pas sur le capital.
                # Au comptant les deux se confondent (max_leverage = 1).
                levier = max(1.0, cfg.max_leverage)
                plafond_engage = (acc.equity * levier
                                  * cfg.max_capital_engaged_pct / 100.0)
                deja_engage = 0.0
                for pos in positions:
                    inst = lookup(pos.symbol)
                    if inst:
                        deja_engage += abs(pos.entry_price * inst.contract_size * pos.volume)
                # AU COMPTANT, LE CASH SE PARTAGE ENTRE LES PLACES.
                #
                # On achete des cryptos : chaque euro engage sort du solde.
                # Servir la premiere position a la taille voulue par le
                # risque la laisserait consommer la moitie du budget, et le
                # compte tiendrait deux lignes la ou il peut en tenir six.
                #
                # Or six positions de 14,40 EUR risquent EXACTEMENT autant
                # que deux de 43 EUR : le risque total vaut le notionnel
                # total multiplie par la distance au stop, et le notionnel
                # total est le budget dans les deux cas. Meme risque, meme
                # esperance — l'esperance en R est normalisee par le risque —
                # mais six instruments au lieu de deux, donc moins de
                # variance et plus de trades.
                #
                # Le plancher, lui, n'est pas negociable : une part sous le
                # ticket minimum de la plateforme ne produit aucun ordre.
                # Mieux vaut alors moins de places, plus grandes.
                # ON NE RESERVE PAS DE CASH POUR DES PLACES QUI N'EXISTENT PAS.
                #
                # Le partage divisait par TOUTES les places libres, donc
                # par six, en pariant que six occasions se presenteraient.
                # Le 30 aout il y en a eu DEUX de toute la journee : quatre
                # sixiemes du compte — environ 55 EUR — ont dormi jusqu'au
                # soir pour des places qui ne se sont jamais ouvertes, et
                # les deux positions prises ont porte 0,25 % de risque au
                # lieu des 0,60 % configures.
                #
                # `places_visees` est le nombre d'occasions que l'appelant
                # a REELLEMENT sous la main. A defaut on retombe sur
                # l'ancien comportement : une couche qui ne sait pas
                # compter ses occasions ne doit pas concentrer par
                # accident.
                #
                # Le budget de risque (`max_total_risk_pct`) reste la borne
                # dure au-dessus : diviser par moins ne peut pas faire
                # depasser le risque total, il rend seulement au capital le
                # droit de travailler quand les occasions sont rares.
                reste = min(available_cash, max(0.0, plafond_engage - deja_engage))
                # Le diviseur ne peut pas venir du SEUL compteur de places :
                # `max_positions` porte a 99 le ferait diviser le cash en 99
                # parts de 0,88 EUR, toutes sous le ticket minimum — le
                # robot refuserait alors chaque trade en croyant partager.
                #
                # La vraie borne est le budget de risque : a 0,60 % par
                # trade et 3,5 % au total, le compte ne peut de toute facon
                # pas tenir plus de 5 lignes. C'est LUI qui limite, mesure
                # a l'appui (5 lignes 35 % du temps, 6 seulement 2 %), donc
                # c'est lui qui doit decider du partage.
                par_le_budget = (int(cfg.max_total_risk_pct // cfg.base_risk_pct)
                                 if cfg.base_risk_pct > 0 else cfg.max_positions)
                plafond_places = min(cfg.max_positions, max(1, par_le_budget))
                libres = max(1, plafond_places - len(positions))
                places = libres if places_visees is None else max(
                    1, min(libres, int(places_visees)))
                # Deux planchers, et on prend le plus haut : celui de la
                # plateforme (un ordre plus petit est rejete) et celui de
                # l'operateur (une position plus petite ne rapporte rien).
                ticket_minimum = max(instrument.min_lot * valeur_unitaire,
                                     cfg.ticket_min_eur)
                part = min(reste, max(reste / places, ticket_minimum))

                max_lots_cash = part / valeur_unitaire
                if max_lots_cash < instrument.min_lot:
                    # Refus CONJONCTUREL, pas structurel : une cloture au
                    # prochain cycle libere le cash. Le libelle evite donc
                    # les mots qui mettent l'instrument en sommeil une heure
                    # (voir `_execute` dans engine.py).
                    return SizingDecision(
                        False,
                        reason=(f"budget de place insuffisant sur {instrument.symbol} : "
                                f"{part:.2f} {acc.currency} disponibles, il en "
                                f"faut {ticket_minimum:.2f}"),
                        factors=factors,
                    )
                if raw_lots > max_lots_cash:
                    raw_lots = max_lots_cash
                    factors.append(f"part de cash : {part:.2f} {acc.currency} "
                                   f"({places} place(s) libre(s) sur "
                                   f"{reste:.2f} disponibles)")

        # Plafond de levier : la valeur notionnelle ne doit pas exploser.
        max_lots_leverage = None
        if cfg.max_leverage > 0:
            max_notional = acc.equity * cfg.max_leverage
            max_lots_leverage = max_notional / (entry_price * instrument.contract_size)
            if raw_lots > max_lots_leverage:
                raw_lots = max_lots_leverage
                factors.append(f"limite par le levier max ({cfg.max_leverage:.0f}x)")

        # Arrondi vers le bas : depasser le risque vise a cause d'un arrondi
        # serait une erreur silencieuse, repetee a chaque trade.
        lots = instrument.normalize_lot(raw_lots, round_down=True)

        # L'arrondi peut ramener au lot minimum, qui peut lui-meme depasser
        # le plafond de levier : on verifie apres normalisation.
        if max_lots_leverage is not None and lots > max_lots_leverage:
            if cfg.max_leverage <= 1.0:
                # Sans levier (le comptant), la contrainte n'est pas un plafond
                # de risque mais l'argent disponible : on ne peut pas acheter
                # plus cher que ce qu'on possede. Le message doit le dire.
                besoin = instrument.min_lot * entry_price * instrument.contract_size
                return SizingDecision(
                    False,
                    reason=(f"capital insuffisant pour acheter le minimum sur "
                            f"{instrument.symbol} : il faudrait {besoin:.2f} "
                            f"{acc.currency} pour {acc.equity:.2f} disponible"),
                    factors=factors,
                )
            return SizingDecision(
                False,
                reason=(f"le lot minimum ({instrument.min_lot}) depasse le levier autorise "
                        f"({cfg.max_leverage:.0f}x) sur {instrument.symbol}"),
                factors=factors,
            )
        if lots < instrument.min_lot or lots <= 0:
            return SizingDecision(
                False,
                reason=(f"capital insuffisant pour le lot minimum sur {instrument.symbol} "
                        f"(il faudrait {instrument.min_lot} lot, soit "
                        f"{stop_distance * value_per_unit * instrument.min_lot:.2f} {acc.currency} de risque "
                        f"pour {risk_amount:.2f} disponible)"),
                factors=factors,
            )

        # PLANCHER DE TAILLE (voir `ticket_min_eur`). On le verifie ICI,
        # apres tous les plafonds et l'arrondi : c'est le seul endroit ou
        # la taille FINALE est connue. Le mettre plus haut laisserait
        # passer une position rabotee ensuite par le cash ou le levier.
        #
        # C'est un REFUS, pas un rabotage vers le haut : ouvrir plus gros
        # que le risque ne le permet serait exactement l'erreur inverse.
        #
        # L'ARRONDI NE DOIT PAS DECLENCHER LE REFUS. `normalize_lot` arrondit
        # vers le BAS — toujours, pour ne jamais depasser le risque vise. Une
        # part de cash de 20,00 EUR redescend donc a 19,98 apres arrondi, et
        # comparer sechement au plancher refuserait une position qui le
        # respecte. La marge vaut exactement un pas de lot : c'est le maximum
        # que l'arrondi peut retirer, ni plus ni moins.
        notionnel = lots * entry_price * instrument.contract_size
        un_pas = instrument.lot_step * entry_price * instrument.contract_size
        if cfg.ticket_min_eur > 0 and notionnel < cfg.ticket_min_eur - un_pas:
            # LE MOTIF DIT CE QUI A LIMITE, PAS SEULEMENT QU'IL A LIMITE.
            #
            # Sans les facteurs, ce message ne dit que le resultat. Le
            # 10 septembre 2026 il a coute une heure : le robot refusait a
            # 8,87 EUR pendant qu'un diagnostic hors-ligne, meme
            # configuration et memes positions, en calculait 21,33 —
            # impossible de savoir laquelle des cinq bornes mordait.
            # Une borne qui refuse doit dire son nom.
            detail = " | ".join(factors[-3:]) if factors else "aucun facteur"
            return SizingDecision(
                False,
                # Libelle CONJONCTUREL : une cloture libere du cash et la
                # meme crypto redevient prenable au cycle suivant. Voir le
                # tri des motifs dans `_execute` (engine.py).
                reason=(f"budget de place insuffisant sur {instrument.symbol} : "
                        f"{notionnel:.2f} {acc.currency} possibles, plancher "
                        f"a {cfg.ticket_min_eur:.2f} — limite par : {detail}"),
                factors=factors,
            )

        # Le lot normalise peut depasser legerement le risque vise : on verifie.
        real_risk = lots * stop_distance * value_per_unit
        real_pct = real_risk / acc.equity * 100.0 if acc.equity else 0.0
        if real_pct > cfg.max_risk_pct * 1.15:
            return SizingDecision(
                False,
                reason=(f"le lot minimum represente {real_pct:.2f}% de risque, "
                        f"au-dessus du plafond {cfg.max_risk_pct:.2f}%"),
                factors=factors,
            )

        # Cout de l'aller-retour : on paie le spread a l'ouverture et a la
        # fermeture, plus l'eventuelle commission du broker.
        cost = self.execution_cost(instrument, lots, entry_price, spread)
        cost_ratio = cost / real_risk * 100.0 if real_risk > 0 else 100.0
        if cfg.max_cost_ratio_pct > 0 and cost_ratio > cfg.max_cost_ratio_pct:
            return SizingDecision(
                False,
                lots=lots,
                cost=round(cost, 4),
                cost_ratio_pct=round(cost_ratio, 1),
                stop_distance=stop_distance,
                reason=(f"cout d'execution trop lourd sur {instrument.symbol} : "
                        f"{cost:.3f} {acc.currency} pour {real_risk:.2f} de risque "
                        f"({cost_ratio:.0f} % du risque, maximum {cfg.max_cost_ratio_pct:.0f} %). "
                        f"Un stop plus large ou une unite de temps superieure corrigerait cela."),
                factors=factors,
            )
        factors.append(f"cout {cost:.3f} = {cost_ratio:.0f} % du risque")

        return SizingDecision(
            allowed=True,
            lots=lots,
            risk_amount=round(real_risk, 2),
            risk_pct=round(real_pct, 3),
            stop_distance=stop_distance,
            cost=round(cost, 4),
            cost_ratio_pct=round(cost_ratio, 1),
            factors=factors,
        )

    def execution_cost(self, instrument: Instrument, lots: float,
                       price: float, spread: float = 0.0) -> float:
        """Cout estime d'un aller-retour, dans la devise du compte.

        Trois postes, et le dernier est celui qu'on oublie :

          1. le SPREAD, compte une seule fois : on achete a l'offre et on
             revend a la demande, l'ecart n'est franchi qu'une fois sur
             l'aller-retour ;
          2. les COMMISSIONS, sur les deux cotes ;
          3. le GLISSEMENT, sur les deux cotes, parce qu'un ordre au marche
             consomme le carnet et n'obtient pas le prix affiche.

        Le glissement n'apparait sur aucune facture, et c'est pour ca qu'on
        l'oublie. Le negliger fait passer pour rentables des trades qui ne
        le sont pas — erreur qui ne se voit que sur le releve de compte.
        """
        cfg = self.config
        ecart = spread if spread > 0 else instrument.typical_spread
        valeur_par_point = instrument.value_per_price_unit(lots)

        cout = ecart * valeur_par_point
        cout += cfg.commission_per_lot * lots
        cout += price * instrument.contract_size * lots * cfg.commission_pct * 2
        # Glissement des deux cotes, exprime en fraction du spread.
        cout += ecart * valeur_par_point * max(0.0, cfg.slippage_spread_ratio) * 2
        return cout

    def cost_ratio_for(self, instrument: Instrument, stop_distance: float,
                       price: float, spread: float = 0.0) -> float:
        """Rapport cout/risque au lot minimum, independamment du capital.

        Sert au filtrage amont : si meme le lot minimum est trop cher a
        traiter sur cette unite de temps, l'instrument est ecarte sans
        qu'on ait besoin de calculer quoi que ce soit d'autre.
        """
        if stop_distance <= 0:
            return 100.0
        risque = stop_distance * instrument.value_per_price_unit(instrument.min_lot)
        if risque <= 0:
            return 100.0
        return self.execution_cost(instrument, instrument.min_lot, price, spread) / risque * 100.0

    # ---------------------------------------------------------------
    def halt(self, reason: str) -> None:
        self.account.halted = True
        self.account.halt_reason = reason
        logger.error("ARRET DU ROBOT : %s", reason)

    def resume(self) -> None:
        self.account.halted = False
        self.account.halt_reason = ""
        self.account.paused_until = 0.0

    def snapshot(self) -> dict:
        acc = self.account
        risk_pct, _ = self.effective_risk_pct()
        return {
            "capital": round(acc.equity, 2),
            "solde": round(acc.balance, 2),
            "devise": acc.currency,
            "pnl_jour_pct": round(acc.daily_pnl_pct(), 2),
            "pnl_semaine_pct": round(acc.weekly_pnl_pct(), 2),
            "drawdown_pct": round(acc.drawdown_pct(), 2),
            "risque_par_trade_pct": round(risk_pct, 3),
            "trades_du_jour": acc.trades_today,
            "pertes_consecutives": acc.consecutive_losses,
            "arrete": acc.halted,
            "raison_arret": acc.halt_reason,
        }
