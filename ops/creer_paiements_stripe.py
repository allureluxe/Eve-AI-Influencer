"""Crée (ou met à jour) les liens de paiement Stripe d'alluxe.fr.

    python3 ops/creer_paiements_stripe.py            # montre ce qui serait créé, ne crée rien
    python3 ops/creer_paiements_stripe.py --creer    # crée chez Stripe, écrit docs/kit/paiements.json

Les prix viennent de docs/kit/offres.json, SEULE source (décision du 4 oct.).
Les CGV fixent le découpage, ce script le suit :
  - paiement unique  : acompte de 30 % au lancement, solde à la livraison ;
  - au mois          : abonnement mensuel (engagement 12 mois, rappelé au paiement) ;
  - agent IA         : installation + abonnement, dans le même paiement.

Un lien déjà créé pour le même montant est réutilisé : relancer le script
après un changement de prix ne recrée que ce qui a changé, et désactive
l'ancien lien pour qu'aucun client ne paie un prix périmé.

PayPal : PAYPAL_CLIENT_ID dans .env (identifiant public de l'appli PayPal
« Live »), recopié tel quel dans paiements.json pour le bouton PayPal.

Clé dans .env : STRIPE_SECRET_KEY (une clé RESTREINTE suffit et vaut mieux :
écriture sur Products, Prices, Payment Links ; rien d'autre).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
OFFRES = RACINE / "docs" / "kit" / "offres.json"
SORTIE = RACINE / "docs" / "kit" / "paiements.json"
SITE = "https://alluxe.fr"
ACOMPTE = 0.30


def montants(offre: dict) -> dict[str, dict]:
    """Ce qu'il faut encaisser pour une offre, en centimes, par étape."""
    unique = round(offre["unique"] * 100)
    mensuel = round(offre["mensuel"] * 100)
    if offre.get("abonnement_obligatoire"):
        return {"mensuel": {"unique": unique, "mensuel": mensuel,
                            "libelle": f"{offre['nom']} — installation + abonnement"}}
    acompte = round(unique * ACOMPTE)
    etapes = {
        "acompte": {"unique": acompte, "libelle": f"{offre['nom']} — acompte 30 %"},
        "solde": {"unique": unique - acompte, "libelle": f"{offre['nom']} — solde à la livraison"},
    }
    if not offre.get("unique_seulement"):              # packs de Noël, kit UGC, clip : pas de formule au mois
        etapes["mensuel"] = {"mensuel": mensuel, "libelle": f"{offre['nom']} — abonnement mensuel"}
    return etapes


def _stripe(methode: str, chemin: str, donnees: dict | None = None) -> dict:
    cle = os.environ["STRIPE_SECRET_KEY"]
    corps = urllib.parse.urlencode(donnees or {}).encode() if donnees else None
    req = urllib.request.Request(f"https://api.stripe.com/v1/{chemin}", data=corps, method=methode,
                                 headers={"authorization": f"Bearer {cle}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Stripe refuse {chemin} : {e.read().decode()[:400]}") from None


def _prix(produit: str, centimes: int, mensuel: bool) -> str:
    d = {"product": produit, "currency": "eur", "unit_amount": centimes}
    if mensuel:
        d["recurring[interval]"] = "month"
    return _stripe("POST", "prices", d)["id"]


def creer_lien(offre: dict, etape: str, m: dict) -> dict:
    produit = _stripe("POST", "products", {"name": m["libelle"],
                                           "metadata[alluxe]": f"{offre['id']}:{etape}"})["id"]
    lignes = []
    if "unique" in m:
        lignes.append(_prix(produit, m["unique"], mensuel=False))
    if "mensuel" in m:
        lignes.append(_prix(produit, m["mensuel"], mensuel=True))
    d = {
        "after_completion[type]": "redirect",
        "after_completion[redirect][url]": f"{SITE}/merci.html?offre={offre['id']}&etape={etape}",
        "billing_address_collection": "required",
        "metadata[alluxe]": f"{offre['id']}:{etape}",
        "custom_text[submit][message]": (
            "En payant, tu acceptes les conditions générales de vente (alluxe.fr/cgv)."
            + (" Abonnement : engagement 12 mois, puis résiliable avec un mois de préavis."
               if "mensuel" in m else "")),
    }
    for i, prix in enumerate(lignes):
        d[f"line_items[{i}][price]"] = prix
        d[f"line_items[{i}][quantity]"] = 1
    if "mensuel" not in m:
        d["invoice_creation[enabled]"] = "true"     # facture envoyée au client
    lien = _stripe("POST", "payment_links", d)
    return {"url": lien["url"], "id": lien["id"], "montants": {k: v for k, v in m.items() if k != "libelle"}}


def main() -> int:
    sys.path.insert(0, str(RACINE))
    from gold_bot.env import charger_env
    charger_env()
    creer = "--creer" in sys.argv
    offres = json.loads(OFFRES.read_text(encoding="utf-8"))["offres"]
    ancien = json.loads(SORTIE.read_text(encoding="utf-8")) if SORTIE.exists() else {}
    stripe_ancien = ancien.get("stripe", {})
    if creer and not os.environ.get("STRIPE_SECRET_KEY"):
        raise SystemExit("STRIPE_SECRET_KEY absente de .env")

    stripe: dict[str, dict] = {}
    for offre in offres:
        for etape, m in montants(offre).items():
            garde = stripe_ancien.get(offre["id"], {}).get(etape)
            voulu = {k: v for k, v in m.items() if k != "libelle"}
            if garde and garde.get("montants") == voulu:
                stripe.setdefault(offre["id"], {})[etape] = garde
                continue
            euros = " + ".join(f"{v / 100:.2f} €{' /mois' if k == 'mensuel' else ''}" for k, v in voulu.items())
            print(f"{'CRÉE' if creer else 'à créer'} : {m['libelle']} ({euros})")
            if not creer:
                continue
            stripe.setdefault(offre["id"], {})[etape] = creer_lien(offre, etape, m)
            if garde:                                       # l'ancien prix ne doit plus être payable
                _stripe("POST", f"payment_links/{garde['id']}", {"active": "false"})

    if creer:
        sortie = {"_note": "Généré par ops/creer_paiements_stripe.py — ne pas modifier à la main.",
                  "stripe": stripe,
                  # Identifiant PUBLIC PayPal (pas un secret : il est lu par le navigateur).
                  "paypal_client_id": os.environ.get("PAYPAL_CLIENT_ID", ancien.get("paypal_client_id", ""))}
        SORTIE.write_text(json.dumps(sortie, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"écrit : {SORTIE.relative_to(RACINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
