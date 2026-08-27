"""La voix de Luna : appels audio et visio.

Deux chemins, dans cet ordre :

1. Le navigateur. `speechSynthesis` parle en francais sans cle, sans
   latence reseau et sans envoyer un mot a qui que ce soit. C'est le
   defaut, et c'est deja convaincant avec une voix francaise de qualite.
2. Un prestataire de synthese vocale (ElevenLabs, Azure, Cartesia...),
   si LUNA_TTS_URL et LUNA_TTS_KEY sont renseignes. Meilleure voix,
   mais chaque phrase part chez un tiers : a savoir avant d'y mettre
   une conversation intime.

Cote ecoute, l'application utilise la reconnaissance vocale du navigateur
(Chrome / Edge) : tu parles, elle repond.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

# Mention obligatoire au decroche d'un appel telephonique : dans plusieurs
# pays (et dans les regles de la plupart des operateurs), une voix
# synthetique doit se declarer. C'est aussi la promesse du produit :
# Luna est un personnage, elle ne pretend jamais l'inverse.
ANNONCE_IA = ("Bonjour, ici Luna. Je suis un personnage virtuel anime par "
              "une intelligence artificielle. Cet appel est reserve aux adultes.")


@dataclass(frozen=True)
class ProfilVoix:
    langue: str = "fr-FR"
    hauteur: float = 1.08     # legerement claire
    debit: float = 0.98       # posee
    volume: float = 1.0
    prefere: tuple[str, ...] = ("Amelie", "Audrey", "Google français", "Microsoft Denise")

    def en_dict(self) -> dict:
        return {"langue": self.langue, "hauteur": self.hauteur,
                "debit": self.debit, "volume": self.volume,
                "prefere": list(self.prefere)}


# Le moment colore la voix : plus lente et plus grave le soir.
COULEURS = {
    "matin": (1.10, 1.02),
    "travail": (1.06, 1.05),
    "pause": (1.08, 1.00),
    "retour": (1.05, 0.97),
    "soiree": (1.00, 0.92),
    "soiree_privee": (0.96, 0.86),
    "nuit": (0.97, 0.88),
}


def profil_pour(moment_cle: str) -> ProfilVoix:
    hauteur, debit = COULEURS.get(moment_cle, (1.08, 0.98))
    return ProfilVoix(hauteur=hauteur, debit=debit)


class FournisseurVoix:
    """Synthese vocale externe, optionnelle."""

    def __init__(self, url: str = "", cle: str = "", voix: str = ""):
        self.url = url or os.getenv("LUNA_TTS_URL", "")
        self.cle = cle or os.getenv("LUNA_TTS_KEY", "")
        self.voix = voix or os.getenv("LUNA_TTS_VOIX", "")

    @property
    def disponible(self) -> bool:
        return bool(self.url and self.cle)

    def parler(self, texte: str) -> bytes:
        """Rend l'audio encode (mp3 le plus souvent) pour ce texte."""
        if not self.disponible:
            raise RuntimeError("aucun prestataire de voix configure")
        corps = {"text": texte, "voice": self.voix, "language": "fr"}
        requete = urllib.request.Request(
            self.url, data=json.dumps(corps).encode("utf-8"),
            headers={"content-type": "application/json",
                     "authorization": f"Bearer {self.cle}",
                     "xi-api-key": self.cle},
            method="POST")
        try:
            with urllib.request.urlopen(requete, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} : {e.read().decode('utf-8','replace')[:200]}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise RuntimeError(f"reseau : {e}") from e
