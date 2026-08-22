#!/usr/bin/env python3
"""Preuve d'execution : un aller-retour reel, minuscule, sur Binance Spot.

Le robot n'entre que sur un signal valide — c'est ce qui fait sa valeur, et
c'est aussi ce qui empeche de le « forcer » a trader pour se rassurer. Ce
script repond au meme besoin autrement : il passe un vrai ordre d'achat puis
le revend immediatement, en empruntant exactement le chemin d'execution du
robot (meme signature HMAC, meme traduction de symbole, memes arrondis de lot,
meme controle de notionnel minimum).

Ce qu'il prouve : les cles fonctionnent, la permission de trading est active,
les ordres partent, sont executes, et apparaissent dans l'historique Binance.

Ce qu'il ne prouve pas : que la strategie trouve de bonnes occasions. Cela,
seuls les trades reels du robot le diront.

Cout : les frais de l'aller-retour, soit environ 0,02 USDC sur un ordre de 10.

    python3 verifier_execution.py                 # simulation, rien n'est envoye
    python3 verifier_execution.py --confirmer     # ordres reels
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.brokers.binance import BinanceConfig, paire            # noqa: E402
from gold_bot.brokers.binance_spot import BinanceSpotBroker          # noqa: E402


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


def formater(quantite: float, regle) -> str:
    """Quantite en decimal explicite, jamais en notation scientifique.

    Envoyer 1e-05 a Binance donne « Invalid quantity » : la valeur doit etre
    ecrite en clair, avec le nombre de decimales du pas de la plateforme.
    """
    pas = regle.step_size
    if pas <= 0:
        decimales = regle.quantity_precision
    else:
        texte = f"{pas:.10f}".rstrip("0")
        decimales = len(texte.split(".")[1]) if "." in texte else 0
    return f"{quantite:.{decimales}f}"


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
                        help="symbole interne a tester, ex. BTCUSD (defaut : le premier disponible)")
    args = parser.parse_args()

    charger_env()
    config = BinanceConfig.from_env()

    titre("1. Configuration")
    print(f"  devise de cotation : {config.quote_asset}")
    print(f"  testnet            : {config.testnet}")
    print(f"  dry-run            : {config.dry_run}")

    if config.dry_run or config.testnet:
        echec("Le robot est en simulation ou sur le testnet : aucun ordre reel "
              "ne peut etre passe. Ce test n'aurait rien prouve.")
        return 2
    if not (config.api_key and config.api_secret):
        echec("Cles Binance absentes.")
        return 2
    ok("mode reel, cles presentes")

    # Le broker force le mode reel : ce script n'a de sens que la.
    config.dry_run = False
    broker = BinanceSpotBroker(config)

    titre("2. Connexion et lecture du compte")
    if not broker.connect():
        echec(f"connexion refusee : {broker._last_error}")
        return 2
    compte = broker.account()
    ok(f"solde : {compte.equity:.2f} {config.quote_asset}")

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
    ok(f"{code} a {prix:.8f}")

    titre("4. Calcul de l'ordre")
    # On vise nettement au-dessus du minimum : la commission est prelevee dans
    # l'actif achete, donc la revente porte sur un peu moins que l'achat. Trop
    # juste, elle repasserait sous le notionnel minimum et resterait bloquee.
    minimum = max(regle.min_notional, 1.0)
    vise = minimum * 2.0
    quantite = regle.arrondir_quantite(vise / prix)
    if quantite < regle.min_qty:
        quantite = regle.min_qty
    notionnel = quantite * prix

    print(f"  notionnel minimum impose : {regle.min_notional:.2f} {config.quote_asset}")
    print(f"  quantite                 : {quantite}")
    print(f"  montant engage           : {notionnel:.2f} {config.quote_asset}")
    print(f"  frais estimes            : {notionnel * 0.002:.4f} {config.quote_asset} (aller-retour)")

    if notionnel > compte.equity * 0.5:
        echec(f"l'ordre representerait plus de la moitie du solde. Abandon.")
        return 2

    if not args.confirmer:
        print("\n  Rien n'a ete envoye. Pour executer reellement :")
        print("      python3 verifier_execution.py --confirmer")
        return 0

    titre("5. ACHAT au marche")
    try:
        achat = broker._appel("POST", "/api/v3/order", {
            "symbol": code, "side": "BUY", "type": "MARKET",
            "quantity": formater(quantite, regle), "newOrderRespType": "FULL",
        })
    except Exception as exc:
        echec(f"achat refuse : {exc}")
        return 3

    achete = float(achat.get("executedQty", 0) or 0)
    depense = float(achat.get("cummulativeQuoteQty", 0) or 0)
    ok(f"ordre #{achat.get('orderId')} — {achete} achete pour {depense:.4f} {config.quote_asset}")

    # La commission est prelevee dans l'actif recu : on relit le solde reel
    # plutot que de supposer que tout ce qui a ete achete est revendable.
    time.sleep(1.5)
    broker.sync()
    actif = code[:-len(config.quote_asset)]
    disponible = broker._soldes.get(actif, 0.0)
    revendable = regle.arrondir_quantite(min(achete, disponible))
    print(f"  solde {actif} apres frais : {disponible} -> revente de {revendable}")

    titre("6. VENTE au marche")
    if revendable < regle.min_qty:
        echec(f"quantite revendable ({revendable}) sous le minimum. "
              f"Le {actif} reste sur le compte, a revendre a la main.")
        return 3
    try:
        vente = broker._appel("POST", "/api/v3/order", {
            "symbol": code, "side": "SELL", "type": "MARKET",
            "quantity": formater(revendable, regle), "newOrderRespType": "FULL",
        })
    except Exception as exc:
        echec(f"vente refusee : {exc}. Le {actif} reste sur le compte.")
        return 3

    recu = float(vente.get("cummulativeQuoteQty", 0) or 0)
    ok(f"ordre #{vente.get('orderId')} — {revendable} vendu pour {recu:.4f} {config.quote_asset}")

    titre("Resultat")
    print(f"  cout reel de la verification : {depense - recu:.4f} {config.quote_asset}")
    print(f"\n  Les deux ordres sont visibles dans Binance :")
    print(f"  Portefeuille > Spot > Historique des ordres, paire {code}")
    print(f"  Numeros : {achat.get('orderId')} (achat) et {vente.get('orderId')} (vente)\n")
    print("  La chaine d'execution du robot fonctionne de bout en bout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
