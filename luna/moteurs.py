"""Les moteurs de generation : texte, voix, images, avatar video.

Luna ne depend d'aucun fournisseur en particulier. Chaque capacite passe
par une interface minuscule, et l'application choisit l'implementation
selon ce qui est configure dans `.env` :

    texte   MoteurClaude          API Anthropic (defaut)
            MoteurCompatibleOpenAI  n'importe quel endpoint /chat/completions
                                    (fournisseur adulte, modele auto-heberge,
                                    passerelle locale...)
            MoteurHorsLigne       repli sans reseau, pour tester l'app

    image   GenerateurImages      endpoint configurable (Stability par
                                  defaut, ou le tien)

    voix    (dans voix.py)        navigateur par defaut, prestataire au choix
    video   (dans avatar.py)      avatar dessine en local, ou prestataire

C'est le point d'integration demande : pour un registre adulte explicite,
tu branches ici le fournisseur de ton choix — l'URL, la cle et le modele
sont a toi, et c'est sa politique de contenu qui s'applique. Le depot ne
livre aucun contenu explicite.
"""
from __future__ import annotations

import json
import logging
import os
import random
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)

TIMEOUT = 60

# Sans User-Agent, urllib envoie "Python-urllib/x.y" -- plusieurs pare-feux
# (Stability, Groq, tous deux passes par Cloudflare) le bloquent avant meme
# de lire la cle, avec un message opaque (erreur 1010) qui ressemble a un
# probleme de cle. Un User-Agent de navigateur suffit. Decouvert le 15 sept.
ENTETE_NAVIGATEUR = {"user-agent": "Mozilla/5.0 (X11; Linux x86_64) luna/1.0"}


class ErreurMoteur(RuntimeError):
    pass


class Moteur:
    """Interface commune. `repondre` rend le texte de Luna."""

    nom = "abstrait"
    disponible = False

    def repondre(self, systeme: str, tours: list[dict]) -> str:
        raise NotImplementedError


# --------------------------------------------------------------------------
class MoteurClaude(Moteur):
    """API Messages d'Anthropic, en urllib : aucune dependance a installer."""

    nom = "claude"
    URL = "https://api.anthropic.com/v1/messages"
    VERSION = "2023-06-01"

    def __init__(self, cle: str = "", modele: str = "", max_tokens: int = 700,
                 temperature: float = 0.9):
        self.cle = cle or os.getenv("ANTHROPIC_API_KEY", "")
        self.modele = modele or os.getenv("LUNA_MODELE", "claude-sonnet-5")
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    def disponible(self) -> bool:  # type: ignore[override]
        return bool(self.cle)

    def repondre(self, systeme: str, tours: list[dict]) -> str:
        if not self.cle:
            raise ErreurMoteur("ANTHROPIC_API_KEY absente")
        corps = {
            "model": self.modele,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": systeme,
            "messages": [{"role": t["role"], "content": t["texte"]} for t in tours],
        }
        requete = urllib.request.Request(
            self.URL,
            data=json.dumps(corps).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self.cle,
                "anthropic-version": self.VERSION,
                **ENTETE_NAVIGATEUR,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(requete, timeout=TIMEOUT) as r:
                reponse = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise ErreurMoteur(f"HTTP {e.code} : {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurMoteur(f"reseau : {e}") from e
        morceaux = [b.get("text", "") for b in reponse.get("content", [])
                    if b.get("type") == "text"]
        texte = "".join(morceaux).strip()
        if not texte:
            raise ErreurMoteur("reponse vide")
        return texte


# --------------------------------------------------------------------------
class MoteurCompatibleOpenAI(Moteur):
    """Tout endpoint qui parle `/v1/chat/completions`.

    C'est le format de fait : OpenAI, les passerelles locales (llama.cpp,
    Ollama, vLLM, LM Studio), et la majorite des fournisseurs specialises
    dans les personnages adultes l'exposent. Renseigne LUNA_API_URL,
    LUNA_API_KEY et LUNA_API_MODELE et le reste de l'application ne change
    pas d'une ligne.

    La politique de contenu appliquee est celle de l'endpoint choisi. A toi
    de verifier qu'il autorise l'usage vise, et que ton pays et ton
    processeur de paiement le permettent si tu exploites le service.
    """

    nom = "compatible-openai"

    def __init__(self, url: str = "", cle: str = "", modele: str = "",
                 max_tokens: int = 700, temperature: float = 0.9):
        self.url = (url or os.getenv("LUNA_API_URL", "")).rstrip("/")
        self.cle = cle or os.getenv("LUNA_API_KEY", "")
        self.modele = modele or os.getenv("LUNA_API_MODELE", "")
        self.max_tokens = max_tokens
        self.temperature = temperature

    @property
    def disponible(self) -> bool:  # type: ignore[override]
        return bool(self.url and self.modele)

    def _endpoint(self) -> str:
        if self.url.endswith("/chat/completions"):
            return self.url
        return self.url + "/chat/completions"

    def repondre(self, systeme: str, tours: list[dict]) -> str:
        if not self.disponible:
            raise ErreurMoteur("LUNA_API_URL ou LUNA_API_MODELE absent")
        messages = [{"role": "system", "content": systeme}]
        messages += [{"role": t["role"], "content": t["texte"]} for t in tours]
        corps = {
            "model": self.modele,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        entetes = {"content-type": "application/json", **ENTETE_NAVIGATEUR}
        if self.cle:
            entetes["authorization"] = f"Bearer {self.cle}"
        requete = urllib.request.Request(
            self._endpoint(), data=json.dumps(corps).encode("utf-8"),
            headers=entetes, method="POST")
        try:
            with urllib.request.urlopen(requete, timeout=TIMEOUT) as r:
                reponse = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise ErreurMoteur(f"HTTP {e.code} : {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurMoteur(f"reseau : {e}") from e
        try:
            texte = reponse["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, AttributeError, TypeError) as e:
            raise ErreurMoteur(f"reponse inattendue : {str(reponse)[:200]}") from e
        if not texte:
            raise ErreurMoteur("reponse vide")
        return texte


# --------------------------------------------------------------------------
class MoteurHorsLigne(Moteur):
    """Repli sans reseau.

    Il ne remplace pas un modele : il permet d'ouvrir l'application, de
    tester l'interface, les appels et la visio sans aucune cle. Luna y dit
    d'ailleurs qu'elle est en mode hors ligne plutot que de faire semblant.
    """

    nom = "hors-ligne"
    disponible = True

    PHRASES = (
        "Je suis la 😊 mais je tourne en mode hors ligne : aucune cle API "
        "n'est configuree, alors je ne peux pas vraiment te repondre.",
        "Hmm 😅 pas de moteur branche pour l'instant. Ajoute ANTHROPIC_API_KEY "
        "dans ton .env et je redeviens bavarde.",
        "Mode demo : l'interface marche, la voix marche, la visio marche — "
        "il me manque juste un cerveau 😂 (une cle API, en fait).",
    )

    def repondre(self, systeme: str, tours: list[dict]) -> str:
        return random.choice(self.PHRASES)


# --------------------------------------------------------------------------
class MoteurAvecRepli(Moteur):
    """Essaie plusieurs moteurs DANS L'ORDRE jusqu'a ce que l'un reponde.

    Meme principe que `GenerateurImages` pour les photos (15 sept.) :
    Groq ou Claude peuvent tomber en panne (quota, reseau, service en
    maintenance) en pleine conversation. Sans repli, Luna redevenait
    hors-ligne pour tout le reste de l'echange alors qu'un autre moteur
    etait peut-etre deja configure a cote.
    """

    def __init__(self, moteurs: list[Moteur]):
        # MoteurHorsLigne ferme toujours la marche : sa reponse ne leve
        # jamais d'ErreurMoteur, donc la chaine ne peut jamais echouer
        # completement -- au pire, Luna dit qu'elle est hors ligne.
        self._moteurs = [m for m in moteurs if m.disponible] + [MoteurHorsLigne()]
        self.nom = self._moteurs[0].nom
        self.disponible = True

    def repondre(self, systeme: str, tours: list[dict]) -> str:
        derniere: ErreurMoteur | None = None
        for m in self._moteurs:
            try:
                return m.repondre(systeme, tours)
            except ErreurMoteur as e:
                derniere = e
                logger.warning("moteur %s indisponible (%s) -- on essaie le "
                               "suivant si un autre est configure.", m.nom, e)
        raise derniere or ErreurMoteur("aucun moteur n'a repondu")


def choisir_moteur() -> Moteur:
    """Chaine de repli : compatible-OpenAI (Groq...), puis Claude, puis
    hors-ligne en dernier recours garanti."""
    return MoteurAvecRepli([MoteurCompatibleOpenAI(), MoteurClaude()])


# --------------------------------------------------------------------------
# Formats acceptes par SDXL. Le portrait est le defaut : Luna est un
# personnage, pas un paysage, et un cadrage vertical rend mieux une
# silhouette entiere comme un plan rapproche.
FORMATS = {
    "portrait": (832, 1216),
    "carre": (1024, 1024),
    "paysage": (1216, 832),
}


class GenerateurImages:
    """Generation d'images, avec repli automatique entre fournisseurs.

    Trois fournisseurs integres, tentes DANS L'ORDRE jusqu'a ce qu'un
    reussisse (pas seulement choisi une fois pour toutes) -- trouve le
    15 sept. quand Hugging Face a soudainement renvoye HTTP 402 (quota
    gratuit mensuel epuise) en plein milieu d'une serie de generations :
    sans repli, Luna restait bloquee jusqu'au mois suivant alors qu'un
    autre fournisseur gratuit etait deja configure a cote.

    - **Stability** (payant, quelques centimes/image) : SDXL, la plus
      haute qualite. `STABILITY_API_KEY`.
    - **Hugging Face** (gratuit avec quota mensuel) :
      `HUGGINGFACE_API_KEY`, modele `stabilityai/stable-diffusion-3-medium-diffusers`
      sur le fournisseur `hf-inference`.
    - **Cloudflare Workers AI** (gratuit avec quota QUOTIDIEN, verifie
      fonctionnel le 15 sept.) : `CLOUDFLARE_ACCOUNT_ID` +
      `CLOUDFLARE_API_TOKEN` (permission "Workers AI"), modele
      `@cf/stabilityai/stable-diffusion-xl-base-1.0`.

    LUNA_IMAGE_URL/LUNA_IMAGE_KEY permettent de pointer ailleurs — ta
    propre instance Stable Diffusion / ComfyUI, ou un service special.
    Dans ce cas le corps envoye reste au format Stability ; adapte-le si
    ton endpoint differe. Un fournisseur personnalise passe toujours en
    premier.

    `fournisseur`/`cle`/`url`/`modele` refletent le PREMIER candidat
    configure (pour l'introspection, ex. `luna.py check`) ; `generer()`
    essaie ensuite tous les candidats configures, pas seulement celui-la.
    """

    MODELE_DEFAUT_STABILITY = "stable-diffusion-xl-1024-v1-0"
    MODELE_DEFAUT_HF = "stabilityai/stable-diffusion-3-medium-diffusers"
    # SDXL-base sur Cloudflare donne un rendu illustration/dessin, pas
    # photoréaliste (verifié le 15 sept., y compris une derive de couleur
    # de cheveux) -- Flux, teste le meme soir, est nettement plus realiste.
    # FLUX.2 depuis le 19 sept. (voir _generer_cloudflare) : nettement
    # plus photorealiste, et il n'a pas les refus intempestifs de
    # flux-1-schnell sur des scenes anodines.
    MODELE_DEFAUT_CLOUDFLARE = "@cf/black-forest-labs/flux-2-dev"

    def __init__(self, cle: str = "", url: str = "", modele: str = ""):
        stability = cle or os.getenv("STABILITY_API_KEY", "")
        if stability.lower().startswith("your_"):
            # Placeholder jamais remplace (convention de .env.example dans
            # tout ce depot) : le traiter comme absent plutot que d'echouer
            # en HTTP 401 alors qu'un fournisseur gratuit est peut-etre
            # configure. Trouve le 15 sept. sur ce depot precisement.
            stability = ""
        huggingface = os.getenv("HUGGINGFACE_API_KEY", "")
        cf_compte = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        cf_jeton = os.getenv("CLOUDFLARE_API_TOKEN", "")
        perso = url or os.getenv("LUNA_IMAGE_URL", "")

        candidats = []
        if perso:
            candidats.append({
                "nom": "stability",     # format de corps suppose
                "cle": cle or os.getenv("LUNA_IMAGE_KEY", "") or stability,
                "url": perso,
                "modele": modele or os.getenv("LUNA_IMAGE_MODELE", self.MODELE_DEFAUT_STABILITY),
            })
        if stability:
            m = modele or os.getenv("LUNA_IMAGE_MODELE", self.MODELE_DEFAUT_STABILITY)
            candidats.append({
                "nom": "stability", "cle": stability, "modele": m,
                "url": f"https://api.stability.ai/v1/generation/{m}/text-to-image",
            })
        if huggingface:
            m = modele or os.getenv("LUNA_IMAGE_MODELE", self.MODELE_DEFAUT_HF)
            candidats.append({
                "nom": "huggingface", "cle": huggingface, "modele": m,
                "url": f"https://router.huggingface.co/hf-inference/models/{m}",
            })
        if cf_compte and cf_jeton:
            m = modele or os.getenv("LUNA_IMAGE_MODELE", self.MODELE_DEFAUT_CLOUDFLARE)
            candidats.append({
                "nom": "cloudflare", "cle": cf_jeton, "modele": m,
                "url": f"https://api.cloudflare.com/client/v4/accounts/{cf_compte}/ai/run/{m}",
            })
        if not candidats:
            candidats.append({
                "nom": "stability", "cle": "",
                "modele": modele or self.MODELE_DEFAUT_STABILITY,
                "url": f"https://api.stability.ai/v1/generation/{modele or self.MODELE_DEFAUT_STABILITY}/text-to-image",
            })

        self._candidats = candidats
        premier = candidats[0]
        self.fournisseur = premier["nom"]
        self.cle = premier["cle"]
        self.url = premier["url"]
        self.modele = premier["modele"]

    @property
    def disponible(self) -> bool:
        return any(c["cle"] and c["url"] for c in self._candidats)

    def generer(self, prompt: str, negatif: str = "", graine: int = 0,
                format: str = "portrait") -> bytes:
        if not self.disponible:
            raise ErreurMoteur("aucune cle d'images configuree")
        methodes = {
            "stability": self._generer_stability,
            "huggingface": self._generer_huggingface,
            "cloudflare": self._generer_cloudflare,
        }
        derniere_erreur: ErreurMoteur | None = None
        for candidat in self._candidats:
            if not (candidat["cle"] and candidat["url"]):
                continue
            try:
                return methodes[candidat["nom"]](
                    candidat["cle"], candidat["url"], prompt, negatif, graine, format)
            except ErreurMoteur as e:
                derniere_erreur = e
                logger.warning("generateur d'images %s indisponible (%s) -- "
                               "on essaie le suivant si un autre est configure.",
                               candidat["nom"], e)
        raise derniere_erreur or ErreurMoteur("aucun fournisseur d'images n'a repondu")

    @staticmethod
    def _requeter(url: str, cle: str, corps: dict) -> bytes:
        requete = urllib.request.Request(
            url, data=json.dumps(corps).encode("utf-8"),
            headers={"content-type": "application/json", "accept": "application/json",
                     "authorization": f"Bearer {cle}", **ENTETE_NAVIGATEUR},
            method="POST")
        try:
            with urllib.request.urlopen(requete, timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise ErreurMoteur(f"HTTP {e.code} : {e.read().decode('utf-8','replace')[:300]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurMoteur(f"reseau : {e}") from e

    def _generer_stability(self, cle: str, url: str, prompt: str, negatif: str,
                            graine: int, format: str) -> bytes:
        largeur, hauteur = FORMATS.get(format, FORMATS["portrait"])
        textes = [{"text": prompt, "weight": 1}]
        if negatif:
            textes.append({"text": negatif, "weight": -1})
        # cfg 6 plutot que 7, et 40 pas plutot que 30 : sur un portrait, une
        # contrainte un peu plus lache et un echantillonnage plus long
        # donnent une peau moins lissee et des mains plus sures.
        corps = {"text_prompts": textes, "cfg_scale": 6, "height": hauteur,
                 "width": largeur, "samples": 1, "steps": 40}
        if graine:
            corps["seed"] = graine
        brut = self._requeter(url, cle, corps)
        import base64
        try:
            reponse = json.loads(brut.decode("utf-8"))
            return base64.b64decode(reponse["artifacts"][0]["base64"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ErreurMoteur("reponse image inattendue") from e

    def _generer_huggingface(self, cle: str, url: str, prompt: str, negatif: str,
                              graine: int, format: str) -> bytes:
        largeur, hauteur = FORMATS.get(format, FORMATS["portrait"])
        parametres = {"width": largeur, "height": hauteur}
        if negatif:
            parametres["negative_prompt"] = negatif
        if graine:
            parametres["seed"] = graine
        corps = {"inputs": prompt, "parameters": parametres}
        brut = self._requeter(url, cle, corps)
        # `hf-inference` route vers plusieurs fournisseurs tiers, et ils ne
        # repondent pas tous pareil : la plupart renvoient l'image en octets
        # bruts, certains renvoient une chaine JSON contenant le base64 tout
        # seul ("iVBORw0..."), et une erreur arrive en objet JSON. Trouve le
        # 15 sept. : la meme requete a donne les deux formats a des essais
        # differents.
        import base64
        if brut[:1] == b"{":
            try:
                detail = json.loads(brut.decode("utf-8")).get("error", "")
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = ""
            raise ErreurMoteur(f"reponse image inattendue : {detail}"[:300])
        if brut[:1] == b'"':
            try:
                return base64.b64decode(json.loads(brut.decode("utf-8")))
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as e:
                raise ErreurMoteur("reponse image inattendue (base64 invalide)") from e
        return brut


    @staticmethod
    def _requeter_multipart(url: str, cle: str, champs: dict) -> bytes:
        """FLUX.2 n'accepte pas de corps JSON -- il exige du multipart."""
        import uuid

        limite = uuid.uuid4().hex
        corps = b""
        for nom, valeur in champs.items():
            corps += (f"--{limite}\r\n"
                      f'Content-Disposition: form-data; name="{nom}"\r\n\r\n'
                      f"{valeur}\r\n").encode("utf-8")
        corps += f"--{limite}--\r\n".encode("utf-8")
        requete = urllib.request.Request(
            url, data=corps, method="POST",
            headers={"authorization": f"Bearer {cle}",
                     "content-type": f"multipart/form-data; boundary={limite}"})
        # LES ERREURS RESEAU DOIVENT DEVENIR DES `ErreurMoteur`, SINON LE
        # REPLI NE S'EXECUTE PAS.
        #
        # `generer()` essaie les fournisseurs l'un apres l'autre et n'attrape
        # que `ErreurMoteur`. Cette methode-ci, seule de toutes, laissait
        # remonter l'`HTTPError` brute d'urllib : une panne de Cloudflare
        # faisait donc echouer TOUTE la chaine au lieu de passer au suivant.
        #
        # Constate le 20 septembre : « HTTP Error 408: Request Timeout »
        # remonte jusqu'a l'appelant alors que Hugging Face et Stability
        # etaient configures a cote et n'ont jamais ete essayes. Le repli
        # existait, il etait teste, il etait documente -- il ne s'executait
        # simplement pas sur ce chemin-la. Meme piege que le pyramidage et
        # que la pause du rejeu : un garde-fou doit etre verifie SUR CHAQUE
        # CHEMIN, pas une fois dans le cas nominal.
        try:
            with urllib.request.urlopen(requete, timeout=240) as reponse:
                brut = reponse.read()
        except urllib.error.HTTPError as e:
            raise ErreurMoteur(
                f"HTTP {e.code} : {e.read().decode('utf-8', 'replace')[:300]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurMoteur(f"reseau : {e}") from e
        if brut[:1] != b"{":
            return brut
        rep = json.loads(brut.decode("utf-8"))
        if not rep.get("success", True):
            raise ErreurMoteur(f"{rep.get('errors', '')}"[:300])
        b64 = (rep.get("result") or {}).get("image")
        if not b64:
            raise ErreurMoteur("reponse image inattendue (pas d'image)")
        import base64
        return base64.b64decode(b64)

    def _generer_cloudflare(self, cle: str, url: str, prompt: str, negatif: str,
                             graine: int, format: str) -> bytes:
        # Flux-1-schnell (le defaut, choisi pour son realisme -- SDXL-base
        # sur Cloudflare rendait des illustrations, pas des photos) ne
        # supporte QUE `prompt` et `steps` : `width`/`height`/`seed`/
        # `negative_prompt` sont rejetes (HTTP 400, verifie le 15 sept.).
        # Consequence assumee : format fixe en 1024x1024, pas de graine
        # (donc pas de garantie de reproduire exactement le meme visage
        # d'une image a l'autre avec ce fournisseur precis), pas de
        # negatif. C'est un repli de secours, pas le fournisseur principal.
        #
        # 19 SEPT. : FLUX.2 EST DISPONIBLE, ET C'EST LE SAUT DE REALISME
        # QUE L'OPERATEUR DEMANDAIT ("les photos ne sont pas encore assez
        # reelles, il manque une grosse amelioration"). Deux generations
        # au-dessus de flux-1-schnell. Il parle un autre protocole :
        # multipart/form-data, pas du JSON -- un corps JSON est refuse
        # avec "required properties at '/' are 'multipart'".
        #
        # Au passage, flux-1-schnell refusait des scenes parfaitement
        # anodines comme "etudiante sur un campus" ("Input prompt contains
        # NSFW content") : c'est ce qui faisait echouer des generations
        # sans raison lisible. FLUX.2 accepte les memes prompts.
        # 20 SEPT. : FLUX.2 TOMBE, ET IL EMPORTAIT TOUT AVEC LUI.
        #
        # Cloudflare a rendu « AiError: Request timeout » (HTTP 408) sur
        # CHAQUE appel FLUX.2 de la soiree -- y compris sur un prompt
        # trivial (« une pomme rouge sur une table »), donc ce n'etait ni
        # la scene ni le filtre de contenu. Le meme soir, flux-1-schnell
        # repondait en 2 secondes et SDXL en 9.
        #
        # Un fournisseur ne se resume pas a un modele. La chaine de repli
        # d'origine passait de Hugging Face a Cloudflare, mais si LE
        # modele Cloudflare est en panne, elle n'avait plus rien a
        # proposer -- alors que deux autres modeles du MEME fournisseur
        # fonctionnaient. On redescend donc d'un cran avant d'abandonner.
        #
        # L'ordre traduit ce qu'on perd a chaque marche : flux-1-schnell
        # est moins realiste que FLUX.2 et refuse parfois des scenes
        # anodines ; SDXL rend des illustrations plutot que des photos.
        # On preferera toujours FLUX.2 -- mais une photo un peu moins
        # belle vaut mieux que pas de photo.
        if "flux-2" in url:
            # SDXL A ETE RETIRE DE CE REPLI LE 20 SEPTEMBRE, apres essai.
            #
            # Il ne comprend pas l'ancre d'apparence de Luna : sur le
            # prompt complet il a rendu une PLANCHE DE TRENTE visages
            # deformes -- precisement ce que l'ancre lui interdit ("not a
            # collage, not a contact sheet"). Un repli qui rend une image
            # inutilisable est pire qu'un echec : il rend un fichier
            # valide, de la bonne taille, que rien ne signale comme rate.
            #
            # Il reste bon pour un prompt court et simple ; il n'a rien a
            # faire dans la chaine d'un personnage recurrent.
            replis = ("@cf/black-forest-labs/flux-1-schnell",)
            try:
                return self._requeter_multipart(url, cle, {"prompt": prompt})
            except ErreurMoteur as principale:
                base = url.rsplit("/ai/run/", 1)[0] + "/ai/run/"
                for modele in replis:
                    try:
                        logger.warning(
                            "FLUX.2 indisponible (%s) -- repli sur %s",
                            principale, modele)
                        return self._generer_cloudflare(
                            cle, base + modele, prompt, negatif, graine, format)
                    except ErreurMoteur:
                        continue
                raise

        corps = {"prompt": prompt, "steps": 8}
        brut = self._requeter(url, cle, corps)
        if brut[:1] == b"{":
            try:
                reponse = json.loads(brut.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                raise ErreurMoteur("reponse image inattendue") from e
            if not reponse.get("success", True):
                raise ErreurMoteur(f"{reponse.get('errors', '')}"[:300])
            b64 = reponse.get("result", {}).get("image")
            if not b64:
                raise ErreurMoteur("reponse image inattendue (pas d'image)")
            import base64
            return base64.b64decode(b64)
        return brut
