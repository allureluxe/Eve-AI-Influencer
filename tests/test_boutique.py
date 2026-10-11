"""Boutique de Noël : l'automate ne commande jamais sans validation, et en
brouillon tant que l'opérateur n'a pas dit « order »."""
import io

import pytest

from boutique import automate, gelato


class FausseBase:
    def __init__(self, commandes):
        self.c = commandes
        self.fichiers = {"portraits/x.png": _png(1024, 1536)}

    def lister(self, statut):
        return [c for c in self.c if c["statut"] == statut]

    def maj(self, c, quoi, **champs):
        c.update(champs)

    def lire(self, chemin):
        return self.fichiers[chemin]

    def ecrire(self, chemin, octets, type_):
        self.fichiers[chemin] = octets

    def lien(self, chemin, secondes):
        return "https://signe/" + chemin


def _png(l, h):
    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (l, h), "red").save(b, "PNG")
    return b.getvalue()


CAT = {"produits": [{"id": "affiche", "gelato_uid": "flat_x", "fichier": {"largeur": 1772, "hauteur": 2362}},
                    {"id": "mug", "fichier": {"largeur": 2000, "hauteur": 900, "mode": "centre"}}]}


def _commande(**k):
    return {"id": "c1", "statut": "validee", "produit": "affiche", "portrait_path": "portraits/x.png",
            "email": "a@b.fr", "prenom": "Léa", "livraison": {}, "retouches": 0, **k}


@pytest.fixture
def commandes_gelato(monkeypatch):
    envoyes = []
    monkeypatch.setattr(gelato, "commander", lambda *a, **k: envoyes.append((a, k)) or {"id": "g1"})
    monkeypatch.setattr(automate, "envoyer_mail", lambda *a: None)
    monkeypatch.setattr(automate, "alerter", lambda *a: None)
    return envoyes


def test_brouillon_par_defaut(commandes_gelato, monkeypatch):
    monkeypatch.delenv("BOUTIQUE_GELATO_MODE", raising=False)
    c = _commande()
    automate.etape_impression(FausseBase([c]), CAT)
    assert commandes_gelato[0][1]["brouillon"] is True
    assert c["statut"] == "envoyee_imprimeur" and c["gelato_order_id"] == "g1"


def test_commande_reelle_seulement_sur_order(commandes_gelato, monkeypatch):
    monkeypatch.setenv("BOUTIQUE_GELATO_MODE", "order")
    automate.etape_impression(FausseBase([_commande()]), CAT)
    assert commandes_gelato[0][1]["brouillon"] is False


def test_rien_ne_part_sans_validation_du_client(commandes_gelato):
    for statut in ("payee", "portrait_pret", "a_retoucher", "attente_paiement"):
        automate.etape_impression(FausseBase([_commande(statut=statut)]), CAT)
    assert commandes_gelato == []


def test_produit_sans_uid_attend_l_operateur(commandes_gelato):
    c = _commande(produit="mug")
    automate.etape_impression(FausseBase([c]), CAT)
    assert commandes_gelato == [] and c["statut"] == "a_verifier"


def test_fichier_au_format_du_support():
    from PIL import Image
    for fmt in CAT["produits"]:
        im = Image.open(io.BytesIO(automate.fichier_impression(_png(1024, 1536), fmt["fichier"])))
        assert im.size == (fmt["fichier"]["largeur"], fmt["fichier"]["hauteur"])


def test_adresse_stripe_vers_gelato():
    liv = automate.livraison_de({"collected_information": {"shipping_details": {
        "name": "Léa Martin", "address": {"line1": "1 rue A", "city": "Lyon", "postal_code": "69001", "country": "FR"}}},
        "customer_details": {"phone": "+33600000000"}})
    a = gelato.adresse(liv, "a@b.fr")
    assert (a["firstName"], a["lastName"], a["postCode"], a["phone"]) == ("Léa", "Martin", "69001", "+33600000000")


def test_la_consigne_garde_le_sujet_et_la_retouche():
    t = automate.consigne("royal", "Ma famille", "les yeux plus clairs")
    assert "toutes les personnes" in t and "les yeux plus clairs" in t


def test_carte_pliee_dos_blanc_couverture_a_droite():
    from PIL import Image
    im = Image.open(io.BytesIO(automate.fichier_impression(
        _png(1024, 1536), {"largeur": 2480, "hauteur": 1748, "mode": "carte"})))
    assert im.size == (2480, 1748)
    assert im.getpixel((100, 874)) == (255, 255, 255)        # dos : blanc
