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
import os
import random
import urllib.error
import urllib.request

TIMEOUT = 60


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
        entetes = {"content-type": "application/json"}
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
def choisir_moteur() -> Moteur:
    """Le premier moteur configure gagne : endpoint perso, puis Claude."""
    perso = MoteurCompatibleOpenAI()
    if perso.disponible:
        return perso
    claude = MoteurClaude()
    if claude.disponible:
        return claude
    return MoteurHorsLigne()


# --------------------------------------------------------------------------
class GenerateurImages:
    """Generation d'images, endpoint configurable.

    Par defaut Stability (deja utilise par le module Eve de ce depot).
    LUNA_IMAGE_URL permet de pointer ailleurs : ta propre instance
    Stable Diffusion / ComfyUI, ou un service specialise. Le corps envoye
    reste le format Stability ; adapte-le si ton endpoint differe.
    """

    def __init__(self, cle: str = "", url: str = "", modele: str = ""):
        self.cle = cle or os.getenv("STABILITY_API_KEY", "") or os.getenv("LUNA_IMAGE_KEY", "")
        self.modele = modele or os.getenv("LUNA_IMAGE_MODELE", "stable-diffusion-v1-6")
        self.url = url or os.getenv("LUNA_IMAGE_URL", "") or (
            f"https://api.stability.ai/v1/generation/{self.modele}/text-to-image")

    @property
    def disponible(self) -> bool:
        return bool(self.cle and self.url)

    def generer(self, prompt: str, negatif: str = "", graine: int = 0) -> bytes:
        if not self.disponible:
            raise ErreurMoteur("aucune cle d'images configuree")
        textes = [{"text": prompt, "weight": 1}]
        if negatif:
            textes.append({"text": negatif, "weight": -1})
        corps = {"text_prompts": textes, "cfg_scale": 7, "height": 1024,
                 "width": 1024, "samples": 1, "steps": 30}
        if graine:
            corps["seed"] = graine
        requete = urllib.request.Request(
            self.url, data=json.dumps(corps).encode("utf-8"),
            headers={"content-type": "application/json", "accept": "application/json",
                     "authorization": f"Bearer {self.cle}"}, method="POST")
        try:
            with urllib.request.urlopen(requete, timeout=120) as r:
                reponse = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise ErreurMoteur(f"HTTP {e.code} : {e.read().decode('utf-8','replace')[:300]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ErreurMoteur(f"reseau : {e}") from e
        import base64
        try:
            return base64.b64decode(reponse["artifacts"][0]["base64"])
        except (KeyError, IndexError, TypeError) as e:
            raise ErreurMoteur("reponse image inattendue") from e
