#!/usr/bin/env python3
"""Preuve d'execution : un aller-retour reel, minuscule, sur OKX Europe.

Le robot n'entre que sur un signal valide — c'est ce qui fait sa valeur, et
c'est aussi ce qui empeche de le « forcer » a trader pour se rassurer. Ce
script repond au meme besoin autrement : il passe un vrai ordre d'achat puis
le revend immediatement, en empruntant exactement le chemin d'execution du
robot (meme signature, meme traduction de symbole, memes arrondis).

Ce qu'il prouve : les trois identifiants fonctionnent, le droit « Trade » est
actif, les ordres partent, sont executes, et apparaissent dans l'historique.

Ce qu'il ne prouve pas : que la strategie trouve de bonnes occasions. Cela,
seuls les trades reels du robot le diront.

Cout : les frais de l'aller-retour, soit environ 0,02 EUR sur un ordre de 10.

    python3 verifier_okx.py                 # simulation, rien n'est envoye
    python3 verifier_okx.py --confirmer     # ordres reels
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.brokers.okx import OkxBroker, OkxConfig, formater   # noqa: E402


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
                        help="symbole interne a tester, ex. BTCUSD")
    args = parser.parse_args()

    charger_env()
    config = OkxConfig.from_env()

    titre("1. Configuration")
    print(f"  devise de cotation : {config.quote_asset}")
    print(f"  dry-run            : {config.dry_run}")
    print(f"  compte demo        : {config.demo}")

    if config.dry_run:
        echec("Le robot est en simulation (OKX_DRY_RUN=1) : aucun ordre reel "
              "ne peut etre passe. Ce test n'aurait rien prouve.")
        return 2
    manquants = [nom for nom, valeur in (
        ("OKX_API_KEY", config.api_key),
        ("OKX_API_SECRET", config.api_secret),
        ("OKX_PASSPHRASE", config.passphrase)) if not valeur]
    if manquants:
        echec(f"identifiant(s) absent(s) de .env : {', '.join(manquants)}")
        print("\n  OKX demande TROIS identifiants, dont une phrase secrete")
        print("  choisie a la creation de la cle. Elle n'est jamais reaffichee :")
        print("  si elle est perdue, il faut recreer une cle.")
        return 2
    ok("mode reel, les trois identifiants sont presents")

    config.dry_run = False
    broker = OkxBroker(config)

    titre("2. Connexion et lecture du compte")
    if not broker.connect():
        echec(f"connexion refusee : {broker._last_error}")
        print("\n  Causes possibles, dans l'ordre de frequence :")
        print("    1. la phrase secrete ne correspond pas a la cle ;")
        print("    2. la cle est restreinte a une adresse IP qui n'est pas")
        print("       celle de ce serveur ;")
        print("    3. l'horloge du serveur derive (verifier : timedatectl) ;")
        print("    4. le compte est sur le domaine EEE : essayer")
        print("       OKX_API_URL=https://eea.okx.com dans .env.")
        return 2
    compte = broker.account()
    ok(f"solde total : {compte.equity:.2f} {config.quote_asset} "
       f"(disponible : {compte.margin_free:.2f})")
    print(f"  tarif taker retenu : {config.fee_rate * 100:.4f} % "
          f"({config.fee_rate * 200:.4f} % aller-retour)")

    titre("3. Choix de la paire de test")
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

    titre("4. Calcul de l'ordre")
    # On vise nettement au-dessus du minimum : la commission est prelevee dans
    # l'actif achete, donc la revente porte sur un peu moins que l'achat. Trop
    # juste, elle repasserait sous le minimum et resterait bloquee.
    minimum_actif = regle.min_size or regle.lot_size
    quantite = regle.arrondir_quantite(max(minimum_actif * 3.0, 10.0 / prix))
    notionnel = quantite * prix

    print(f"  quantite minimale imposee : {formater(minimum_actif)}")
    print(f"  quantite                  : {formater(quantite)}")
    print(f"  montant engage            : {notionnel:.2f} {config.quote_asset}")
    print(f"  frais estimes             : {notionnel * config.fee_rate * 2:.4f} "
          f"{config.quote_asset} (aller-retour)")

    if notionnel > compte.margin_free * 0.5:
        echec("l'ordre representerait plus de la moitie du solde disponible. Abandon.")
        return 2

    if not args.confirmer:
        print("\n  Rien n'a ete envoye. Pour executer reellement :")
        print("      python3 verifier_okx.py --confirmer")
        return 0

    titre("5. ACHAT au marche")
    # Sans protections attachees : ce test revend tout de suite, un stop
    # pose puis annule dans la seconde n'apporterait rien et pourrait
    # bloquer la quantite au moment de la revente.
    try:
        achat = broker._appel("POST", "/api/v5/trade/order", corps={
            "instId": code, "tdMode": "cash", "side": "buy",
            "ordType": "market", "tgtCcy": "base_ccy",
            "sz": formater(quantite, regle.decimales_quantite),
        })
    except Exception as exc:  # noqa: BLE001
        echec(f"achat refuse : {exc}")
        print("\n  Si le message parle de permission, la cle lit le compte mais")
        print("  n'a pas le droit « Trade ». A corriger dans l'espace OKX :")
        print("  Profil > API > modifier la cle.")
        print("  Ne cochez jamais « Withdraw » : le robot n'en a pas besoin.")
        return 3

    identifiant = str(achat[0].get("ordId", ""))
    time.sleep(1.5)
    obtenu = broker._prix_execute(code, identifiant) or prix
    ok(f"ordre {identifiant} — {formater(quantite)} achete a {formater(obtenu)}")

    # La commission est prelevee dans l'actif recu : on relit le solde reel
    # plutot que de supposer que tout ce qui a ete achete est revendable.
    broker.sync()
    actif = code.split("-")[0]
    disponible = broker._soldes.get(actif, 0.0)
    revendable = regle.arrondir_quantite(min(quantite, disponible))
    print(f"  solde {actif} apres frais : {formater(disponible)} "
          f"-> revente de {formater(revendable)}")

    titre("6. VENTE au marche")
    if revendable <= 0 or (regle.min_size and revendable < regle.min_size):
        echec(f"quantite revendable ({formater(revendable)}) sous le minimum. "
              f"Le {actif} reste sur le compte, a revendre a la main.")
        return 3
    try:
        vente = broker._appel("POST", "/api/v5/trade/order", corps={
            "instId": code, "tdMode": "cash", "side": "sell",
            "ordType": "market", "tgtCcy": "base_ccy",
            "sz": formater(revendable, regle.decimales_quantite),
        })
    except Exception as exc:  # noqa: BLE001
        echec(f"vente refusee : {exc}. Le {actif} reste sur le compte.")
        return 3

    id_vente = str(vente[0].get("ordId", ""))
    time.sleep(1.5)
    sortie = broker._prix_execute(code, id_vente) or prix
    ok(f"ordre {id_vente} — {formater(revendable)} vendu a {formater(sortie)}")

    titre("Resultat")
    cout = quantite * obtenu - revendable * sortie
    print(f"  cout reel de la verification : {cout:.4f} {config.quote_asset}")
    print("\n  Les deux ordres sont visibles dans OKX :")
    print(f"  Trading > Historique des ordres, marche {code}")
    print(f"  Identifiants : {identifiant} (achat) et {id_vente} (vente)\n")
    print("  La chaine d'execution du robot fonctionne de bout en bout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
