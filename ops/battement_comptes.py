#!/usr/bin/env python3
"""Publie le pouls et le capital des comptes demo, sans toucher aux robots.

POURQUOI CE FICHIER EXISTE, ET POURQUOI IL EST TEMPORAIRE
=========================================================

L'application declare un compte « arrete » quand sa fiche
(`alluxe_bot_comptes.vu_le`) n'a pas ete rafraichie depuis un quart
d'heure. Or `run_demo.py` ne la publiait qu'au DEMARRAGE : les deux
robots etaient donc affiches arretes en permanence alors qu'ils
tournaient. Constate le 21 septembre :

    demo    vu_le = la veille 13h14   (20 heures)
    demo2   vu_le = 05h43             (3 h 30)

Un voyant toujours rouge ne dit plus rien. On cesse de le regarder, et
le jour ou un robot tombe vraiment, personne ne le voit.

`run_demo.py` republie desormais sa fiche toutes les cinq minutes --
mais cela n'entrera en vigueur qu'a son prochain demarrage, et
l'operateur a demande le 20 septembre que les deux comptes tournent
JUSQU'AU 28 SANS QUE RIEN NE SOIT TOUCHE. Ce script fait donc le travail
depuis l'exterieur, en lisant les fichiers d'etat : aucun redemarrage,
aucune interruption.

    A SUPPRIMER apres le premier redemarrage des robots, le 28. Le
    battement interne fera alors double emploi.

Il calcule aussi le capital vivant de chaque compte et le journalise --
utile pour verifier d'un coup d'oeil ce que vaut une simulation sans
ouvrir l'application. Il ne l'ECRIT pas en base : la table n'a pas de
colonne pour ca.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gold_bot.env import charger_env                          # noqa: E402
from gold_bot.methode import phrase_methode, resume_methode   # noqa: E402
from gold_bot.settings import BotConfig                        # noqa: E402

# CRON N'HERITE D'AUCUN ENVIRONNEMENT. Premiere version de ce fichier :
# la tache tournait toutes les cinq minutes et echouait a chaque fois sur
# « identifiants Supabase absents » -- donc le pouls qu'elle devait
# retablir n'a jamais battu, et les comptes seraient restes affiches
# « arretes ».
#
# C'est la meme famille de piege que le chien de garde du 31 aout
# (chemin relatif sans `cd`, donc jamais execute) : un travail planifie
# qui echoue en silence ressemble exactement a un travail qui n'existe
# pas. Tous les autres scripts d'`ops/` appellent `charger_env()` pour
# cette raison.
charger_env()

log = logging.getLogger("battement")

COMPTES = {
    # LE COMPTE REEL A REJOINT LA LISTE le 25 septembre, au depot de
    # 120 EUR. L'operateur l'a vu tout de suite : « je ne vois toujours
    # pas 120 EUR de capital dans l'application ». Les positions, elles,
    # remontaient bien -- c'est le robot qui les publie. Le CAPITAL, lui,
    # passe par ce battement, qui ne connaissait que les simulations.
    "reel": "robot.bitvavo.json",
    "demo": "robot.demo.json",
    "demo2": "robot.demo2.json",
}


#: Les cours de TOUS les marches, lus une fois par passage.
#: Un appel par crypto sur 24 positions, c'est 24 allers-retours pour
#: une donnee que Bitvavo rend entiere en un seul.
_CACHE: dict[str, float] = {}


def _charger_les_cours() -> None:
    """Le CARNET D'ORDRES, pas le prix du dernier echange.

    CINQUIEME ENDROIT OU CETTE MEME ERREUR SE REPETE. Ce script lisait
    `/ticker/price`, qui rend le prix de la derniere TRANSACTION : sur
    un marche peu echange il ne bouge pas tant que personne n'echange,
    et il affiche alors un cours vieux d'une heure.

    Le robot (20 sept.) et l'application (21 sept.) ont deja ete
    corriges. Ce script-ci a ete ecrit AVANT la decouverte et n'a pas
    ete repris -- d'ou l'ecart vu par l'operateur le 22 :

        verite (carnet)                   3 716,22 EUR
        gros chiffre de l'application     3 714,91 EUR   juste
        courbe et fiche du serveur        3 553,61 EUR   162 de moins

    Corriger la formule ne suffit jamais : il faut corriger TOUS ceux
    qui la calculent. C'est la lecon qui revient depuis le 18 septembre.
    """
    global _CACHE
    try:
        with urllib.request.urlopen(
                "https://api.bitvavo.com/v2/ticker/book", timeout=25) as r:
            lignes = json.loads(r.read().decode())
    except Exception:                                          # noqa: BLE001
        return
    # LA CLE EST LE MARCHE, PAS LA CRYPTO. Onze actifs sont cotes chez
    # Bitvavo DANS DEUX DEVISES (EUR et USDC) : BTC, SUI, ADA et huit
    # autres. Ranger les prix par crypto faisait ecraser le prix en
    # euros par celui en dollars, soit +15 % sur ces positions.
    #
    # Erreur introduite le 22 septembre a 00h32 en corrigeant le prix
    # perime, et repercutee dans la courbe : elle annoncait 3 716 EUR la
    # ou le compte en valait 3 569. C'est l'operateur qui a vu les deux
    # chiffres se contredire sur le meme ecran.
    #
    # On ne garde donc QUE les marches en euros -- le robot ne negocie
    # rien d'autre.
    out: dict[str, float] = {}
    for l in lignes:
        try:
            marche = str(l["market"])
            actif, _, devise = marche.partition("-")
            if devise != "EUR":
                continue
            b = float(l.get("bid") or 0)
            a = float(l.get("ask") or 0)
            v = (b + a) / 2 if b > 0 and a > 0 else (b or a)
            if v > 0:
                out[actif] = v
        except (KeyError, TypeError, ValueError):
            continue
    if out:
        _CACHE = out


def _cours(actif: str) -> float | None:
    if not _CACHE:
        _charger_les_cours()
    return _CACHE.get(actif)


def _avoirs_bitvavo() -> list | None:
    """Tous les avoirs du compte reel, tels que Bitvavo les rend.

    Le simulateur tient son solde dans son fichier d'etat ; le compte
    reel, lui, n'a de verite que chez le courtier. On l'interroge
    directement, sans passer par le robot -- ce battement doit pouvoir
    publier le capital meme quand le robot est a l'arret.
    """
    cle = os.environ.get("BITVAVO_API_KEY", "")
    secret = os.environ.get("BITVAVO_API_SECRET", "")
    if not cle or not secret:
        return None
    import hashlib
    import hmac
    ts = str(int(time.time() * 1000))
    sig = hmac.new(secret.encode(),
                   (ts + "GET" + "/v2/balance").encode(),
                   hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        "https://api.bitvavo.com/v2/balance",
        headers={"Bitvavo-Access-Key": cle, "Bitvavo-Access-Signature": sig,
                 "Bitvavo-Access-Timestamp": ts,
                 "Bitvavo-Access-Window": "10000"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            soldes = json.loads(r.read().decode())
    except Exception as exc:                                   # noqa: BLE001
        log.warning("solde Bitvavo illisible : %s", str(exc)[:120])
        return None
    return soldes


def _fichier_etat(compte: str) -> Path:
    """Le robot REEL ecrit `state.json`, les simulations `state-<nom>.json`."""
    return Path("data/state.json") if compte == "reel" \
        else Path(f"data/state-{compte}.json")


def _signer_bitvavo(chemin: str) -> dict | None:
    """Les en-tetes signes d'un GET Bitvavo. None si les cles manquent."""
    cle = os.environ.get("BITVAVO_API_KEY", "")
    secret = os.environ.get("BITVAVO_API_SECRET", "")
    if not cle or not secret:
        return None
    import hashlib
    import hmac
    ts = str(int(time.time() * 1000))
    sig = hmac.new(secret.encode(), (ts + "GET" + "/v2" + chemin).encode(),
                   hashlib.sha256).hexdigest()
    return {"Bitvavo-Access-Key": cle, "Bitvavo-Access-Signature": sig,
            "Bitvavo-Access-Timestamp": ts, "Bitvavo-Access-Window": "10000"}


#: Virements de la periode affichee (ts en s, montant signe), remplis par
#: `_depart_reel` et publies pour que la courbe de l'appli les neutralise.
_VIREMENTS_PERIODE: list[tuple[float, float]] = []


def _decaler_la_courbe(url: str, cle: str, compte: str, virements: list[dict]) -> None:
    """Neutralise chaque virement dans la courbe, UNE fois, cote base.

    Demande de l'operateur, 2 oct. 2026 : un retrait faisait chuter la
    courbe comme une perte. La correction cote application n'arrivait pas
    sur ses appareils (mise a jour OTA non recue) : la base decale donc
    elle-meme les releves d'avant chaque virement. La fonction SQL tient le
    registre des virements deja appliques (decaler_courbe_capital).
    """
    for v in virements:
        try:
            req = urllib.request.Request(
                f"{url}/rest/v1/rpc/decaler_courbe_capital",
                data=json.dumps({"p_compte": compte, "p_ts": v["ts"],
                                 "p_montant": v["montant"]}).encode(),
                headers={"apikey": cle, "authorization": f"Bearer {cle}",
                         "content-type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=20) as r:
                n = json.loads(r.read().decode() or "0")
            if n:
                log.info("courbe %s : %s releves decales de %+.2f (virement %s)",
                         compte, n, v["montant"], v["ts"])
        except Exception as exc:                               # noqa: BLE001
            log.warning("courbe non decalee pour %s : %s", v.get("ts"), str(exc)[:120])


def _depart_reel() -> float | None:
    """Ce que l'operateur a REELLEMENT mis dans le compte, net des retraits.

    POURQUOI CETTE FONCTION EXISTE. Le compte reel publiait
    `capital_depart = cfg.engine.start_balance`, soit **1 000 EUR** —
    un reglage de SIMULATEUR, qui ne veut rien dire sur un compte au
    comptant. Le gain encaisse s'en deduisait : `118,25 − 1 000`, donc
    **−881,75 EUR**. C'est pour ca que le bloc « encaisse » n'existait
    pas sur l'ecran Direct : il ne manquait pas, il cachait un chiffre
    absurde.

    La definition juste vient de l'operateur, le 26 septembre :
    « j'ai retire 2 EUR des 120, donc 118 de capital de depart ; si
    j'ajoute du capital il augmente, si j'en sors il diminue. »

    LA REGLE, ET POURQUOI ELLE NE STOCKE RIEN. On parcourt les
    mouvements en euros dans l'ordre, et **chaque fois que le cumul
    passe a zero ou en dessous, on repart de zero**. Un cumul negatif
    signifie que tout ce qui avait ete depose est ressorti : le compte a
    ete vide, et ce qui suit est une nouvelle serie.

        23 aout    +1, +50, -51,07  ->  -0,07  ->  remise a zero
        ...
        16 sept.   -50              -> -10,97  ->  remise a zero
        25 sept.   +120                 120,00
        26 sept.   -2                   118,00   <- le chiffre attendu

    Aucun fichier de reference, aucune date ecrite en dur : si le compte
    est vide a nouveau puis realimente, la remise a zero se refait toute
    seule. C'est ce qui evite la panne classique du depot — une
    reference figee qui devient fausse au premier mouvement.

    Les frais de depot sont deja deduits par Bitvavo dans `amount`.
    """
    mouvements: list[tuple[int, float]] = []
    for quoi, signe in (("/depositHistory", 1.0), ("/withdrawalHistory", -1.0)):
        entetes = _signer_bitvavo(quoi)
        if entetes is None:
            return None
        try:
            req = urllib.request.Request(
                "https://api.bitvavo.com/v2" + quoi, headers=entetes)
            with urllib.request.urlopen(req, timeout=30) as r:
                lignes = json.loads(r.read().decode())
        except Exception as exc:                               # noqa: BLE001
            log.warning("%s illisible : %s", quoi, str(exc)[:120])
            return None
        for x in lignes:
            if x.get("symbol") != "EUR" or x.get("status") != "completed":
                continue
            mouvements.append((int(x["timestamp"]), signe * float(x["amount"])))

    if PERIODE_REEL_DEPUIS:
        # La periode affichee commence a un capital connu : on n'y ajoute
        # que les virements qui la suivent (horodatages Bitvavo en ms).
        _VIREMENTS_PERIODE[:] = sorted(
            (ts / 1000.0, m) for ts, m in mouvements if ts / 1000.0 > PERIODE_REEL_DEPUIS)
        apres = sum(m for _, m in _VIREMENTS_PERIODE)
        return round(PERIODE_REEL_CAPITAL + apres, 2)
    if not mouvements:
        return None
    mouvements.sort()
    cumul = 0.0
    for _, montant in mouvements:
        cumul += montant
        if cumul <= 0:
            cumul = 0.0
    return round(cumul, 2)


def _cash_bitvavo() -> float | None:
    """Les EUROS SEULS, sans la valeur des cryptos detenues.

    C'est ce qui manquait pour que l'ecran Direct vive comme l'ecran
    Demo. Demo recalcule son capital a chaque cotation ; Direct ne le
    pouvait pas, parce qu'au comptant le capital vaut
    `euros restants + valeur de ce qu'on detient` et que l'application
    ne connaissait pas le premier terme. Elle devait donc attendre que
    le serveur republie, toutes les cinq minutes — d'ou le « le capital
    reste fige » de l'operateur, trois fois de suite.

    Avec ce chiffre, l'application fait elle-meme l'addition avec les
    cotations qu'elle a deja en direct pour les positions.
    """
    soldes = _avoirs_bitvavo()
    if soldes is None:
        return None
    for b in soldes:
        if b.get("symbol") == "EUR":
            return float(b.get("available", 0)) + float(b.get("inOrder", 0))
    return 0.0


def _capital_bitvavo() -> float | None:
    """Euros + valeur de marche de tout ce qui est detenu.

    C'est la definition d'un compte AU COMPTANT, et c'est ce que montre
    l'application de Bitvavo. On lit tous les avoirs, pas seulement
    l'euro : un robot qui vient d'acheter a peu d'euros et beaucoup de
    crypto, et son capital n'a pas bouge pour autant.
    """
    soldes = _avoirs_bitvavo()
    if soldes is None:
        return None
    total = 0.0
    for b in soldes:
        actif = b.get("symbol", "")
        quantite = float(b.get("available", 0)) + float(b.get("inOrder", 0))
        if quantite <= 0:
            continue
        if actif == "EUR":
            total += quantite
            continue
        prix = _cours(actif)
        if prix is None:
            # UN CAPITAL INCOMPLET EST PIRE QU'AUCUN CAPITAL. Le 1er et le
            # 2 oct., un prix manquant a fait publier 83,90 puis 171,36 EUR
            # (les euros seuls : la lecture des cours avait echoue) pour un
            # compte a ~500 -- des pics faux sur la courbe. Une POSITION DU
            # ROBOT sans prix annule le releve ; un reliquat inconnu non.
            if f"{actif}USD" in _actifs_detenus_par_le_robot():
                log.warning("capital non publie : pas de prix pour %s", actif)
                return None
            continue        # poussiere ou jeton delisté : sans effet
        total += quantite * prix
    return total


def _actifs_detenus_par_le_robot() -> set[str]:
    """Symboles des positions ouvertes du robot reel (volume > 0)."""
    try:
        meta = json.loads(Path("data/state.json").read_text()).get("position_meta") or {}
    except Exception:                                          # noqa: BLE001
        return set()
    return {k for k, m in meta.items() if float(m.get("volume") or 0) > 0}



def _portefeuille_reel() -> tuple[list[dict], float]:
    """Portefeuille REEL: avoirs Bitvavo + prix de revient du robot.

    Les signaux Supabase ne sont pas la source de verite d'une position
    reelle: un ordre peut etre execute, partiellement vendu, ou rester en
    reliquat alors que son signal est deja ferme. Bitvavo donne la quantite
    detenue; `state.json` porte le prix d'entree du robot pour cette quantite.
    """
    soldes = _avoirs_bitvavo()
    if soldes is None:
        return [], 0.0
    try:
        etat = json.loads(Path("data/state.json").read_text())
    except Exception:
        return [], 0.0
    meta = etat.get("position_meta") or {}
    positions: list[dict] = []
    latent = 0.0
    for solde in soldes:
        actif = str(solde.get("symbol") or "")
        if actif == "EUR":
            continue
        quantite = float(solde.get("available", 0) or 0) + float(solde.get("inOrder", 0) or 0)
        if quantite <= 0:
            continue
        prix = _cours(actif)
        m = meta.get(actif + "USD") or meta.get(actif + "EUR")
        if not m or prix is None:
            # Les poussières sans prix de revient ne sont pas des positions
            # du robot. Elles restent incluses dans l'equity Bitvavo.
            continue
        entree = float(m.get("entry_price") or 0)
        if entree <= 0:
            continue
        stop = float(m.get("stop_loss") or entree)
        p = {
            "id": f"portefeuille:{actif}",
            "reference": f"REEL:{actif}",
            "pair": f"{actif}/EUR",
            "side": "buy",
            "entry_price": entree,
            "stop_loss": stop,
            "take_profit_1": None,
            "take_profit_2": None,
            "position_size_pct": None,
            "capital_eur": None,
            "volume": quantite,
            "stop_loss_actuel": stop,
            "published_at": dt.datetime.fromtimestamp(float(m.get("opened_at") or time.time()), dt.timezone.utc).isoformat(),
            "status": "active",
            "closed_at": None,
            "result_pct": None,
            "profit_eur": None,
        }
        positions.append(p)
        latent += quantite * (prix - entree)
    positions.sort(key=lambda x: x["pair"])
    return positions, latent

def _solde_du_compte(compte: str) -> float | None:
    """Le liquide seul, sans le gain latent. Frais d'achat deduits."""
    chemin = _fichier_etat(compte)
    if not chemin.exists():
        return None
    try:
        solde = json.loads(chemin.read_text()).get("solde_simule")
    except Exception:                                          # noqa: BLE001
        return None
    return float(solde) if solde is not None else None


def capital_du_compte(compte: str) -> float | None:
    """Le capital VIVANT : liquide + gain latent des positions ouvertes.

    C'est la definition du simulateur (`PaperBroker.account`) : la valeur
    achetee n'est jamais debitee du solde, seul le gain flottant compte.
    Additionner le solde ET la valeur des positions reviendrait a compter
    l'argent deux fois -- erreur commise le 21 septembre, qui annoncait
    6 120 EUR sur un compte de 3 300.
    """
    chemin = _fichier_etat(compte)
    if not chemin.exists():
        return None
    try:
        etat = json.loads(chemin.read_text())
    except Exception:                                          # noqa: BLE001
        return None
    # LE COMPTANT NE SE COMPTE PAS COMME LE SIMULATEUR.
    #
    # Chez `PaperBroker`, la somme achetee n'est JAMAIS debitee du solde
    # (modele a marge) : le capital vaut donc solde + gain latent, et
    # additionner la valeur des positions compterait l'argent deux fois.
    #
    # Sur le compte REEL, au comptant, c'est l'inverse : les euros
    # partent vraiment a l'achat et on detient de la crypto. Appliquer la
    # formule du simulateur annoncait 96,56 EUR pour 120 deposes --
    # vu par l'operateur des la premiere minute : « je ne vois toujours
    # pas 120 EUR de capital ».
    #
    # Le capital reel vaut donc : euros restants + VALEUR de ce qu'on
    # detient, exactement ce qu'affiche Bitvavo.
    if compte == "reel":
        return _capital_bitvavo()

    solde = etat.get("solde_simule")
    if solde is None:
        # LE COMPTE REEL N'A PAS DE SOLDE SIMULE, il a un vrai solde chez
        # Bitvavo. On va le chercher la-bas plutot que de rendre None --
        # sinon l'application affiche un capital vide sur le seul compte
        # qui contient de l'argent.
        solde = _solde_bitvavo()
        if solde is None:
            return None
    latent = 0.0
    for p in (etat.get("position_meta") or {}).values():
        actif = p.get("symbol", "").replace("USD", "").replace("EUR", "")
        prix = _cours(actif)
        if prix is None:
            continue
        signe = -1.0 if str(p.get("side", "")).upper().endswith("SELL") else 1.0
        latent += signe * p.get("volume", 0.0) * (prix - p.get("entry_price", 0.0))
    return float(solde) + latent


#: DEBUT DE LA PERIODE AFFICHEE POUR LE COMPTE REEL -- UN SEUL ENDROIT.
#:
#: Decision de l'operateur, 2 oct. 2026 : tout l'affichage du reel repart
#: du capital a ~600 EUR, soit le redemarrage du 1er oct. a 19h41 UTC sur
#: 595,62 EUR apres le retrait de 1 610 EUR. Ce couple pilote ENSEMBLE :
#:   - l'historique publie (trades fermes avant : non publies) ;
#:   - le capital de depart (595,62 + depots - retraits posterieurs) ;
#:   - donc « encaisse » = capital - depart - latent, sur la meme periode
#:     que l'historique, au lieu des depots nets depuis le 25 sept. (648).
#: « Quand on fait un changement, tout l'affichage se remet a jour » :
#: changer ces deux valeurs suffit, au battement suivant (5 min). Le
#: journal local data/trades.jsonl reste intact.
PERIODE_REEL_DEPUIS = 1790883660.0
PERIODE_REEL_CAPITAL = 595.62
HISTORIQUE_REEL_DEPUIS = PERIODE_REEL_DEPUIS


def _synchroniser_historique_reel(url: str, cle: str) -> None:
    """Publie le journal d'execution reel dans la table d'historique complete."""
    chemin = Path("data/trades.jsonl")
    if not chemin.exists():
        return
    try:
        lignes = [json.loads(x) for x in chemin.read_text().splitlines() if x.strip()]
    except Exception as exc:
        log.warning("journal reel illisible: %s", str(exc)[:120])
        return

    import hashlib
    corps = []
    for trade in lignes:
        try:
            opened = float(trade["opened_at"])
            closed = float(trade["closed_at"])
            if closed < HISTORIQUE_REEL_DEPUIS:
                continue
            entry = float(trade["entry_price"])
            exit_price = float(trade["exit_price"])
            volume = float(trade["volume"])
            side = str(trade.get("side", "BUY")).upper()
            sens = -1.0 if side == "SELL" else 1.0
            pct = ((exit_price - entry) / entry * 100.0 * sens) if entry > 0 else 0.0
            stable = json.dumps(trade, sort_keys=True, separators=(",", ":"))
            trade_id = hashlib.sha256(stable.encode()).hexdigest()
            corps.append({
                "trade_id": trade_id,
                "reference": str(trade.get("position_id") or trade.get("symbol") or trade_id[:12]),
                "pair": str(trade.get("symbol") or "").replace("USD", "/EUR").replace("EUR/EUR", "/EUR"),
                "side": side,
                "entry_price": entry,
                "exit_price": exit_price,
                "volume": volume,
                "opened_at": dt.datetime.fromtimestamp(opened, dt.timezone.utc).isoformat(),
                "closed_at": dt.datetime.fromtimestamp(closed, dt.timezone.utc).isoformat(),
                "profit_eur": float(trade.get("profit") or 0.0),
                "result_pct": round(pct, 6),
                "reason": str(trade.get("reason") or ""),
                "partial": bool(trade.get("partial", False)),
            })
        except (KeyError, TypeError, ValueError, OverflowError):
            continue

    if not corps:
        return
    try:
        requete = urllib.request.Request(
            f"{url}/rest/v1/alluxe_bot_historique_reel?on_conflict=trade_id",
            data=json.dumps(corps).encode(),
            headers={
                "apikey": cle,
                "authorization": f"Bearer {cle}",
                "content-type": "application/json",
                "prefer": "resolution=merge-duplicates,return=minimal",
            },
            method="POST",
        )
        urllib.request.urlopen(requete, timeout=30).close()
        log.info("historique reel synchronise: %s executions", len(corps))
    except Exception as exc:
        log.warning("historique reel non synchronise: %s", str(exc)[:160])


def _realise_publie(url: str, cle: str, compte: str) -> float | None:
    """Reel realise visible par l'application pour la session courante.

    Le solde du PaperBroker contient aussi les frais d'entree des positions
    ouvertes. Il ne peut donc pas servir directement de « encaisse ». La
    source de verite de l'ecran est ici `signals`: seules les clotures
    effectivement publiees dans l'application comptent comme realisees.
    """
    try:
        if compte == "reel":
            # Le reel n'a pas de started_at de simulateur : les trades
            # reels clotures sont la source de verite du realise.
            requete = urllib.request.Request(
                f"{url}/rest/v1/signals?select=profit_eur,status&is_demo=eq.false&status=in.(closed_tp,closed_sl)",
                headers={"apikey": cle, "authorization": f"Bearer {cle}"},
            )
        else:
            etat = json.loads(_fichier_etat(compte).read_text())
            debut = float(etat.get("started_at") or 0.0)
            if debut <= 0:
                return None
            debut_iso = dt.datetime.fromtimestamp(debut, dt.timezone.utc).isoformat()
            requete = urllib.request.Request(
                f"{url}/rest/v1/signals?select=profit_eur,status&compte=eq.{urllib.parse.quote(compte, safe='')}&is_demo=eq.true&status=in.(closed_tp,closed_sl)&created_at=gte.{urllib.parse.quote(debut_iso, safe='')}",
                headers={"apikey": cle, "authorization": f"Bearer {cle}"},
            )
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            lignes = json.loads(reponse.read().decode("utf-8"))
        return round(sum(float(x.get("profit_eur") or 0.0) for x in lignes), 2)
    except Exception as exc:                                  # noqa: BLE001
        log.warning("realise publie %s indisponible : %s", compte, str(exc)[:160])
        return None


def publier(compte: str, fichier: str) -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        log.warning("identifiants Supabase absents")
        return False
    if compte == "reel":
        _synchroniser_historique_reel(url, cle)
    try:
        cfg = BotConfig.load(fichier)
    except Exception as exc:                                   # noqa: BLE001
        log.warning("%s illisible : %s", fichier, str(exc)[:120])
        return False

    corps = {
        "compte": compte,
        "resume_methode": resume_methode(cfg),
        "methode": phrase_methode(cfg),
        "capital_depart": float(getattr(cfg.engine, "start_balance", 0.0) or 0.0),
        "vu_le": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    # LE COMPTE REEL N'A PAS DE `start_balance` : IL A DES VIREMENTS.
    #
    # `start_balance` est la dotation d'un simulateur. Sur le compte
    # reel elle valait 1 000 EUR et ne correspondait a rien — voir
    # `_depart_reel`. On la remplace par les depots nets, et on publie
    # les euros disponibles pour que l'application calcule le capital
    # en direct au lieu de l'attendre.
    if compte == "reel":
        depart_reel = _depart_reel()
        if depart_reel is not None and depart_reel > 0:
            corps["capital_depart"] = depart_reel
            # La courbe de l'appli retire ces virements : un retrait n'est
            # pas une perte (demande de l'operateur du 2 oct. 2026).
            corps["virements"] = [
                {"ts": dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat(),
                 "montant": round(m, 2)} for t, m in _VIREMENTS_PERIODE]
            _decaler_la_courbe(url, cle, compte, corps["virements"])
        cash = _cash_bitvavo()
        if cash is not None:
            corps["cash_eur"] = round(cash, 2)
    depart = float(corps["capital_depart"] or 0.0)

    # LE CAPITAL VA MAINTENANT EN BASE.
    #
    # Il n'y allait pas le 21 septembre : la colonne n'existait pas
    # (PGRST204) et le jeton d'administration avait expire, donc aucune
    # migration ne passait. Consequence visible pour l'operateur : le
    # capital affiche sur l'onglet demo qu'on NE regarde PAS ne comptait
    # que les trades fermes -- il ignorait toutes les positions
    # ouvertes, et paraissait fige.
    #
    # Le jeton a ete regenere le 22 ; la colonne et la table
    # d'historique existent.
    capital = capital_du_compte(compte)
    if capital is not None:
        corps["capital_eur"] = round(capital, 2)

    # PORTEFEUILLE REEL: Bitvavo est la source de verite.
    # `signals` reste l'historique du robot, mais ne peut pas representer
    # les reliquats apres une vente partielle (ex. MOVR/GRASS) ni detecter
    # un signal devenu orphelin (ex. BNT).
    if compte == "reel":
        portefeuille, latent = _portefeuille_reel()
        corps["positions_reel"] = portefeuille
        if capital is not None and depart > 0:
            # Identite comptable: equity = depots nets + realise + latent.
            # Ainsi "encaissé" inclut aussi les frais et ecarts que le journal
            # de signaux peut ignorer; il ne double jamais le latent.
            corps["encaisse_eur"] = round(capital - depart - latent, 2)
    else:
        # Pour les simulations, conserver la source historique des trades.
        solde = _solde_du_compte(compte)
        depart = corps["capital_depart"]
        if solde is not None and depart > 0:
            realise_publie = _realise_publie(url, cle, compte)
            if realise_publie is not None:
                corps["encaisse_eur"] = realise_publie

    try:
        requete = urllib.request.Request(
            f"{url}/rest/v1/alluxe_bot_comptes",
            data=json.dumps(corps).encode(),
            headers={"apikey": cle, "authorization": f"Bearer {cle}",
                     "content-type": "application/json",
                     "prefer": "resolution=merge-duplicates"},
            method="POST")
        urllib.request.urlopen(requete, timeout=20).close()
    except Exception as exc:                                   # noqa: BLE001
        log.warning("fiche « %s » non publiee : %s", compte, str(exc)[:160])
        return False
    # UN RELEVE DE PLUS DANS L'HISTORIQUE, pour la courbe.
    #
    # Une ligne toutes les cinq minutes et par compte : c'est peu de
    # donnees, et c'est ce qui permet de tracer 1 jour, 7 jours, 30
    # jours et 1 an. Sans releve regulier, aucune courbe n'est possible
    # -- on ne peut pas reconstituer apres coup une valeur qu'on n'a
    # jamais enregistree.
    #
    # L'echec n'est pas fatal : mieux vaut un trou dans la courbe qu'un
    # pouls perdu.
    if capital is not None:
        try:
            r = urllib.request.Request(
                f"{url}/rest/v1/alluxe_bot_capital",
                data=json.dumps({"compte": compte,
                                 "capital_eur": round(capital, 2)}).encode(),
                headers={"apikey": cle, "authorization": f"Bearer {cle}",
                         "content-type": "application/json"},
                method="POST")
            urllib.request.urlopen(r, timeout=20).close()
        except Exception as exc:                               # noqa: BLE001
            log.warning("releve de capital non enregistre : %s", str(exc)[:120])

    log.info("fiche « %s » publiee — capital %s",
             compte, f"{capital:.2f} EUR" if capital is not None else "inconnu")
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    # ON NE PUBLIE QUE POUR UN ROBOT QUI TOURNE VRAIMENT. Sinon ce script
    # maintiendrait le voyant au vert sur un compte mort, ce qui est pire
    # que le defaut qu'il corrige.
    import subprocess
    ok = 0
    for compte, fichier in COMPTES.items():
        # LE SERVICE REEL NE S'APPELLE PAS `robot-reel`. Les simulations
        # tournent sous `robot-demo` et `robot-demo2`, mais l'argent reel
        # sous `robot-dual-live` -- nom herite du moteur a deux strategies.
        # Sans cette correspondance, le compte qui contient l'argent est
        # le seul declare « arrete ».
        service = "robot-dual-live" if compte == "reel" else f"robot-{compte}"
        actif = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True).stdout.strip() == "active"
        if not actif and compte != "reel":
            log.info("robot-%s n'est pas actif : fiche non rafraichie", compte)
            continue
        # Le compte réel doit rester affiché même si le moteur de trading
        # est arrêté : l'application doit montrer le vrai portefeuille
        # Bitvavo, pas le dernier snapshot du robot.
        ok += 1 if publier(compte, fichier) else 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
