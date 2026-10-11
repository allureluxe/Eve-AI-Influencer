"""L'imprimeur : Gelato (impression à la demande, fabriqué près du client).

    python3 -m boutique.gelato catalogues               # liste les catalogues
    python3 -m boutique.gelato chercher posters         # productUid candidats d'un catalogue
    python3 -m boutique.gelato devis <productUid> FR    # prix réel fabrication + port

Clé dans .env : GELATO_API_KEY (tableau de bord Gelato > Developer > API keys).
Endpoints : https://dashboard.gelato.com/docs/ (Order API v4, Product API v3).

Le productUid de chaque produit vit dans docs/kit/noel/catalogue.json
(« gelato_uid »), jamais ici : un produit sans uid ne peut pas être commandé
et l'automate le met « a_verifier » au lieu de deviner.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

ORDRES = "https://order.gelatoapis.com/v4/orders"
PRODUITS = "https://product.gelatoapis.com/v3"


class ErreurGelato(RuntimeError):
    pass


def _appel(methode: str, url: str, corps: dict | None = None) -> dict:
    cle = os.getenv("GELATO_API_KEY", "")
    if not cle:
        raise ErreurGelato("GELATO_API_KEY absente")
    req = urllib.request.Request(url, method=methode,
                                 data=json.dumps(corps).encode() if corps is not None else None,
                                 headers={"X-API-KEY": cle, "Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=60).read() or b"{}")
    except urllib.error.HTTPError as e:
        raise ErreurGelato(f"HTTP {e.code} : {e.read()[:500]!r}") from e


def adresse(livraison: dict, email: str) -> dict:
    """Adresse Stripe (customer_details / shipping_details) -> adresse Gelato."""
    nom = (livraison.get("nom") or "").strip()
    prenom, _, famille = nom.partition(" ")
    a = livraison.get("adresse") or {}
    return {"firstName": prenom or nom, "lastName": famille or prenom or nom,
            "addressLine1": a.get("line1") or "", "addressLine2": a.get("line2") or "",
            "city": a.get("city") or "", "postCode": a.get("postal_code") or "",
            "state": a.get("state") or "", "country": a.get("country") or "FR",
            "email": email, "phone": livraison.get("telephone") or ""}


def commander(commande_id: str, uid: str, fichier_url: str, livraison: dict, email: str,
              brouillon: bool = False) -> dict:
    """Passe la commande. `brouillon` = commande « draft », visible chez Gelato
    mais ni payée ni imprimée : pour les premiers essais."""
    return _appel("POST", ORDRES, {
        "orderType": "draft" if brouillon else "order",
        "orderReferenceId": commande_id,
        "customerReferenceId": email,
        "currency": "EUR",
        "items": [{"itemReferenceId": commande_id, "productUid": uid, "quantity": 1,
                   "files": [{"type": "default", "url": fichier_url}]}],
        "shipmentMethodUid": "standard",
        "shippingAddress": adresse(livraison, email),
    })


def etat(order_id: str) -> dict:
    """fulfillmentStatus, et le suivi quand il existe."""
    o = _appel("GET", f"{ORDRES}/{order_id}")
    suivi = ""
    for envoi in o.get("shipment", {}).get("packages", []) or []:
        suivi = envoi.get("trackingUrl") or suivi
    return {"statut": o.get("fulfillmentStatus", ""), "suivi": suivi}


def devis(uid: str, pays: str = "FR") -> dict:
    return _appel("POST", f"{ORDRES}:quote", {
        "orderReferenceId": "devis", "customerReferenceId": "devis", "currency": "EUR",
        "recipient": {"country": pays, "firstName": "A", "lastName": "B", "addressLine1": "1 rue",
                      "city": "Paris", "postCode": "75001", "email": "devis@alluxe.fr"},
        "products": [{"itemReferenceId": "1", "productUid": uid, "quantity": 1}]})


def main() -> int:
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from gold_bot.env import charger_env
    charger_env()
    cmd = sys.argv[1:] or ["catalogues"]
    if cmd[0] == "catalogues":
        for c in _appel("GET", f"{PRODUITS}/catalogs").get("data", []):
            print(c.get("catalogUid"), "-", c.get("title"))
    elif cmd[0] == "chercher":
        r = _appel("POST", f"{PRODUITS}/catalogs/{cmd[1]}/products:search", {"limit": 100})
        for p in r.get("products", []):
            print(p.get("productUid"))
    elif cmd[0] == "devis":
        print(json.dumps(devis(cmd[1], cmd[2] if len(cmd) > 2 else "FR"), indent=2)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
