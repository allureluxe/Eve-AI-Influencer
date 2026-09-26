"""Le plafond de depense quotidien de Luna.

POURQUOI CE FICHIER EXISTE AVANT LE MOTEUR PAYANT

Jusqu'ici, tous les generateurs d'images de Luna etaient gratuits. Leur
pire panne etait un quota epuise : on attendait minuit. Le 22 septembre,
une tache automatique a brule le quota Cloudflare de la journee en
vingt-et-un reessais, et l'operateur a attendu sa photo quatre jours.
Desagreable, gratuit.

Avec une cle OpenAI, le meme enchainement ne coute plus une attente : il
coute de l'argent. Et la boucle qui l'appelle tourne **toutes les deux
minutes** par cron, avec publication automatique. Un prompt qui echoue
en boucle, un planificateur qui redemande, une ligne dupliquee dans la
file — et la facture court toute la nuit sans que personne ne regarde.

Ce module est la reponse : **un compteur qui refuse**. Pas un
avertissement dans un journal que personne ne lit.

    depense = Depenses()
    depense.reserver(0.07, "image openai")   # leve BudgetEpuise si trop

LE COMPTEUR EST UN FICHIER, PAS UNE VARIABLE. Chaque appel du cron est
un processus neuf : un compteur en memoire repartirait de zero toutes
les deux minutes, ce qui revient a n'avoir aucun plafond. Le fichier est
la seule forme qui survive au processus.

LA JOURNEE EST CELLE DE PARIS, pas UTC. L'operateur lit ses depenses a
l'heure ou il vit ; un plafond qui se reinitialise a 2h du matin chez
lui serait incomprehensible le jour ou il le verifierait.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

#: Plafond par defaut, en euros. Volontairement bas : il vaut mieux que
#: l'operateur le releve sciemment que de decouvrir une facture.
PLAFOND_DEFAUT_EUR = 1.00

FICHIER = Path(os.getenv("LUNA_DEPENSES_FICHIER", "data/depenses_luna.json"))


class BudgetEpuise(RuntimeError):
    """Le plafond du jour est atteint. Rien n'a ete depense."""


def _aujourdhui() -> str:
    """La date a Paris, au format ISO."""
    try:
        from zoneinfo import ZoneInfo
        maintenant = dt.datetime.now(ZoneInfo("Europe/Paris"))
    except Exception:                                          # noqa: BLE001
        maintenant = dt.datetime.now()
    return maintenant.date().isoformat()


class Depenses:
    """Le journal des depenses du jour, et le refus quand il est plein."""

    def __init__(self, plafond_eur: float | None = None,
                 fichier: Path | None = None):
        if plafond_eur is None:
            plafond_eur = float(os.getenv("LUNA_BUDGET_JOUR_EUR",
                                          PLAFOND_DEFAUT_EUR))
        self.plafond = max(0.0, plafond_eur)
        # LE CHEMIN SE LIT A LA CONSTRUCTION, PAS A L'IMPORT.
        #
        # `FICHIER` est evalue une fois, au chargement du module : un test
        # qui pose LUNA_DEPENSES_FICHIER apres coup n'avait donc AUCUN
        # effet, et ecrivait dans le compteur de production. C'est arrive
        # le 26 septembre — 2,40 EUR fantomes inscrits par trois passages
        # de la suite de tests, qui auraient bloque les vraies depenses
        # de la journee.
        #
        # Le depot connait deja ce piege : « les diagnostics ET la suite
        # de tests ecrivaient dans data/ et remettaient l'echantillon a
        # zero ». Meme cause, meme remede — resoudre le chemin tard.
        self.fichier = fichier or Path(
            os.getenv("LUNA_DEPENSES_FICHIER", str(FICHIER)))

    def _lire(self) -> dict:
        # UN FICHIER ABSENT EST NORMAL ; UN FICHIER ILLISIBLE NE L'EST PAS.
        #
        # La distinction decide de tout. Au premier appel de la journee le
        # fichier n'existe pas : le total vaut zero, c'est juste. Mais un
        # fichier present et corrompu — coupure en plein ecriture, disque
        # plein, sauvegarde a moitie restauree — signifie qu'on NE SAIT
        # PAS combien a deja ete depense. Repartir de zero dans ce cas,
        # c'est lever le plafond precisement le jour ou la machine va mal.
        #
        # « Un garde-fou qui ne peut pas verifier doit refuser » : c'est
        # ecrit dans le CLAUDE.md de ce depot, et ce compteur-ci garde de
        # l'argent reel. Il refuse.
        if not self.fichier.exists():
            return {"date": _aujourdhui(), "total_eur": 0.0, "lignes": []}
        try:
            donnees = json.loads(self.fichier.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise BudgetEpuise(
                f"compteur de depenses illisible ({self.fichier}) : {e}. "
                "Par securite, rien n'est depense tant qu'on ne sait pas "
                "combien l'a deja ete. Supprimer le fichier remet le "
                "compteur du jour a zero, en connaissance de cause."
            ) from e
        if not isinstance(donnees, dict):
            raise BudgetEpuise(
                f"compteur de depenses au mauvais format ({self.fichier}).")
        # UN JOUR DIFFERENT REMET LE COMPTEUR A ZERO, et la comparaison
        # se fait sur la date ECRITE, jamais sur l'age du fichier : un
        # fichier touche par une sauvegarde ne doit pas rouvrir le
        # robinet.
        if donnees.get("date") != _aujourdhui():
            return {"date": _aujourdhui(), "total_eur": 0.0, "lignes": []}
        return donnees

    def _ecrire(self, donnees: dict) -> None:
        self.fichier.parent.mkdir(parents=True, exist_ok=True)
        # Ecriture atomique : une coupure au milieu d'un write laisserait
        # un JSON tronque, donc un compteur illisible, donc — avec le
        # `except` de `_lire` — un compteur a zero. Le plafond
        # disparaitrait exactement le jour ou la machine a eu un probleme.
        provisoire = self.fichier.with_suffix(".tmp")
        provisoire.write_text(json.dumps(donnees, ensure_ascii=False),
                              encoding="utf-8")
        provisoire.replace(self.fichier)

    def total_du_jour(self) -> float:
        return round(float(self._lire().get("total_eur", 0.0)), 4)

    def reste(self) -> float:
        return round(max(0.0, self.plafond - self.total_du_jour()), 4)

    def reserver(self, cout_eur: float, motif: str = "") -> float:
        """Compte `cout_eur` AVANT la depense. Leve `BudgetEpuise` si trop.

        On reserve avant d'appeler le fournisseur, pas apres : si l'appel
        part et que le processus meurt en route, l'argent est parti quand
        meme. Compter apres coup, c'est ne pas compter les cas ou ca se
        passe mal — precisement ceux qui se repetent.
        """
        cout_eur = max(0.0, float(cout_eur))
        donnees = self._lire()
        total = float(donnees.get("total_eur", 0.0))
        if total + cout_eur > self.plafond:
            raise BudgetEpuise(
                f"plafond du jour atteint : {total:.2f} EUR deja depenses "
                f"sur {self.plafond:.2f} autorises, et cette operation en "
                f"demande {cout_eur:.2f}. Relever LUNA_BUDGET_JOUR_EUR "
                f"pour aller plus loin.")
        donnees["total_eur"] = round(total + cout_eur, 4)
        donnees.setdefault("lignes", []).append({
            "horodatage": dt.datetime.now(dt.timezone.utc).isoformat(),
            "cout_eur": round(cout_eur, 4), "motif": motif,
        })
        self._ecrire(donnees)
        return round(self.plafond - donnees["total_eur"], 4)
