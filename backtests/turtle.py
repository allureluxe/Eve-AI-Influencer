#!/usr/bin/env python3
"""La methode Turtle ORIGINALE, telle que Dennis et Eckhardt l'ont ecrite.

Ce fichier n'est pas une variante de la notre. C'est l'autre systeme,
implemente separement pour qu'on puisse les faire courir cote a cote sur
la meme periode, le meme univers et le MEME modele de frais — c'est la
seule facon d'obtenir une comparaison qui veuille dire quelque chose.

Les regles, dans l'ordre du manuel :

  1. N = ATR 20 jours. L'unite vaut  1 % du capital / N  : un mouvement
     de 1 N fait donc bouger le compte de 1 %.
  2. Entree System 1  : cassure du plus-haut de 20 jours, SAUTEE si la
     cassure precedente sur ce marche aurait ete gagnante.
     Entree System 2  : cassure du plus-haut de 55 jours, jamais sautee.
  3. Stop a 2 N de l'entree. Il ne bouge que par le pyramidage.
  4. Pyramidage : une unite de plus tous les 1/2 N en notre faveur,
     4 unites au maximum, et TOUS les stops remontent a 2 N sous le prix
     de la derniere unite.
  5. Sortie : cloture sous le plus-bas de 10 jours (System 1) ou de
     20 jours (System 2). Aucun objectif de profit.
  6. Plafonds : 4 unites par marche, 12 unites par sens.

Ce qui est FIDELE mais impossible sur le compte reel : la vente a
decouvert. Le compte Bitvavo est au comptant. On mesure donc les deux —
`autoriser_vente=True` pour repondre a « que vaut la vraie methode »,
`False` pour repondre a « que vaut ce qu'on pourrait vraiment armer ».
"""
from __future__ import annotations

from dataclasses import dataclass, field

from donnees import Bougie
from moteur import COMMISSION, SPREAD, Trade, atr


@dataclass
class ReglagesTurtle:
    capital: float = 1000.0
    risque_n_pct: float = 0.01      # 1 % du compte par N — la regle du manuel
    n_periode: int = 20             # N = ATR 20 jours
    stop_n: float = 2.0             # stop a 2 N
    pyramide_max: int = 4           # 4 unites par marche
    espacement_n: float = 0.5       # une unite de plus tous les 1/2 N
    unites_max_par_sens: int = 12   # plafond de portefeuille du manuel
    system1_entree: int = 20
    system1_sortie: int = 10
    system2_entree: int = 55
    system2_sortie: int = 20
    filtre_system1: bool = True     # sauter la cassure apres un gagnant
    autoriser_vente: bool = True    # la moitie du systeme, interdite au comptant
    ticket_min: float = 5.0         # minimum Bitvavo
    multiplicateur_couts: float = 1.0
    debut: float = 0.0              # fenetre de mesure ; l'historique
    fin: float = 9e18               # anterieur reste lisible pour les canaux
    # Plafond d'exposition, notionnel total (achats + ventes) / capital.
    # A 1,0 le compte n'engage jamais plus qu'il ne possede : c'est la
    # seule facon de savoir si la VENTE paie, ou si c'etait le LEVIER.
    levier_max: float = 9.9
    # Interet d'emprunt sur les VENTES a decouvert, par jour. Tarif
    # Bitvavo marge : ~0,0274 %/j. Il court tant que la position est
    # ouverte — sur un trend suivi 20 jours c'est 0,55 % du notionnel,
    # loin d'etre negligeable. L'omettre rend la vente a decouvert plus
    # belle qu'elle n'est.
    interet_vente_par_jour: float = 0.000274
    # Paires reellement vendables a decouvert. Bitvavo n'ouvre la marge
    # que sur une quinzaine d'actifs, pas sur les 70 de l'univers. Vendre
    # tout l'univers en rejeu surestime donc la vente a decouvert d'un
    # facteur qu'il vaut mieux mesurer que supposer. Vide = tout permis.
    paires_vendables: tuple[str, ...] = ()
    # LIQUIDATION. Chez Bitvavo la vente a decouvert est a levier 10x : la
    # marge vaut 10 % du notionnel et la position est liquidee des que le
    # prix monte de ~7 %. Ce n'est PAS un stop qu'on choisit — il est
    # impose, il ne se deplace pas, et il coupe avant le stop 2N des que
    # celui-ci est plus large. Le mesurer change tout sur les actifs
    # volatils. A 0, aucune liquidation (l'hypothese trop belle d'avant).
    liquidation_hausse_pct: float = 0.07


@dataclass
class Unite:
    entree: float
    lots: float


@dataclass
class PositionT:
    paire: str
    sens: int                       # +1 achat, -1 vente
    systeme: int                    # 1 ou 2 — decide le canal de sortie
    unites: list[Unite] = field(default_factory=list)
    stop: float = 0.0
    derniere_entree: float = 0.0
    n_entree: float = 0.0
    ouvert_le: float = 0.0

    @property
    def lots(self) -> float:
        return sum(u.lots for u in self.unites)

    @property
    def prix_moyen(self) -> float:
        tot = self.lots
        return sum(u.entree * u.lots for u in self.unites) / tot if tot else 0.0


# ---------------------------------------------------------------------
# Le filtre System 1 : « la cassure precedente a-t-elle gagne ? »
# ---------------------------------------------------------------------
def _cassures_perdantes(serie: list[Bougie], r: ReglagesTurtle,
                        sens: int) -> dict[int, bool]:
    """Pour chaque cassure de 20 jours, dit si la PRECEDENTE avait perdu.

    Le manuel dit de sauter une cassure quand celle d'avant aurait ete
    gagnante — que la Tortue l'ait prise ou non. On simule donc en
    parallele un System 1 « fantome » qui prend TOUT, et on lit son
    dernier resultat clos au moment ou la vraie cassure se presente.
    """
    n_e, n_s = r.system1_entree, r.system1_sortie
    ok: dict[int, bool] = {}
    dernier_gagnant: bool | None = None
    fantome: tuple[int, float, float] | None = None   # (i0, entree, stop)

    for i in range(max(n_e, r.n_periode) + 1, len(serie) - 1):
        b = serie[i]

        # Le trade fantome en cours se termine-t-il ici ?
        if fantome is not None:
            i0, entree, stop = fantome
            fini = sortie = None
            if sens > 0:
                canal = min(x.low for x in serie[i - n_s:i])
                if b.low <= stop:
                    fini, sortie = True, stop
                elif b.close < canal:
                    fini, sortie = True, b.close
            else:
                canal = max(x.high for x in serie[i - n_s:i])
                if b.high >= stop:
                    fini, sortie = True, stop
                elif b.close > canal:
                    fini, sortie = True, b.close
            if fini:
                dernier_gagnant = (sortie - entree) * sens > 0
                fantome = None

        # Une cassure se produit-elle a la cloture de i ?
        if sens > 0:
            cassure = b.close > max(x.high for x in serie[i - n_e:i])
        else:
            cassure = b.close < min(x.low for x in serie[i - n_e:i])
        if not cassure:
            continue

        # Verdict pour la VRAIE strategie : on saute si la precedente a gagne.
        ok[i] = (dernier_gagnant is not True)

        # Et le fantome, lui, la prend toujours.
        if fantome is None:
            a = atr(serie, i, r.n_periode)
            if a > 0:
                e = serie[i + 1].open
                fantome = (i, e, e - sens * r.stop_n * a)
    return ok


# ---------------------------------------------------------------------
# Le rejeu
# ---------------------------------------------------------------------
def rejouer_turtle(donnees: dict[str, list[Bougie]], r: ReglagesTurtle) -> dict:
    comm = COMMISSION * r.multiplicateur_couts
    spread = SPREAD * r.multiplicateur_couts

    index = {p: {b.ts: i for i, b in enumerate(s)} for p, s in donnees.items()}
    jours = sorted({b.ts for s in donnees.values() for b in s
                    if r.debut <= b.ts <= r.fin})

    # Filtre System 1 : precalcule une fois par paire et par sens.
    autorise = {}
    if r.filtre_system1:
        for p, s in donnees.items():
            autorise[(p, 1)] = _cassures_perdantes(s, r, 1)
            if r.autoriser_vente:
                autorise[(p, -1)] = _cassures_perdantes(s, r, -1)

    capital = r.capital
    ouvertes: dict[str, PositionT] = {}
    trades: list[Trade] = []
    courbe: list[tuple[float, float]] = []
    jours_exposes = 0
    frais_total = 0.0
    pyramidages = 0
    expo: list[tuple[float, float]] = []

    def fermer(pos: PositionT, px_brut: float, t: float, motif: str):
        nonlocal capital, frais_total
        px = px_brut * (1 - pos.sens * spread)
        brut = (px - pos.prix_moyen) * pos.lots * pos.sens
        f = (pos.prix_moyen + px) * pos.lots * comm
        if pos.sens < 0 and r.interet_vente_par_jour > 0:
            jours = max(0.0, (t - pos.ouvert_le) / 86400.0)
            f += (pos.prix_moyen * pos.lots
                  * r.interet_vente_par_jour * jours)
        capital += brut - f
        frais_total += f
        trades.append(Trade(pos.paire, pos.ouvert_le, t, pos.prix_moyen, px,
                            pos.lots, brut - f, f, motif))

    for t in jours:
        # ---- 1. Sorties et pyramidage, sur la bougie du jour ----
        for paire in list(ouvertes):
            pos = ouvertes[paire]
            i = index[paire].get(t)
            if i is None:
                continue
            s = donnees[paire]
            b = s[i]
            n_s = r.system1_sortie if pos.systeme == 1 else r.system2_sortie
            if i < n_s + 1:
                continue

            # Le stop passe AVANT le canal : dans la journee il est touche
            # en premier des que le plus-bas y descend.
            # La liquidation passe AVANT tout le reste : elle ne se
            # negocie pas et elle ne se deplace pas.
            if pos.sens < 0 and r.liquidation_hausse_pct > 0:
                seuil_liq = pos.unites[0].entree * (1 + r.liquidation_hausse_pct)
                if b.high >= seuil_liq:
                    fermer(pos, seuil_liq, t, "LIQUIDATION")
                    del ouvertes[paire]; continue

            if pos.sens > 0:
                canal = min(x.low for x in s[i - n_s:i])
                if b.low <= pos.stop:
                    fermer(pos, pos.stop, t, "stop 2N"); del ouvertes[paire]; continue
                if b.close < canal:
                    fermer(pos, b.close, t, f"canal {n_s} j"); del ouvertes[paire]; continue
            else:
                canal = max(x.high for x in s[i - n_s:i])
                if b.high >= pos.stop:
                    fermer(pos, pos.stop, t, "stop 2N"); del ouvertes[paire]; continue
                if b.close > canal:
                    fermer(pos, b.close, t, f"canal {n_s} j"); del ouvertes[paire]; continue

            # Pyramidage : tous les 1/2 N depuis la DERNIERE unite posee.
            while (len(pos.unites) < r.pyramide_max and pos.n_entree > 0
                   and i + 1 < len(s)):
                seuil = pos.derniere_entree + pos.sens * r.espacement_n * pos.n_entree
                atteint = (b.high >= seuil) if pos.sens > 0 else (b.low <= seuil)
                if not atteint:
                    break
                total_unites = sum(len(p.unites) for p in ouvertes.values()
                                   if p.sens == pos.sens)
                if total_unites >= r.unites_max_par_sens:
                    break
                px = seuil * (1 + pos.sens * spread)
                lots = r.risque_n_pct * capital / pos.n_entree
                notionnel = lots * px
                engage = sum(abs(p.lots) * p.prix_moyen
                             for p in ouvertes.values())
                if (notionnel < r.ticket_min
                        or engage + notionnel > r.levier_max * capital):
                    break
                pos.unites.append(Unite(px, lots))
                pos.derniere_entree = px
                # Regle du manuel : TOUS les stops remontent a 2 N sous la
                # derniere unite. C'est ce qui rend le pyramidage tenable.
                pos.stop = px - pos.sens * r.stop_n * pos.n_entree
                pyramidages += 1

        if ouvertes:
            jours_exposes += 1

        # ---- 2. Entrees ----
        for paire, s in donnees.items():
            if paire in ouvertes:
                continue
            i = index[paire].get(t)
            besoin = max(r.system2_entree, r.n_periode) + 1
            if i is None or i < besoin or i + 1 >= len(s):
                continue
            b = s[i]
            a = atr(s, i, r.n_periode)
            if a <= 0:
                continue

            sens = systeme = 0
            vendable = (not r.paires_vendables) or (paire in r.paires_vendables)
            # System 2 d'abord : il n'est jamais saute, donc il prime.
            if b.close > max(x.high for x in s[i - r.system2_entree:i]):
                sens, systeme = 1, 2
            elif (r.autoriser_vente and vendable
                    and b.close < min(x.low for x in s[i - r.system2_entree:i])):
                sens, systeme = -1, 2
            elif b.close > max(x.high for x in s[i - r.system1_entree:i]):
                if not r.filtre_system1 or autorise.get((paire, 1), {}).get(i, True):
                    sens, systeme = 1, 1
            elif (r.autoriser_vente and vendable
                    and b.close < min(x.low for x in s[i - r.system1_entree:i])):
                if not r.filtre_system1 or autorise.get((paire, -1), {}).get(i, True):
                    sens, systeme = -1, 1
            if sens == 0:
                continue

            total_unites = sum(len(p.unites) for p in ouvertes.values()
                               if p.sens == sens)
            if total_unites >= r.unites_max_par_sens:
                continue

            px = s[i + 1].open * (1 + sens * spread)
            lots = r.risque_n_pct * capital / a       # 1 N = 1 % du compte
            notionnel = lots * px
            if notionnel < r.ticket_min:
                continue
            # Plafond d'exposition, TOUS SENS CONFONDUS. Une vente engage
            # autant qu'un achat : la borner d'un seul cote laisserait le
            # levier rentrer par la porte de derriere.
            engage_total = sum(abs(p.lots) * p.prix_moyen
                               for p in ouvertes.values())
            place = max(0.0, r.levier_max * capital - engage_total)
            if notionnel > place:
                lots = place / px
                notionnel = lots * px
                if notionnel < r.ticket_min:
                    continue
            ouvertes[paire] = PositionT(
                paire, sens, systeme, [Unite(px, lots)],
                px - sens * r.stop_n * a, px, a, s[i + 1].ts)

        # ---- 3. Valeur du portefeuille ----
        valeur = capital
        notionnel_jour = 0.0
        for paire, pos in ouvertes.items():
            i = index[paire].get(t)
            if i is not None:
                valeur += (donnees[paire][i].close - pos.prix_moyen) \
                          * pos.lots * pos.sens
                notionnel_jour += donnees[paire][i].close * pos.lots
        courbe.append((t, valeur))
        # Combien d'argent est engage rapporte a ce qu'on possede. Au
        # comptant ce rapport ne PEUT pas depasser 1 : au-dessus, la
        # methode emprunte, et Bitvavo refuserait l'ordre.
        expo.append((t, notionnel_jour / valeur if valeur > 0 else 0.0))

    for paire, pos in list(ouvertes.items()):
        i = index[paire].get(jours[-1]) if jours else None
        b = donnees[paire][i] if i is not None else donnees[paire][-1]
        fermer(pos, b.close, b.ts, "fin de periode")

    return {"trades": trades, "courbe": courbe, "frais": frais_total,
            "jours_exposes": jours_exposes, "jours_total": len(jours),
            "capital_final": courbe[-1][1] if courbe else r.capital,
            "pyramidages": pyramidages, "expo": expo, "reglages": r}
