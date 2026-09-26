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
        if prix is not None:
            total += quantite * prix
    return total


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


def publier(compte: str, fichier: str) -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        log.warning("identifiants Supabase absents")
        return False
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
        cash = _cash_bitvavo()
        if cash is not None:
            corps["cash_eur"] = round(cash, 2)
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

    # CE QUI EST VRAIMENT DANS LA CAISSE.
    #
    # L'application additionnait les benefices des trades fermes pour
    # afficher « X EUR encaisses ». Deux choses manquaient a ce total, et
    # l'operateur les a vues le 22 septembre en comparant ses ecrans au
    # serveur (128,28 affiches pour 117,08 reels) :
    #
    #   - les arrondis des pourcentages publies, ~3 EUR sur 7 trades ;
    #   - surtout, LES FRAIS D'ACHAT DES POSITIONS ENCORE OUVERTES.
    #     `ClosedTrade.profit` ne deduit que les frais de VENTE ; ceux
    #     d'achat sont preleves a l'ouverture et n'apparaissent donc
    #     dans aucun trade ferme. Sur la demo 2, 25 positions ouvertes
    #     depuis le debut : 7,93 EUR deja payes, invisibles.
    #
    # Le solde du simulateur, lui, les porte tous. C'est le seul chiffre
    # qui ne se reconstitue pas — et c'est celui sur lequel le robot
    # dimensionne ses positions.
    solde = _solde_du_compte(compte) if compte != "reel" else _capital_bitvavo()
    depart = corps["capital_depart"]
    if solde is not None and depart > 0:
        corps["encaisse_eur"] = round(solde - depart, 2)

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
        if not actif:
            log.info("robot-%s n'est pas actif : fiche non rafraichie", compte)
            continue
        ok += 1 if publier(compte, fichier) else 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
