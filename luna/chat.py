"""Le moteur de conversation : ce qui fait tenir Luna ensemble.

Il enchaine, pour chaque message : lire les signaux, apprendre ce qu'il
faut retenir, choisir le moment, calculer le registre reellement autorise,
construire le prompt, appeler le moteur, noter l'echange.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from . import limites, prompt as prompt_mod
from .avatar import expression_pour
from .memoire import Memoire
from .moments import MOMENTS, Moment, moment_pour
from .moteurs import ErreurMoteur, Moteur, choisir_moteur
from .persona import LUNA, Persona
from .voix import profil_pour


@dataclass
class Reponse:
    texte: str
    moment: str
    registre: str
    expression: str
    voix: dict
    signaux: list[str] = field(default_factory=list)
    erreur: str = ""


class Luna:
    def __init__(self, memoire: Memoire | None = None,
                 porte: limites.PorteAdulte | None = None,
                 moteur: Moteur | None = None,
                 persona: Persona = LUNA,
                 horloge=datetime.now):
        self.persona = persona
        self.memoire = memoire or Memoire()
        self.porte = porte or limites.PorteAdulte()
        self.moteur = moteur or choisir_moteur()
        self.horloge = horloge
        self.registre_demande = limites.SENSUEL
        self.moment_force: Moment | None = None

    # -- reglages ---------------------------------------------------------
    def demander_registre(self, registre: str) -> str:
        if registre in limites.REGISTRES:
            self.registre_demande = registre
        return self.registre_demande

    def forcer_moment(self, cle: str) -> Moment:
        """Bascule manuelle (« soiree privee » ne s'active jamais seule)."""
        moment = MOMENTS.get(cle)
        if moment is not None:
            self.moment_force = moment
        return self.moment_force or self.moment()

    def relacher_moment(self) -> None:
        self.moment_force = None

    def moment(self) -> Moment:
        return self.moment_force or moment_pour(self.horloge())

    def registre_effectif(self, canal: str = "app") -> str:
        registre = self.porte.registre_effectif(self.registre_demande, canal)
        moment = self.moment()
        if moment.sur_demande and limites.rang(registre) < limites.rang(limites.SENSUEL):
            # Soiree privee sans acces adulte : on revient a la soiree normale.
            self.moment_force = MOMENTS["soiree"]
        return registre

    # -- conversation -----------------------------------------------------
    def ouverture(self, canal: str = "app") -> Reponse:
        """Le premier message, celui qu'elle envoie sans qu'on lui demande."""
        moment = self.moment()
        ecart = self.memoire.bonjour()
        texte = moment.ouvertures[self.memoire.rencontres % len(moment.ouvertures)]
        if ecart > 48 and self.memoire.prenom:
            texte = (f"{self.memoire.prenom} ! Tu m'as manque 🥺 " + texte)
        self.memoire.noter("assistant", texte)
        self.memoire.sauver()
        registre = self.registre_effectif(canal)
        return Reponse(texte=texte, moment=moment.cle, registre=registre,
                       expression="sourire", voix=profil_pour(moment.cle).en_dict())

    def repondre(self, message: str, canal: str = "app") -> Reponse:
        message = (message or "").strip()
        if not message:
            raise ValueError("message vide")

        signaux = limites.analyser(message)
        if any(s.cle == "mineur" for s in signaux):
            # Verrou dur : plus aucun registre au-dessus de tendre, et la
            # porte adulte est revoquee, pas seulement contournee.
            self.porte.revoquer()
            self.registre_demande = limites.TENDRE
            self.relacher_moment()

        self.memoire.apprendre(message)
        self.memoire.noter("user", message)

        moment = self.moment()
        registre = self.registre_effectif(canal)
        systeme = prompt_mod.construire(
            self.persona, moment, self.memoire, registre, signaux,
            canal=canal, quand=self.horloge())
        tours = [{"role": t["role"], "texte": t["texte"]}
                 for t in self.memoire.historique(14)]

        erreur = ""
        try:
            texte = self.moteur.repondre(systeme, tours)
        except ErreurMoteur as e:
            erreur = str(e)
            texte = ("Je n'arrive pas a te repondre la, il y a un souci "
                     "technique de mon cote 😔 Reessaie dans un instant ?")

        self.memoire.noter("assistant", texte)
        self.memoire.sauver()
        return Reponse(
            texte=texte,
            moment=moment.cle,
            registre=registre,
            expression=expression_pour(texte, registre),
            voix=profil_pour(moment.cle).en_dict(),
            signaux=[s.cle for s in signaux],
            erreur=erreur,
        )
