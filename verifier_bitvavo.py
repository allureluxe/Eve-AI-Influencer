#!/usr/bin/env python3
"""Preuve d'execution : un aller-retour reel, minuscule, sur Bitvavo.

Le robot n'entre que sur un signal valide — c'est ce qui fait sa valeur, et
c'est aussi ce qui empeche de le « forcer » a trader pour se rassurer. Ce
script repond au meme besoin autrement : il passe un vrai ordre d'achat puis
le revend immediatement, en empruntant exactement le chemin d'execution du
robot (meme signature HMAC, meme traduction de symbole, memes arrondis,
meme controle de notionnel minimum).

Ce qu'il prouve : les cles fonctionnent, le droit « Trade » est actif, les
ordres partent, sont executes, et apparaissent dans l'historique Bitvavo.

Ce qu'il ne prouve pas : que la strategie trouve de bonnes occasions. Cela,
seuls les trades reels du robot le diront.

Cout : les frais de l'aller-retour, soit environ 0,05 EUR sur un ordre de 10.

    python3 verifier_bitvavo.py                 # simulation, rien n'est envoye
    python3 verifier_bitvavo.py --confirmer     # ordres reels
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.brokers.bitvavo import (BitvavoBroker, BitvavoConfig,   # noqa: E402
                                      formater)


def charger_env(chemin: str = ".env") -> None:
    """Charge le .env comme le fait le service systemd."""
    if not os.path.exists(chemin):
        return
    with open(chemin, "r", encoding="utf-8") as fh:
        for ligne in fh:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            os.environ.setdefault(cle.strip(), valeur.strip())


def adresse_publique() -> str:
    """Adresse IP publique de ce serveur, vue depuis l'exterieur.

    C'est celle que la plateforme voit, et donc celle qu'il faut
    autoriser — pas celle de l'interface reseau locale, qui peut differer
    derriere une passerelle.
    """
    import urllib.request
    for service in ("https://api.ipify.org", "https://ifconfig.me/ip"):
        try:
            with urllib.request.urlopen(service, timeout=6) as r:
                adresse = r.read().decode().strip()
            if adresse and len(adresse) <= 45:
                return adresse
        except Exception:  # noqa: BLE001
            continue
    return ""


def titre(texte: str) -> None:
    print(f"\n\033[1;36m{texte}\033[0m")


def ok(texte: str) -> None:
    print(f"  \033[1;32m[OK]\033[0m {texte}")


def echec(texte: str) -> None:
    print(f"  \033[1;31m[STOP]\033[0m {texte}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirmer", action="store_true",
                        help="envoyer reellement les ordres")
    parser.add_argument("--paire", default="",
                        help="symbole interne a tester, ex. BTCUSD "
                             "(defaut : le premier disponible)")
    args = parser.parse_args()

    charger_env()
    config = BitvavoConfig.from_env()

    titre("1. Configuration")
    print(f"  devise de cotation : {config.quote_asset}")
    print(f"  dry-run            : {config.dry_run}")

    # En simulation on fait TOUT le diagnostic — connexion, solde, tarif
    # reel, choix de la paire, calcul de l'ordre — et on s'arrete juste
    # avant d'envoyer. Refuser de tourner obligerait a desarmer la
    # securite pour verifier que la cle fonctionne : exactement le
    # contraire de ce qu'on veut.
    if config.dry_run and args.confirmer:
        echec("BITVAVO_DRY_RUN=1 : impossible d'envoyer des ordres reels.")
        print("\n  Le diagnostic complet reste disponible sans --confirmer :")
        print("      python3 verifier_bitvavo.py")
        return 2
    if not (config.api_key and config.api_secret):
        echec("Cles Bitvavo absentes de .env "
              "(BITVAVO_API_KEY et BITVAVO_API_SECRET).")
        return 2
    if config.dry_run:
        ok("cles presentes — diagnostic en LECTURE SEULE, aucun ordre ne partira")
    else:
        ok("mode reel, cles presentes")

    # Le broker est toujours construit en lecture seule ici : les ordres
    # ne partent qu'au moment explicite, plus bas, et seulement avec
    # --confirmer sur un .env desarme.
    # `dataclasses.replace` et non `__dict__` : BitvavoConfig utilise
    # slots=True et n'a donc pas de __dict__.
    broker = BitvavoBroker(replace(config, dry_run=True))

    titre("2. Connexion et lecture du compte")
    if not broker.connect():
        echec(f"connexion refusee : {broker._last_error}")
        if "IP" in broker._last_error:
            # Le cas est si frequent — et la reponse si simple — qu'il vaut
            # mieux donner l'adresse que de demander a l'utilisateur d'aller
            # la chercher.
            adresse = adresse_publique()
            print()
            print("  \033[1;33mLa cle est VALIDE : Bitvavo la reconnait et l'authentifie.\033[0m")
            print("  Elle est simplement restreinte a des adresses IP qui n'incluent")
            print("  pas celle de ce serveur.")
            if adresse:
                print(f"\n  Adresse vue par l'exterieur :  \033[1m{adresse}\033[0m")
                if ":" in adresse:
                    print("\n  \033[1;31mC'est une adresse IPv6.\033[0m Si tu as autorise une IPv4")
                    print("  dans Bitvavo, elle ne sert a rien : la plateforme ne voit")
                    print("  jamais cette adresse-la.")
                    print("\n  Deux solutions :")
                    print("    a) ajouter CETTE adresse IPv6 dans Bitvavo ;")
                    print("    b) forcer la sortie en IPv4 — ajouter dans .env :")
                    print("       \033[1mGB_FORCE_IPV4=1\033[0m")
                    print("       puis relancer. L'IPv4 autorisee redevient la bonne.")
            print("\n  Bitvavo > Parametres > API > modifier la cle >")
            print("  adresses IP autorisees. Ajoute-la, enregistre, puis relance.")
            return 5
        print("\n  Causes possibles, dans l'ordre de frequence :")
        print("    1. la cle ou le secret sont mal recopies (espace en trop) ;")
        print("    2. la cle est restreinte a une adresse IP qui n'est pas")
        print("       celle de ce serveur ;")
        print("    3. l'horloge du serveur derive de plus de 10 secondes")
        print("       (verifier avec : timedatectl).")
        return 2
    compte = broker.account()
    ok(f"solde total : {compte.equity:.2f} {config.quote_asset} "
       f"(disponible : {compte.margin_free:.2f})")

    titre("3. Droits reels de la cle et tarif du compte")
    # Bitvavo expose les droits de la cle : sans cette lecture, un refus
    # laisse le choix entre plusieurs causes ; avec elle, la cause est nommee.
    try:
        infos = broker._appel("GET", "/account")
        frais = infos.get("fees", {}) if isinstance(infos, dict) else {}
        if frais:
            taker = float(frais.get("taker", 0) or 0)
            print(f"  tarif taker du compte    : {taker * 100:.3f} %")
            print(f"  aller-retour au marche   : {taker * 200:.3f} %")
            if taker > 0:
                print(f"  stop minimum conseille   : {taker * 2 / 0.15 * 100:.2f} % du prix")
    except Exception as exc:  # noqa: BLE001
        print(f"  (informations de compte illisibles : {str(exc)[:120]})")

    titre("4. Choix de la paire de test")
    candidats = [args.paire.upper()] if args.paire else ["BTCUSD", "ETHUSD", "SOLUSD"]
    symbole = next((s for s in candidats if broker.supports(s)), "")
    if not symbole:
        echec(f"aucune paire testable parmi {', '.join(candidats)}")
        return 2

    code = broker.symbol_for(symbole)
    regle = broker.regle(symbole)
    prix = broker._prix(code)
    if not prix:
        echec(f"prix indisponible pour {code}")
        return 2
    ok(f"{code} a {formater(prix)} {config.quote_asset}")

    titre("5. Calcul de l'ordre")
    # On vise nettement au-dessus du minimum : la commission est prelevee dans
    # l'actif achete, donc la revente porte sur un peu moins que l'achat. Trop
    # juste, elle repasserait sous le minimum et resterait bloquee.
    minimum = max(regle.min_notional, 1.0)
    vise = minimum * 2.0
    quantite = regle.arrondir_quantite(vise / prix)
    if regle.min_amount and quantite < regle.min_amount:
        quantite = regle.min_amount
    notionnel = quantite * prix

    print(f"  notionnel minimum impose : {regle.min_notional:.2f} {config.quote_asset}")
    print(f"  quantite                 : {formater(quantite, regle.amount_decimals)}")
    print(f"  montant engage           : {notionnel:.2f} {config.quote_asset}")
    print(f"  frais estimes            : {notionnel * config.fee_rate * 2:.4f} "
          f"{config.quote_asset} (aller-retour)")

    if notionnel > compte.margin_free * 0.5:
        echec("l'ordre representerait plus de la moitie du solde disponible. Abandon.")
        return 2

    if config.dry_run:
        titre("Resultat du diagnostic")
        ok("la cle fonctionne, le compte est lisible, la paire est cotable")
        print("\n  Rien n'a ete envoye — et rien ne peut l'etre tant que")
        print("  BITVAVO_DRY_RUN=1 dans .env.")
        print("\n  Pour la preuve d'execution reelle, plus tard et seulement")
        print("  quand tu l'auras decide :")
        print("      1. nano .env   ->   BITVAVO_DRY_RUN=0")
        print("      2. python3 verifier_bitvavo.py --confirmer")
        return 0

    if not args.confirmer:
        print("\n  Rien n'a ete envoye. Pour executer reellement :")
        print("      python3 verifier_bitvavo.py --confirmer")
        return 0

    # A partir d'ici seulement, un broker capable d'envoyer des ordres.
    config.dry_run = False
    broker.config = config

    titre("6. ACHAT au marche")
    try:
        achat = broker._appel("POST", "/order", corps={
            "market": code, "side": "buy", "orderType": "market",
            "operatorId": config.operator_id,
            "amount": formater(quantite, regle.amount_decimals),
        })
    except Exception as exc:  # noqa: BLE001
        echec(f"achat refuse : {exc}")
        print("\n  Si le message parle de droits ou d'autorisation, la cle lit")
        print("  le compte mais n'a pas le droit « Trade ». A corriger dans")
        print("  l'espace Bitvavo : Parametres > API > modifier la cle.")
        print("  Ne cochez jamais le droit de retrait : le robot n'en a pas besoin.")
        return 3

    achete = float(achat.get("filledAmount", 0) or 0)
    depense = float(achat.get("filledAmountQuote", 0) or 0)
    ok(f"ordre {achat.get('orderId')} — {formater(achete)} achete pour "
       f"{depense:.4f} {config.quote_asset}")

    # La commission est prelevee dans l'actif recu : on relit le solde reel
    # plutot que de supposer que tout ce qui a ete achete est revendable.
    time.sleep(1.5)
    broker.sync()
    actif = code.split("-")[0]
    disponible = broker._soldes.get(actif, 0.0)
    revendable = regle.arrondir_quantite(min(achete, disponible))
    print(f"  solde {actif} apres frais : {formater(disponible)} "
          f"-> revente de {formater(revendable)}")

    titre("7. VENTE au marche")
    if revendable <= 0 or (regle.min_amount and revendable < regle.min_amount):
        echec(f"quantite revendable ({formater(revendable)}) sous le minimum. "
              f"Le {actif} reste sur le compte, a revendre a la main.")
        return 3
    try:
        vente = broker._appel("POST", "/order", corps={
            "market": code, "side": "sell", "orderType": "market",
            "operatorId": config.operator_id,
            "amount": formater(revendable, regle.amount_decimals),
        })
    except Exception as exc:  # noqa: BLE001
        echec(f"vente refusee : {exc}. Le {actif} reste sur le compte.")
        return 3

    recu = float(vente.get("filledAmountQuote", 0) or 0)
    ok(f"ordre {vente.get('orderId')} — {formater(revendable)} vendu pour "
       f"{recu:.4f} {config.quote_asset}")

    titre("Resultat")
    print(f"  cout reel de la verification : {depense - recu:.4f} {config.quote_asset}")
    print("\n  Les deux ordres sont visibles dans Bitvavo :")
    print(f"  Portefeuille > Historique des transactions, marche {code}")
    print(f"  Identifiants : {achat.get('orderId')} (achat) et "
          f"{vente.get('orderId')} (vente)\n")
    print("  La chaine d'execution du robot fonctionne de bout en bout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
