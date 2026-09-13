"""Le point de marche du matin, redige par Claude et relu par du code.

Ce que fait ce module
---------------------
1. Rassemble les chiffres du jour (BTC, ETH, moyenne 50 jours, Fear &
   Greed, dominance, volatilite, agenda du jour).
2. Demande a Claude une note de trois paragraphes en francais courant.
3. **Relit la reponse** et refuse ce qui enfreint les regles.
4. Ecrit le resultat en BROUILLON. Rien n'est publie sans validation.

Pourquoi la relecture par du code
---------------------------------
Le prompt interdit de predire un prix et de promettre un gain. Un
prompt est une consigne, pas une garantie : il suffit d'une formulation
maladroite pour qu'une note dise « le bitcoin devrait atteindre
70 000 EUR ». Cette phrase-la, dans une application financiere publiee
sur le Play Store, est un probleme de conformite, pas un probleme de
style.

Le controle `verifier_la_note()` est donc une **barriere**, au meme
titre que le plafond de coût du robot : la note qui la franchit est
refusee et regeneree, et si elle echoue deux fois, rien n'est ecrit.

Et pourquoi le brouillon
------------------------
`published_at` reste nul. La note n'apparait dans l'application que
lorsqu'un humain a lu et valide, avec `valider_note.py`. Un texte
genere automatiquement et publie automatiquement dans une application
financiere n'a aucun filet.
"""

from __future__ import annotations

import json
import logging
import os
import re
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .signal_publisher import SupabaseIndisponible, SupabaseREST

log = logging.getLogger(__name__)

#: Le modele qui redige. La specification de l'application nommait
#: `claude-sonnet-4-6` ; on prend le modele courant par defaut, et la
#: variable d'environnement permet d'en changer sans toucher au code.
#: Une note par jour : le cout est negligeable dans les deux cas.
MODELE = os.getenv("EVE_MODELE_NOTE", "claude-opus-5")


# ---------------------------------------------------------------------
# Les chiffres du jour
# ---------------------------------------------------------------------

@dataclass
class Photo:
    """L'etat du marche a un instant, tel qu'affiche dans l'application."""

    btc_prix: Optional[float] = None
    btc_var_7j: Optional[float] = None
    btc_vs_ma50: Optional[float] = None      # ecart en % a la moyenne 50 j
    eth_prix: Optional[float] = None
    eth_var_7j: Optional[float] = None
    eth_vs_ma50: Optional[float] = None
    fear_greed: Optional[int] = None
    fear_greed_texte: str = ""
    dominance_btc: Optional[float] = None
    volatilite_pct: Optional[float] = None   # ATR 14 en % du prix
    evenements: List[Dict[str, Any]] = field(default_factory=list)

    # -- les scores affiches en jauges dans l'application -------------

    def trend_score(self) -> Optional[int]:
        """De -100 (baisse franche) a +100 (hausse franche).

        Moyenne de la variation 7 jours et de l'ecart a la moyenne
        50 jours, sur les deux cryptos disponibles. Une variation de
        20 % ou plus sature la jauge : au-dela, l'utilisateur n'a pas
        besoin d'un chiffre plus precis pour comprendre.
        """
        morceaux = [v for v in (self.btc_var_7j, self.btc_vs_ma50,
                                self.eth_var_7j, self.eth_vs_ma50)
                    if v is not None]
        if not morceaux:
            return None
        moyenne = sum(morceaux) / len(morceaux)
        return max(-100, min(100, round(moyenne / 20.0 * 100)))

    def volatility_score(self) -> Optional[int]:
        """De 0 (marche endormi) a 100 (marche agite).

        5 % de mouvement quotidien sature la jauge — au-dessus, la
        crypto est en crise et le detail importe peu.
        """
        if self.volatilite_pct is None:
            return None
        return max(0, min(100, round(self.volatilite_pct / 5.0 * 100)))


def _json_distant(url: str, timeout: float = 8.0) -> Optional[Any]:
    """Un GET JSON qui ne fait jamais tomber l'appelant."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "eve-bot/1"})
        with urllib.request.urlopen(req, timeout=timeout) as rep:
            return json.loads(rep.read().decode())
    except Exception as exc:                                # noqa: BLE001
        log.warning("source %s indisponible : %s", url.split("/")[2], exc)
        return None


def lire_fear_greed() -> tuple[Optional[int], str]:
    """L'indice de peur et d'avidite (alternative.me, gratuit)."""
    data = _json_distant("https://api.alternative.me/fng/?limit=1")
    try:
        entree = data["data"][0]
        traduction = {
            "Extreme Fear": "peur extreme", "Fear": "peur",
            "Neutral": "neutre", "Greed": "avidite",
            "Extreme Greed": "avidite extreme",
        }
        brut = entree.get("value_classification", "")
        return int(entree["value"]), traduction.get(brut, brut.lower())
    except (TypeError, KeyError, IndexError, ValueError):
        return None, ""


def lire_dominance() -> Optional[float]:
    """La part du bitcoin dans la capitalisation totale (CoinGecko)."""
    data = _json_distant("https://api.coingecko.com/api/v3/global")
    try:
        return round(float(data["data"]["market_cap_percentage"]["btc"]), 2)
    except (TypeError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------------
# La relecture — la partie qui protege
# ---------------------------------------------------------------------

#: Une prediction de prix : « atteindra 70 000 », « vers les 3 500 EUR ».
_PREDICTION = re.compile(
    r"(atteindra|atteindre|ira (?:jusqu')?a|montera|descendra|vise(?:ra)?|"
    r"objectif de|devrait (?:atteindre|monter|descendre|toucher)|"
    r"prevision|je prevois|d'ici (?:la )?fin)",
    re.IGNORECASE)

#: Une promesse de gain, interdite par le Play Store comme par l'honnetete.
_PROMESSE = re.compile(
    r"(garanti|assure(?:e|ment)?\b|sans risque|profit(?:s)? (?:assure|certain)|"
    r"a coup sur|certitude|vous (?:allez|gagnerez)|il faut acheter|"
    r"opportunite a ne pas manquer|argent facile|rendement garanti)",
    re.IGNORECASE)

#: Le ton alarmiste vend autant que la promesse, et fait paniquer.
_ALARMISTE = re.compile(
    r"(krach imminent|effondrement total|catastrophe|paniqu|"
    r"vendez tout|tout va s'ecrouler|desastre)",
    re.IGNORECASE)


class NoteRefusee(Exception):
    """La note enfreint une regle. Elle n'est pas ecrite."""


def verifier_la_note(titre: str, corps: str, photo: Photo) -> None:
    """Relit la note. Leve `NoteRefusee` au moindre manquement.

    Ces controles ne sont pas du confort : une prediction de prix ou une
    promesse de gain dans une application financiere est un motif de
    retrait du Play Store, et un mensonge fait a l'utilisateur.
    """
    texte = f"{titre}\n{corps}"

    for motif, quoi in ((_PREDICTION, "une prediction de prix"),
                        (_PROMESSE, "une promesse de gain"),
                        (_ALARMISTE, "un ton alarmiste")):
        trouve = motif.search(texte)
        if trouve:
            raise NoteRefusee(f"{quoi} : {trouve.group(0)!r}")

    if not titre.strip():
        raise NoteRefusee("titre vide")
    if titre.count(".") > 1:
        raise NoteRefusee("le titre doit tenir en une phrase")
    if len(corps.strip()) < 40:
        raise NoteRefusee("corps trop court (la base exige 40 caracteres)")

    paragraphes = [p for p in corps.split("\n\n") if p.strip()]
    if len(paragraphes) > 3:
        raise NoteRefusee(f"{len(paragraphes)} paragraphes, trois au maximum")

    # UNE ANNONCE IMPORTANTE NON MENTIONNEE EST UNE OMISSION, PAS UN STYLE.
    # C'est le seul jour ou l'utilisateur a besoin de la note.
    forts = [e for e in photo.evenements if e.get("impact") == "high"]
    if forts:
        noms = [e.get("name_fr", "") for e in forts]
        if not any(_mots_communs(n, texte) for n in noms if n):
            raise NoteRefusee(
                f"annonce a fort impact non mentionnee : {', '.join(noms)}")


def _mots_communs(nom: str, texte: str) -> bool:
    """Le nom de l'evenement apparait-il, meme reformule ?"""
    bas = texte.lower()
    mots = [m for m in re.split(r"\W+", nom.lower()) if len(m) > 4]
    return any(m in bas for m in mots) if mots else nom.lower() in bas


# ---------------------------------------------------------------------
# La redaction
# ---------------------------------------------------------------------

CONSIGNE = """Tu rediges la note de marche quotidienne d'une application \
de suivi de trading crypto, lue par des gens qui ne connaissent rien au \
trading.

REGLES ABSOLUES, dans l'ordre :
1. Ne predis JAMAIS un prix, un niveau ou une direction future. Decris ce \
qui s'est passe, jamais ce qui va se passer.
2. Ne promets JAMAIS un gain. Pas de "garanti", pas de "sans risque", pas \
de "il faut acheter".
3. Ton factuel et calme. Ni vendeur, ni alarmiste. Tu informes, tu ne \
conseilles pas.
4. Trois paragraphes au maximum, separes par une ligne vide. Francais \
courant, phrases courtes, aucun jargon (pas de "ATR", pas de "RSI", pas \
de "support", pas de "resistance").
5. Si une annonce economique a fort impact a lieu aujourd'hui, elle DOIT \
etre mentionnee par son nom.

Reponds UNIQUEMENT en JSON, sans texte autour :
{"titre": "une seule phrase qui dit ce qui compte aujourd'hui",
 "corps": "paragraphe 1\\n\\nparagraphe 2\\n\\nparagraphe 3"}"""


def _decrire(photo: Photo) -> str:
    """Les chiffres, mis en phrases pour le modele."""
    l: List[str] = []
    if photo.btc_prix:
        l.append(f"Bitcoin : {photo.btc_prix:,.0f} EUR, "
                 f"{photo.btc_var_7j:+.1f} % sur sept jours"
                 if photo.btc_var_7j is not None
                 else f"Bitcoin : {photo.btc_prix:,.0f} EUR")
    if photo.btc_vs_ma50 is not None:
        sens = "au-dessus" if photo.btc_vs_ma50 >= 0 else "en dessous"
        l.append(f"Bitcoin {sens} de sa moyenne des 50 derniers jours "
                 f"({photo.btc_vs_ma50:+.1f} %)")
    if photo.eth_prix:
        l.append(f"Ethereum : {photo.eth_prix:,.0f} EUR, "
                 f"{photo.eth_var_7j:+.1f} % sur sept jours"
                 if photo.eth_var_7j is not None
                 else f"Ethereum : {photo.eth_prix:,.0f} EUR")
    if photo.fear_greed is not None:
        l.append(f"Indice de peur et d'avidite : {photo.fear_greed} sur 100"
                 + (f" ({photo.fear_greed_texte})" if photo.fear_greed_texte else ""))
    if photo.dominance_btc is not None:
        l.append(f"Part du bitcoin dans le marche : {photo.dominance_btc:.1f} %")
    if photo.volatilite_pct is not None:
        l.append(f"Mouvement quotidien moyen : {photo.volatilite_pct:.1f} %")
    if photo.evenements:
        for e in photo.evenements:
            fort = " (annonce importante)" if e.get("impact") == "high" else ""
            l.append(f"Aujourd'hui : {e.get('name_fr')}{fort}")
    else:
        l.append("Aucune annonce economique notable aujourd'hui.")
    return "\n".join(f"- {x}" for x in l)


@dataclass
class RedacteurDeNote:
    """Demande la note a Claude, la relit, la depose en brouillon."""

    client_llm: Any = None
    client_base: Optional[SupabaseREST] = None
    modele: str = MODELE
    essais: int = 2

    @classmethod
    def depuis_env(cls) -> "RedacteurDeNote":
        url = os.getenv("SUPABASE_URL", "").strip()
        cle = os.getenv("SUPABASE_SERVICE_KEY", "").strip()
        llm = None
        if os.getenv("ANTHROPIC_API_KEY", "").strip():
            import anthropic
            llm = anthropic.Anthropic()
        return cls(client_llm=llm,
                   client_base=SupabaseREST(url, cle) if url and cle else None)

    # -- redaction -----------------------------------------------------

    def rediger(self, photo: Photo) -> tuple[str, str]:
        """Rend (titre, corps). Leve `NoteRefusee` si rien ne passe.

        Deux essais : le second rappelle au modele ce qui a ete refuse.
        Au-dela on abandonne — insister ferait tourner en rond et
        couterait sans rien produire de meilleur.
        """
        if self.client_llm is None:
            raise NoteRefusee("aucune cle Anthropic : pas de note aujourd'hui")

        reproche = ""
        derniere: Optional[Exception] = None
        for essai in range(self.essais):
            message = (f"Voici l'etat du marche ce matin :\n\n{_decrire(photo)}"
                       + (f"\n\nTa reponse precedente a ete refusee : "
                          f"{reproche}. Recommence en respectant les regles."
                          if reproche else ""))
            reponse = self.client_llm.messages.create(
                model=self.modele,
                max_tokens=2000,
                system=CONSIGNE,
                messages=[{"role": "user", "content": message}],
            )
            texte = "".join(b.text for b in reponse.content
                            if getattr(b, "type", "") == "text")
            try:
                titre, corps = _extraire(texte)
                verifier_la_note(titre, corps, photo)
                return titre, corps
            except NoteRefusee as exc:
                derniere = exc
                reproche = str(exc)
                log.warning("note refusee (essai %d) : %s", essai + 1, exc)

        raise NoteRefusee(f"deux essais refuses, rien n'est publie "
                          f"(dernier motif : {derniere})")

    # -- depot ---------------------------------------------------------

    def deposer(self, titre: str, corps: str, photo: Photo) -> bool:
        """Ecrit la note EN BROUILLON (`published_at` nul)."""
        if self.client_base is None:
            return False
        ligne = {
            "published_at": None,        # BROUILLON — validation humaine
            "headline": titre,
            "body_fr": corps,
            "trend_score": photo.trend_score(),
            "volatility_score": photo.volatility_score(),
            "fear_greed": photo.fear_greed,
            "btc_dominance": photo.dominance_btc,
        }
        try:
            self.client_base.inserer("market_notes", ligne)
        except SupabaseIndisponible as exc:
            log.warning("note non deposee : %s", exc)
            return False
        return True


def _extraire(texte: str) -> tuple[str, str]:
    """Sort le JSON de la reponse, meme entoure de texte."""
    debut, fin = texte.find("{"), texte.rfind("}")
    if debut < 0 or fin <= debut:
        raise NoteRefusee("reponse illisible : aucun JSON")
    try:
        obj = json.loads(texte[debut:fin + 1])
    except json.JSONDecodeError as exc:
        raise NoteRefusee(f"JSON invalide : {exc}") from exc
    titre = str(obj.get("titre", "")).strip()
    corps = str(obj.get("corps", "")).strip()
    if not titre or not corps:
        raise NoteRefusee("titre ou corps manquant")
    return titre, corps
