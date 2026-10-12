"""L'automate de la boutique de Noël : chaque commande avance seule, du paiement
à l'expédition. Autorisé par l'opérateur le 11 oct. 2026 (« c'est bon »).

    python3 -m boutique.automate          # un passage (lancé toutes les 2 min par le timer)
    python3 -m boutique.automate --etat   # résumé des commandes par statut

Un passage fait, dans l'ordre :
  1. attente_paiement -> payee        Stripe dit « paid » (adresse lue chez Stripe)
                      -> annulee      session expirée (la photo est effacée)
  2. payee / a_retoucher -> portrait_pret   portrait généré d'après la photo,
                                            lien d'aperçu envoyé au client
  3. validee -> envoyee_imprimeur     fichier haute définition + commande Gelato
  4. envoyee_imprimeur -> expediee    suivi envoyé au client

Garde-fous :
  - rien n'est imprimé sans le « valider » du client (fonction boutique-apercu) ;
  - plafond de dépense d'images par jour (BOUTIQUE_BUDGET_JOUR_EUR, défaut 3 €) :
    plein, la commande attend le lendemain au lieu d'échouer ;
  - BOUTIQUE_GELATO_MODE=draft (DÉFAUT) : Gelato reçoit des BROUILLONS, ni payés
    ni imprimés, à confirmer sur leur tableau de bord. Ne passer à « order »
    qu'avec l'accord de l'opérateur, après une commande d'essai reçue et jugée bonne ;
  - toute erreur met la commande « a_verifier » et prévient l'opérateur
    (BOUTIQUE_ALERTE_EMAIL) : jamais de boucle qui redépense.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import smtplib
import sys
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
CATALOGUE = RACINE / "docs" / "kit" / "noel" / "catalogue.json"
SEAU = "boutique"
log = logging.getLogger("boutique")

STYLES = {
    "royal": "un portrait peint à l'huile de style XVIIIe, pull de Noël tricoté rouge et blanc, "
             "fond vert sapin profond avec bokeh doré",
    "aquarelle": "une aquarelle douce et lumineuse, bonnet ou écharpe de Noël, touches de houx "
                 "et flocons de neige, fond clair",
    "conte": "une illustration de livre pour enfants, pyjamas de Noël assortis, devant une "
             "cheminée et un sapin illuminé",
    # 12 oct. : l'opérateur veut tout le monde, pas que les animaux. JAMAIS de personnage
    # ou de marque existants (Disney, Marvel, stars…) : contrefaçon. Tout est inventé.
    "pere-noel": "une photo de Noël féerique où chaque sujet porte un costume de Père Noël, de "
                 "Mère Noël ou de lutin, dans l'atelier du Père Noël avec jouets et guirlandes",
    "super-heros": "une affiche de film de super-héros ORIGINALE : costume, cape et masque "
                   "inventés aux couleurs rouge et or de Noël, ville enneigée la nuit, sans aucun "
                   "logo ni emblème de personnage existant",
    "animation": "une image de film d'animation 3D familial, personnages ORIGINAUX au rendu doux "
                 "et expressif, village enneigé illuminé, sans ressembler à un personnage existant",
    "amoureux": "un portrait romantique de Noël : le couple enlacé sous une branche de gui, "
                "lumières dorées, neige légère, tons rouges et chauds, regard tendre",
    "neige": "une photo de Noël réaliste sous la neige qui tombe, manteau et écharpe d'hiver, "
             "marché de Noël illuminé en arrière-plan, lumière dorée",
}

ANIMAUX = {"Mon chien", "Mon chat", "Un autre animal"}


def consigne(style: str, sujet: str, note: str = "") -> str:
    if sujet in ANIMAUX:
        qui = "l'animal de la photo"
    elif sujet == "Mon bébé":
        qui = "le bébé de la photo, avec un rendu tendre et adapté à son âge"
    else:
        qui = "toutes les personnes et animaux de la photo"
    texte = (f"Transforme cette photo en {STYLES[style]}. Garde exactement {qui} : visages, "
             "pelage, couleurs, marques distinctives et expression doivent rester reconnaissables. "
             "Tenues correctes et adaptées à tous les âges. Cadrage centré, portrait. "
             "Aucun texte, aucun logo, aucun personnage ni marque existants.")
    if note:
        texte += f" Correction demandée par le client : {note}"
    return texte


def maintenant() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------- Supabase
class Base:
    def __init__(self) -> None:
        self.url = os.environ["SUPABASE_URL"].rstrip("/")
        self.cle = os.environ["SUPABASE_SERVICE_KEY"]

    def _req(self, methode: str, chemin: str, corps: bytes | None = None, type_: str = "application/json",
             entetes: dict | None = None) -> bytes:
        req = urllib.request.Request(f"{self.url}{chemin}", data=corps, method=methode, headers={
            "apikey": self.cle, "Authorization": f"Bearer {self.cle}", "Content-Type": type_, **(entetes or {})})
        return urllib.request.urlopen(req, timeout=120).read()

    def lister(self, statut: str) -> list[dict]:
        return json.loads(self._req("GET", f"/rest/v1/boutique_commandes?statut=eq.{statut}&order=cree_le.asc"))

    def maj(self, c: dict, quoi: str, **champs) -> None:
        champs["journal"] = (c.get("journal") or []) + [{"quand": maintenant(), "quoi": quoi}]
        champs["maj_le"] = maintenant()
        self._req("PATCH", f"/rest/v1/boutique_commandes?id=eq.{c['id']}", json.dumps(champs).encode())
        c.update(champs)

    def lire(self, chemin: str) -> bytes:
        return self._req("GET", f"/storage/v1/object/{SEAU}/{chemin}")

    def ecrire(self, chemin: str, octets: bytes, type_: str) -> None:
        self._req("POST", f"/storage/v1/object/{SEAU}/{chemin}", octets, type_, {"x-upsert": "true"})

    def effacer(self, chemin: str) -> None:
        self._req("DELETE", f"/storage/v1/object/{SEAU}", json.dumps({"prefixes": [chemin]}).encode())

    def lien(self, chemin: str, secondes: int) -> str:
        r = json.loads(self._req("POST", f"/storage/v1/object/sign/{SEAU}/{chemin}",
                                 json.dumps({"expiresIn": secondes}).encode()))
        return f"{self.url}/storage/v1{r['signedURL']}"


# ----------------------------------------------------------------------- Stripe
def session_stripe(session_id: str) -> dict:
    req = urllib.request.Request(f"https://api.stripe.com/v1/checkout/sessions/{session_id}",
                                 headers={"Authorization": f"Bearer {os.environ['STRIPE_SECRET_KEY']}"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def livraison_de(session: dict) -> dict:
    """L'adresse a changé de place selon les versions de l'API Stripe : on lit les deux."""
    exp = (session.get("collected_information") or {}).get("shipping_details") \
        or session.get("shipping_details") or {}
    client = session.get("customer_details") or {}
    return {"nom": exp.get("name") or client.get("name") or "", "adresse": exp.get("address") or {},
            "telephone": client.get("phone") or ""}


# ------------------------------------------------------------------- Courriels
#: signature des courriels clients : le « flyer » alluxe.ia (12 oct., demande de l'opérateur ;
#: un flyer imprimé coûtait 13,40 EUR par colis chez Gelato, d'où la version numérique).
SIGNATURE = ("\n\nalluxe · Portraits de Noël\n\n"
             "P.S. Votre portrait est fait avec l'IA. Pour votre activité, alluxe.ia crée aussi sites, "
             "boutiques en ligne, contenus de Noël et agents IA, à petit prix : https://alluxe.fr/offres.html")


def envoyer_mail(a: str, sujet: str, texte: str) -> None:
    hote, port = os.getenv("SMTP_HOTE", "smtp.gmail.com"), int(os.getenv("SMTP_PORT", "587"))
    utilisateur, mdp = os.getenv("SMTP_UTILISATEUR", ""), os.getenv("SMTP_MOTDEPASSE", "")
    if not (utilisateur and mdp and a):
        log.warning("courriel non envoyé (SMTP ou destinataire absent) : %s", sujet)
        return
    m = EmailMessage()
    m["From"] = os.getenv("BOUTIQUE_EXPEDITEUR", utilisateur)
    m["To"], m["Subject"] = a, sujet
    m.set_content(texte)
    with smtplib.SMTP(hote, port, timeout=30) as s:
        s.starttls()
        s.login(utilisateur, mdp)
        s.send_message(m)


def alerter(c: dict, pourquoi: str) -> None:
    envoyer_mail(os.getenv("BOUTIQUE_ALERTE_EMAIL", ""), f"[boutique] commande à vérifier : {pourquoi[:60]}",
                 f"Commande {c['id']} ({c.get('produit')}, {c.get('email')}).\n\n{pourquoi}\n\n"
                 "Statut passé à « a_verifier » : l'automate n'y touche plus.")


# ------------------------------------------------------------------ Les images
def generer_portrait(photo: bytes, consigne_: str) -> bytes:
    from luna.budget import Depenses
    from luna.moteurs import GenerateurImages
    Depenses(plafond_eur=float(os.getenv("BOUTIQUE_BUDGET_JOUR_EUR", "3")),
             fichier=RACINE / "data" / "boutique_depenses.json").reserver(
        float(os.getenv("LUNA_COUT_IMAGE_EUR", "0.07")), "portrait client")
    brut = GenerateurImages._requeter_multipart(
        "https://api.openai.com/v1/images/edits", os.environ["OPENAI_API_KEY"],
        champs={"model": os.getenv("LUNA_IMAGE_MODELE_OPENAI", "gpt-image-2"), "prompt": consigne_,
                "size": "1024x1536", "n": "1"},
        fichiers={"image[]": ("photo.jpg", photo, "image/jpeg")})
    d = json.loads(brut)["data"][0]
    return base64.b64decode(d["b64_json"]) if d.get("b64_json") else urllib.request.urlopen(d["url"]).read()


def fichier_impression(portrait: bytes, fmt: dict) -> bytes:
    """Recadre au format du support puis agrandit à sa taille d'impression.
    fmt = {"largeur": px, "hauteur": px, "mode": "plein"|"centre"} (catalogue.json)."""
    from PIL import Image
    im = Image.open(io.BytesIO(portrait)).convert("RGB")
    L, H = fmt["largeur"], fmt["hauteur"]
    if fmt.get("mode") == "carte":                  # carte pliée : dos blanc à gauche, portrait en couverture à droite
        fond = Image.new("RGB", (L, H), "white")
        demi = L // 2
        cible = demi / H
        if im.width / im.height > cible:
            w = round(im.height * cible)
            im = im.crop(((im.width - w) // 2, 0, (im.width - w) // 2 + w, im.height))
        else:
            h = round(im.width / cible)
            im = im.crop((0, (im.height - h) // 2, im.width, (im.height - h) // 2 + h))
        fond.paste(im.resize((L - demi, H), Image.LANCZOS), (demi, 0))
        im = fond
    elif fmt.get("mode") == "centre":                 # mug : portrait au centre d'un fond blanc
        fond = Image.new("RGB", (L, H), "white")
        w = round(im.width * H / im.height)
        fond.paste(im.resize((w, H), Image.LANCZOS), ((L - w) // 2, 0))
        im = fond
    else:                                           # affiche, toile : recadrage centré puis agrandissement
        cible = L / H
        if im.width / im.height > cible:
            w = round(im.height * cible)
            im = im.crop(((im.width - w) // 2, 0, (im.width - w) // 2 + w, im.height))
        else:
            h = round(im.width / cible)
            im = im.crop((0, (im.height - h) // 2, im.width, (im.height - h) // 2 + h))
        im = im.resize((L, H), Image.LANCZOS)
    sortie = io.BytesIO()
    im.save(sortie, "JPEG", quality=95, dpi=(150, 150))
    return sortie.getvalue()


# --------------------------------------------------------------------- Étapes
def catalogue() -> dict:
    return json.loads(CATALOGUE.read_text())


def produit(cat: dict, pid: str) -> dict:
    return next(p for p in cat["produits"] if p["id"] == pid)


def etape_paiements(base: Base) -> None:
    for c in base.lister("attente_paiement"):
        s = session_stripe(c["stripe_session_id"])
        if s.get("payment_status") == "paid":
            base.maj(c, "payée (Stripe)", statut="payee", livraison=livraison_de(s))
        elif s.get("status") == "expired":
            base.effacer(c["photo_path"])
            base.maj(c, "session expirée, photo effacée", statut="annulee")


def etape_portraits(base: Base, base_url: str) -> None:
    from luna.budget import BudgetEpuise
    for statut in ("payee", "a_retoucher"):
        for c in base.lister(statut):
            note = (c.get("note_retouche") or "") if statut == "a_retoucher" else ""
            try:
                image = generer_portrait(base.lire(c["photo_path"]), consigne(c["style"], c["sujet"], note))
            except BudgetEpuise:
                log.warning("plafond d'images atteint : %s attend demain", c["id"])
                return
            n = c["retouches"] + (1 if statut == "a_retoucher" else 0)
            chemin = f"portraits/{c['id']}-{n}.png"
            base.ecrire(chemin, image, "image/png")
            base.maj(c, f"portrait {n} généré", statut="portrait_pret", portrait_path=chemin, retouches=n)
            envoyer_mail(c["email"], "Votre portrait de Noël est prêt — à vous de valider",
                         f"Bonjour {c['prenom']},\n\nVotre portrait est prêt. Regardez-le ici :\n"
                         f"{base_url}/apercu.html?j={c['jeton']}\n\n"
                         "S'il vous plaît, cliquez « Valider » et nous l'imprimons. Sinon, dites-nous "
                         "quoi changer : rien n'est imprimé sans votre accord." + SIGNATURE)


def etape_impression(base: Base, cat: dict) -> None:
    from boutique import gelato
    brouillon = os.getenv("BOUTIQUE_GELATO_MODE", "draft") != "order"
    for c in base.lister("validee"):
        p = produit(cat, c["produit"])
        if not p.get("gelato_uid") or not p.get("fichier"):
            base.maj(c, "produit sans gelato_uid", statut="a_verifier")
            alerter(c, f"Le produit {p['id']} n'a pas de gelato_uid ou de format de fichier dans catalogue.json.")
            continue
        chemin = f"impression/{c['id']}.jpg"
        base.ecrire(chemin, fichier_impression(base.lire(c["portrait_path"]), p["fichier"]), "image/jpeg")
        try:
            o = gelato.commander(c["id"], p["gelato_uid"], base.lien(chemin, 14 * 86400),
                                 c.get("livraison") or {}, c["email"], brouillon=brouillon)
        except gelato.ErreurGelato as e:
            base.maj(c, f"Gelato a refusé : {e}", statut="a_verifier", erreur=str(e)[:500], impression_path=chemin)
            alerter(c, f"Gelato a refusé la commande : {e}")
            continue
        base.maj(c, f"commande Gelato {o.get('id')} ({'brouillon' if brouillon else 'réelle'})",
                 statut="envoyee_imprimeur", gelato_order_id=o.get("id"), impression_path=chemin)
        envoyer_mail(c["email"], "Votre portrait part à l'impression",
                     f"Bonjour {c['prenom']},\n\nMerci ! Votre portrait est en fabrication. Vous recevrez le "
                     "lien de suivi dès l'expédition." + SIGNATURE)


def etape_expeditions(base: Base) -> None:
    from boutique import gelato
    for c in base.lister("envoyee_imprimeur"):
        e = gelato.etat(c["gelato_order_id"])
        if e["statut"] in ("shipped", "delivered") or e["suivi"]:
            base.maj(c, f"expédiée ({e['statut']})", statut="expediee", suivi_url=e["suivi"] or None)
            envoyer_mail(c["email"], "Votre portrait de Noël est en route",
                         f"Bonjour {c['prenom']},\n\nVotre colis est parti."
                         + (f" Suivi : {e['suivi']}" if e["suivi"] else "") + SIGNATURE)
        elif e["statut"] in ("canceled", "failed"):
            base.maj(c, f"Gelato : {e['statut']}", statut="a_verifier")
            alerter(c, f"Gelato indique « {e['statut']} ».")


def passage(base: Base | None = None) -> None:
    base = base or Base()
    base_url = os.getenv("BOUTIQUE_BASE_URL", "https://alluxe.fr/noel")
    cat = catalogue()
    etapes = [("portraits", lambda: etape_portraits(base, base_url))]
    if os.getenv("STRIPE_SECRET_KEY"):
        etapes.insert(0, ("paiements", lambda: etape_paiements(base)))
    if os.getenv("GELATO_API_KEY"):
        etapes += [("impression", lambda: etape_impression(base, cat)),
                   ("expeditions", lambda: etape_expeditions(base))]
    for nom, etape in etapes:
        try:
            etape()
        except Exception:                                   # noqa: BLE001
            log.exception("étape %s en échec ; reprise au prochain passage", nom)


def main() -> int:
    sys.path.insert(0, str(RACINE))
    from gold_bot.env import charger_env
    charger_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if "--etat" in sys.argv:
        base = Base()
        for s in ("attente_paiement", "payee", "portrait_pret", "a_retoucher", "validee",
                  "envoyee_imprimeur", "expediee", "a_verifier", "annulee"):
            n = len(base.lister(s))
            if n:
                print(f"{s:20s} {n}")
        return 0
    passage()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
