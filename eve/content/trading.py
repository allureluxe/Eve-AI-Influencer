"""Contenu « coulisses » sur le système de trading — chiffres réels uniquement.

Principe de conception : **le générateur est incapable d'inventer un chiffre
de performance.** Les nombres ne peuvent venir que de
`data/trading/results.json`, un fichier alimenté depuis le vrai système.

- Fichier absent  → le pilier `work` produit du contenu de méthode, sans
  aucun chiffre. C'est le comportement par défaut, et il est sûr.
- Fichier présent mais incomplet → erreur explicite, rien n'est publié.
- Fichier valide  → les chiffres sont repris tels quels, avec la période,
  le drawdown et l'avertissement de risque, sans exception.

Le drawdown maximal est obligatoire : une performance affichée sans son
risque est trompeuse, même si le rendement est exact.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from eve.config import settings

RESULTS_PATH = settings.paths.data / "trading" / "results.json"

CHAMPS_REQUIS = ("system_name", "period", "metrics")
METRIQUES_REQUISES = ("return_pct", "max_drawdown_pct")


class TradingDataError(ValueError):
    """Données de performance absentes, incomplètes ou incohérentes."""


@dataclass(frozen=True)
class TradingResults:
    system_name: str
    start: str
    end: str
    metrics: dict[str, float]
    currency: str = ""
    verified_by: str = ""
    verification_url: str = ""
    monthly: tuple[dict, ...] = ()
    notes: str = ""

    @property
    def periode(self) -> str:
        return f"du {self.start} au {self.end}"

    @property
    def rendement(self) -> float:
        return float(self.metrics["return_pct"])

    @property
    def drawdown(self) -> float:
        return float(self.metrics["max_drawdown_pct"])

    def ligne_chiffres(self) -> str:
        """Les chiffres, dans l'ordre qui ne trompe personne : risque inclus."""
        bouts = [f"{self.rendement:+.1f} % sur la période",
                 f"drawdown maximal {self.drawdown:.1f} %"]
        if "trades" in self.metrics:
            bouts.append(f"{int(self.metrics['trades'])} opérations")
        if "profit_factor" in self.metrics:
            bouts.append(f"profit factor {float(self.metrics['profit_factor']):.2f}")
        if "win_rate_pct" in self.metrics:
            bouts.append(f"{float(self.metrics['win_rate_pct']):.1f} % de trades gagnants")
        return " · ".join(bouts)


def load_results(path: Path | None = None) -> TradingResults | None:
    """Charge les résultats réels. Renvoie None si aucun fichier n'existe.

    Lève `TradingDataError` si le fichier existe mais ne tient pas debout :
    mieux vaut bloquer la production que publier des chiffres douteux.
    """
    src = path or RESULTS_PATH
    if not src.exists():
        return None

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TradingDataError(f"{src} n'est pas un JSON valide : {exc}") from exc

    manquants = [c for c in CHAMPS_REQUIS if c not in data]
    if manquants:
        raise TradingDataError(f"{src} : champs manquants {manquants}.")

    metrics = data["metrics"]
    absents = [m for m in METRIQUES_REQUISES if m not in metrics]
    if absents:
        raise TradingDataError(
            f"{src} : métriques obligatoires manquantes {absents}. "
            "Le drawdown maximal est requis — un rendement sans son risque "
            "est trompeur, même exact.")

    periode = data["period"]
    if not periode.get("start") or not periode.get("end"):
        raise TradingDataError(f"{src} : la période (start, end) est obligatoire.")
    if periode["end"] > date.today().isoformat():
        raise TradingDataError(
            f"{src} : la période se termine dans le futur ({periode['end']}). "
            "Seuls des résultats passés et constatés peuvent être publiés.")
    if float(metrics["max_drawdown_pct"]) < 0:
        raise TradingDataError(f"{src} : le drawdown doit être exprimé en valeur positive.")

    return TradingResults(
        system_name=str(data["system_name"]),
        start=str(periode["start"]),
        end=str(periode["end"]),
        metrics={k: float(v) for k, v in metrics.items()},
        currency=str(data.get("account_currency", "")),
        verified_by=str(data.get("verified_by", "")),
        verification_url=str(data.get("verification_url", "")),
        monthly=tuple(data.get("monthly", ())),
        notes=str(data.get("notes", "")),
    )


# Contenu de méthode : aucun chiffre, utilisable en permanence.
METHODE_TOPICS = [
    ("Ce qu'est vraiment un système automatisé",
     "Un ensemble de règles écrites à l'avance, exécutées sans moi. C'est tout.",
     ["les règles sont décidées à froid, jamais pendant une position",
      "le système ne prédit rien, il réagit",
      "la partie difficile n'est pas le code, c'est de ne pas y toucher"]),
    ("Le drawdown, la seule métrique que je regarde",
     "C'est la baisse maximale subie avant de revenir au point haut. Elle décide de tout.",
     ["un rendement sans son drawdown ne veut rien dire",
      "on ne tient pas un système dont la baisse dépasse ce qu'on supporte",
      "je regarde toujours le pire mois avant le meilleur"]),
    ("Pourquoi la plupart des robots vendus en ligne ne valent rien",
     "Ils sont optimisés sur le passé jusqu'à ce que la courbe soit belle.",
     ["une courbe parfaite est un signal d'alerte, pas de qualité",
      "sans test hors échantillon, un résultat ne prouve rien",
      "personne ne vend une machine à imprimer de l'argent"]),
    ("Combien de temps avant de savoir si ça marche",
     "Des mois. Un bon mois ne prouve rien, un mauvais non plus.",
     ["il faut assez d'opérations pour que le hasard s'efface",
      "je compte en centaines de trades, pas en semaines",
      "la patience fait partie de la méthode"]),
    ("Ce que je note à chaque décision",
     "La raison avant, le résultat après. Séparément, et dans cet ordre.",
     ["écrire la raison avant de connaître l'issue",
      "relire trois mois plus tard",
      "un bon résultat sur une mauvaise raison est le pire des cas"]),
]


def build_work_content(results: TradingResults | None, rng) -> tuple[str, str, list[str]]:
    """Retourne (titre, réponse, points) pour le pilier `work`.

    Avec des données réelles, une publication sur deux les cite ; les autres
    parlent méthode. Sans données, on ne parle que méthode.
    """
    if results is None or rng.random() < 0.5:
        return rng.choice(METHODE_TOPICS)

    titre = f"Les chiffres de {results.system_name}, {results.periode}"
    reponse = results.ligne_chiffres()
    points = ["ce sont des résultats passés, ils ne préjugent de rien",
              "le drawdown compte autant que le rendement"]
    if results.verified_by:
        points.append(f"vérifié par {results.verified_by}")
    if results.notes:
        points.append(results.notes)
    return titre, reponse, points
